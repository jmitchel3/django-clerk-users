"""
Clerk authentication middleware.

This middleware validates Clerk JWT tokens and creates Django sessions
for authenticated users. It uses manual session handling instead of
Django's login() to avoid triggering signals that may conflict with Clerk.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.models import AnonymousUser
from django.middleware.csrf import rotate_token
from django.utils.crypto import constant_time_compare

from django_clerk_users.authentication.utils import (
    get_clerk_payload_from_request,
    get_or_create_user_from_payload,
)
from django_clerk_users.client import get_configured_clerk_secret_key
from django_clerk_users.exceptions import ClerkAuthenticationError, ClerkTokenError

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

# Authentication backend path
CLERK_BACKEND = "django_clerk_users.authentication.ClerkBackend"
DEFAULT_CLERK_SESSION_REVALIDATION_SECONDS = 300


def _get_clerk_secret_key() -> str | None:
    return get_configured_clerk_secret_key()


def _get_session_revalidation_seconds() -> int:
    raw_interval = getattr(
        settings,
        "CLERK_SESSION_REVALIDATION_SECONDS",
        DEFAULT_CLERK_SESSION_REVALIDATION_SECONDS,
    )
    try:
        return max(0, int(raw_interval))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid CLERK_SESSION_REVALIDATION_SECONDS value %r, using default %s",
            raw_interval,
            DEFAULT_CLERK_SESSION_REVALIDATION_SECONDS,
        )
        return DEFAULT_CLERK_SESSION_REVALIDATION_SECONDS


class ClerkAuthMiddleware:
    """
    Middleware that authenticates users via Clerk JWT tokens.

    This middleware implements a session-based optimization strategy:
    1. On first request: Validates JWT, creates Django session
    2. On subsequent requests: Uses session (avoids repeated validation)
    3. Periodically re-validates to detect token expiration

    After processing, the middleware sets:
    - request.user: The authenticated Django user (or AnonymousUser)
    - request.clerk_user: Same as request.user (for explicit Clerk access)
    - request.clerk_payload: The decoded JWT payload (if authenticated)
    - request.org: The organization ID from the token (if present)

    Note: This middleware manually sets session data instead of using Django's
    login() function to avoid triggering signals that may conflict with Clerk's
    authentication flow.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        self.debug = getattr(settings, "DEBUG", False)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Process authentication before the view
        self.process_request(request)

        # Call the next middleware/view
        response = self.get_response(request)

        return response

    def process_request(self, request: HttpRequest) -> None:
        """
        Process the request and authenticate the user.

        Sets request.user, request.clerk_user, request.clerk_payload,
        and request.org based on the authentication result.

        Supports hybrid authentication:
        - If user is authenticated via Django session (e.g., admin login),
          respects that authentication and skips Clerk JWT validation
        - Otherwise, attempts Clerk JWT authentication
        """
        # Initialize attributes
        request.clerk_user = None  # type: ignore
        request.clerk_payload = None  # type: ignore
        request.org = None  # type: ignore

        # Skip Clerk authentication if not configured
        if not _get_clerk_secret_key():
            return

        # Check if user is already authenticated via Django's standard auth
        # (e.g., admin login with username/password)
        if hasattr(request, "user") and request.user.is_authenticated:
            # Check if this is a Clerk session or a traditional Django session
            if self._is_clerk_session(request):
                # This is a Clerk session, validate it
                if self._is_session_valid(request):
                    # Clerk session is still valid
                    request.clerk_user = request.user  # type: ignore
                    request.org = request.session.get("clerk_org_id")  # type: ignore
                    return
                # Clerk session expired, clear it and try JWT auth below
                self._clear_session(request)
            else:
                # This is a traditional Django session (e.g., admin login)
                # Don't interfere with it - just skip Clerk authentication
                logger.debug("Using existing Django session (non-Clerk)")
                return

        # Try to authenticate via JWT token
        try:
            payload = get_clerk_payload_from_request(request)
        except ClerkTokenError as e:
            logger.debug(f"Token validation failed: {e}")
            self._set_anonymous(request)
            return

        if not payload:
            # No token provided - anonymous user
            self._set_anonymous(request)
            return

        # Get or create the Django user
        try:
            user, created = get_or_create_user_from_payload(payload)
        except ClerkAuthenticationError as e:
            logger.warning(f"Failed to get/create user: {e}")
            self._set_anonymous(request)
            return
        except Exception as e:
            logger.error(f"ClerkAuthMiddleware error: {e}", exc_info=True)
            if self.debug:
                raise
            self._set_anonymous(request)
            return

        if not user.is_active:
            logger.debug(f"User {user.clerk_id} is inactive")
            self._set_anonymous(request)
            return

        # Create Django session (without calling login())
        self._create_session(request, user, payload)

        # Set request attributes
        user.backend = CLERK_BACKEND
        request.user = user
        request.clerk_user = user  # type: ignore
        request.clerk_payload = payload  # type: ignore
        request.org = payload.get("org_id")  # type: ignore

        if created:
            logger.info(f"Created new user: {user.email} ({user.clerk_id})")

    def _is_clerk_session(self, request: HttpRequest) -> bool:
        """
        Check if the current session is a Clerk-authenticated session.

        Returns True if this session was created by Clerk authentication,
        False if it's a traditional Django session (e.g., admin login).
        """
        # Clerk sessions have the last_clerk_check timestamp
        return "last_clerk_check" in request.session

    def _is_session_valid(self, request: HttpRequest) -> bool:
        """
        Check if the current Clerk session is valid and doesn't need revalidation.

        Returns True if:
        1. User is authenticated in session
        2. The session hasn't expired
        3. The re-validation interval hasn't passed

        Note: This method should only be called for Clerk sessions.
        """
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # Check if re-validation is needed
        last_check = request.session.get("last_clerk_check", 0)
        now = int(time.time())

        if now - last_check > _get_session_revalidation_seconds():
            # Re-validation needed - try to validate the token
            try:
                payload = get_clerk_payload_from_request(request)
                if payload:
                    # Token is still valid, update session
                    request.session["last_clerk_check"] = now
                    request.session["clerk_org_id"] = payload.get("org_id")
                    request.clerk_payload = payload  # type: ignore
                    return True

                # Missing token or invalid payload - end the session
                self._clear_session(request)
                return False
            except ClerkTokenError:
                # Token is invalid - invalidate session
                self._clear_session(request)
                return False

        return True

    def _create_session(self, request: HttpRequest, user, payload: dict) -> None:
        """
        Create a Django session for the authenticated user.

        This mirrors Django's login() session state without sending
        user_logged_in. Keeping Django's auth hash and session-key rotation
        avoids the next AuthenticationMiddleware pass flushing the session.
        """
        session_auth_hash = ""
        if hasattr(user, "get_session_auth_hash"):
            session_auth_hash = user.get_session_auth_hash()

        session_user_id = user._meta.pk.value_to_string(user)
        if SESSION_KEY in request.session:
            if request.session.get(SESSION_KEY) != session_user_id or (
                session_auth_hash
                and not constant_time_compare(
                    request.session.get(HASH_SESSION_KEY, ""),
                    session_auth_hash,
                )
            ):
                request.session.flush()
        else:
            request.session.cycle_key()

        # Manually set session auth data (what login() would do internally).
        request.session[SESSION_KEY] = session_user_id
        request.session[BACKEND_SESSION_KEY] = CLERK_BACKEND
        request.session[HASH_SESSION_KEY] = session_auth_hash

        # Store Clerk-specific session data
        request.session["last_clerk_check"] = int(time.time())
        request.session["clerk_org_id"] = payload.get("org_id")

        rotate_token(request)

        logger.debug("Created session for user %s", user.email)

    def _clear_session(self, request: HttpRequest) -> None:
        """
        Clear the Django session.
        """
        request.session.flush()

    def _set_anonymous(self, request: HttpRequest) -> None:
        """
        Set the request user to anonymous.
        """
        if not hasattr(request, "user") or request.user.is_authenticated:
            request.user = AnonymousUser()
        request.clerk_user = None  # type: ignore
        request.clerk_payload = None  # type: ignore
        request.org = None  # type: ignore
