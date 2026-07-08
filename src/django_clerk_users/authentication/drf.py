"""
Django REST Framework authentication class for Clerk.

This module requires djangorestframework to be installed.
Install it with: pip install django-clerk-users[drf]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.http import HttpRequest

    from django_clerk_users.models import AbstractClerkUser

from django_clerk_users.authentication.utils import (
    get_clerk_payload_from_request,
    get_or_create_user_from_payload,
)
from django_clerk_users.exceptions import ClerkAuthenticationError, ClerkTokenError

logger = logging.getLogger(__name__)

# Defer DRF import - check at class instantiation time
_drf_available = False
_drf_import_error: str | None = None

try:
    from rest_framework import authentication, exceptions

    _drf_available = True
    _BaseAuthentication: Any = authentication.BaseAuthentication
    _SessionAuthentication: Any = authentication.SessionAuthentication
except ImportError:
    _drf_import_error = (
        "Django REST Framework is required for ClerkAuthentication. "
        "Install it with: pip install django-clerk-users[drf]"
    )
    _BaseAuthentication = object
    _SessionAuthentication = object
    exceptions = None  # type: ignore[assignment]


def _authorization_scheme(auth_header: str | bytes) -> str:
    if isinstance(auth_header, bytes):
        auth_header = auth_header.decode("latin1")

    parts = auth_header.strip().split(None, 1)
    if not parts:
        return ""
    return parts[0].lower()


class ClerkAuthentication(_BaseAuthentication):
    """
    Django REST Framework authentication class for Clerk.

    This authentication class validates Clerk JWT tokens and returns
    the corresponding Django user.

    To use this class, add it to DEFAULT_AUTHENTICATION_CLASSES in settings:

        REST_FRAMEWORK = {
            'DEFAULT_AUTHENTICATION_CLASSES': [
                'django_clerk_users.authentication.ClerkAuthentication',
            ],
        }
    """

    def __init__(self) -> None:
        if not _drf_available:
            raise ImportError(_drf_import_error)
        super().__init__()

    def authenticate(
        self, request: HttpRequest
    ) -> tuple[AbstractClerkUser, dict] | None:
        """
        Authenticate the request and return a tuple of (user, auth).

        Args:
            request: The incoming HTTP request.

        Returns:
            A tuple of (user, payload) if authentication succeeds,
            or None if no authentication credentials were provided.

        Raises:
            AuthenticationFailed: If authentication fails.
        """
        try:
            payload = get_clerk_payload_from_request(request)
        except ClerkTokenError as e:
            raise exceptions.AuthenticationFailed(str(e))

        if payload is None:
            return None

        try:
            user, _ = get_or_create_user_from_payload(payload)
        except ClerkAuthenticationError as e:
            raise exceptions.AuthenticationFailed(str(e))

        if not user.is_active:
            raise exceptions.AuthenticationFailed("User is inactive.")

        # Attach the Clerk payload to the request for later use
        request.clerk_payload = payload  # type: ignore

        return (user, payload)

    def authenticate_header(self, request: HttpRequest) -> str:
        """
        Return a string to be used as the WWW-Authenticate header.

        Args:
            request: The incoming HTTP request.

        Returns:
            The authentication scheme identifier.
        """
        return "Bearer"


class CsrfExemptSessionAuthentication(_SessionAuthentication):
    """
    DRF SessionAuthentication variant that does not enforce CSRF.

    Use this only for APIs where session cookies are created by your own login
    flow and requests are same-origin or otherwise protected by your app.
    """

    def __init__(self) -> None:
        if not _drf_available:
            raise ImportError(_drf_import_error)
        super().__init__()

    def enforce_csrf(self, request: HttpRequest) -> None:
        return None


class ClerkSessionAuthentication(_BaseAuthentication):
    """
    DRF authentication that supports Clerk bearer tokens and Django sessions.

    Clerk bearer tokens take precedence. If an Authorization: Bearer header is
    present, Clerk authentication handles the request and any Clerk failure is
    surfaced as an authentication failure. Requests without a bearer token fall
    back to Django session authentication.
    """

    clerk_authentication_class = ClerkAuthentication
    session_authentication_class = CsrfExemptSessionAuthentication

    def __init__(self) -> None:
        if not _drf_available:
            raise ImportError(_drf_import_error)
        super().__init__()
        self.clerk_authentication = self.clerk_authentication_class()
        self.session_authentication = self.session_authentication_class()

    def authenticate(
        self, request: HttpRequest
    ) -> tuple[AbstractClerkUser, dict] | None:
        if (
            _authorization_scheme(request.META.get("HTTP_AUTHORIZATION", ""))
            == "bearer"
        ):
            return self.clerk_authentication.authenticate(request)

        return self.session_authentication.authenticate(request)

    def authenticate_header(self, request: HttpRequest) -> str:
        return "Bearer"
