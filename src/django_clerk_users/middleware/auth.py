"""
Clerk authentication middleware.

This middleware validates Clerk JWT tokens and creates Django sessions
for authenticated users.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import AnonymousUser

from django_clerk_users.authentication.utils import (
    get_clerk_payload_from_request,
    get_or_create_user_from_payload,
)
from django_clerk_users.exceptions import ClerkAuthenticationError, ClerkTokenError
from django_clerk_users.settings import CLERK_SESSION_REVALIDATION_SECONDS

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


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
    """

    def __init__(self, get_response: Callable[["HttpRequest"], "HttpResponse"]):
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        # Process authentication before the view
        self.process_request(request)

        # Call the next middleware/view
        response = self.get_response(request)

        return response

    def process_request(self, request: "HttpRequest") -> None:
        """
        Process the request and authenticate the user.

        Sets request.user, request.clerk_user, request.clerk_payload,
        and request.org based on the authentication result.
        """
        # Initialize attributes
        request.clerk_user = None  # type: ignore
        request.clerk_payload = None  # type: ignore
        request.org = None  # type: ignore

        # Check if user is already authenticated via session
        if self._is_session_valid(request):
            # User is already authenticated, just set clerk attributes
            request.clerk_user = request.user  # type: ignore
            request.org = request.session.get("clerk_org_id")  # type: ignore
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

        if not user.is_active:
            logger.debug(f"User {user.clerk_id} is inactive")
            self._set_anonymous(request)
            return

        # Create Django session
        self._create_session(request, user, payload)

        # Set request attributes
        request.user = user
        request.clerk_user = user  # type: ignore
        request.clerk_payload = payload  # type: ignore
        request.org = payload.get("org_id")  # type: ignore

        if created:
            logger.info(f"Created new user: {user.email} ({user.clerk_id})")

    def _is_session_valid(self, request: "HttpRequest") -> bool:
        """
        Check if the current session is valid and doesn't need revalidation.

        Returns True if:
        1. User is authenticated in session
        2. The session hasn't expired
        3. The re-validation interval hasn't passed
        """
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # Check if re-validation is needed
        last_check = request.session.get("last_clerk_check", 0)
        now = int(time.time())

        if now - last_check > CLERK_SESSION_REVALIDATION_SECONDS:
            # Re-validation needed - try to validate the token
            try:
                payload = get_clerk_payload_from_request(request)
                if payload:
                    # Token is still valid, update session
                    request.session["last_clerk_check"] = now
                    request.session["clerk_org_id"] = payload.get("org_id")
                    request.clerk_payload = payload  # type: ignore
                    return True
                else:
                    # No token or invalid - keep using session for now
                    # (might be a same-origin request without token)
                    return True
            except ClerkTokenError:
                # Token is invalid - invalidate session
                self._clear_session(request)
                return False

        return True

    def _create_session(
        self, request: "HttpRequest", user, payload: dict
    ) -> None:
        """
        Create a Django session for the authenticated user.
        """
        # Log the user in (creates session)
        login(request, user, backend="django_clerk_users.authentication.ClerkBackend")

        # Store Clerk-specific session data
        request.session["last_clerk_check"] = int(time.time())
        request.session["clerk_org_id"] = payload.get("org_id")

    def _clear_session(self, request: "HttpRequest") -> None:
        """
        Clear the Django session.
        """
        request.session.flush()

    def _set_anonymous(self, request: "HttpRequest") -> None:
        """
        Set the request user to anonymous.
        """
        if not hasattr(request, "user") or request.user.is_authenticated:
            request.user = AnonymousUser()
        request.clerk_user = None  # type: ignore
        request.clerk_payload = None  # type: ignore
        request.org = None  # type: ignore
