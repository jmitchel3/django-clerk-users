"""
Hybrid Clerk bearer + Django session authentication for DRF.

Copy this module into your project (for example ``myapp/authentication.py``).
It only uses supported django-clerk-users APIs: no monkey patches and no
rewriting of request headers.
"""

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, SessionAuthentication

from django_clerk_users.authentication import (
    ClerkAuthentication,
    ClerkSessionAuthentication,
)
from django_clerk_users.authentication.utils import get_bearer_token


class CsrfClerkSessionAuthentication(ClerkSessionAuthentication):
    """
    Default precedence, CSRF enforced for cookie sessions.

    ``ClerkSessionAuthentication`` uses ``CsrfExemptSessionAuthentication`` for
    its session fallback. Overriding ``session_authentication_class`` with DRF's
    ``SessionAuthentication`` keeps Django's CSRF check on unsafe methods.

    A non-Bearer Authorization header (or ``Bearer`` with no token, or Bearer
    while Clerk is unconfigured) returns ``None`` so DRF tries the next
    authenticator, which is DRF's normal multi-scheme behavior.
    """

    session_authentication_class = SessionAuthentication


class StrictClerkSessionAuthentication(BaseAuthentication):
    """
    A supplied Authorization header is authoritative.

    - No Authorization header: Django session with CSRF enforced.
    - ``Authorization: Bearer <token>``: Clerk only. Invalid tokens fail.
    - Any other Authorization value (including an empty or whitespace-only
      header), an empty Bearer token, or Clerk not configured: authentication
      fails. The request never falls through to the session cookie or to a
      later authenticator.

    List it as the only entry in ``DEFAULT_AUTHENTICATION_CLASSES``; any class
    listed after it would only see requests that carried no credentials.
    """

    clerk_authentication_class = ClerkAuthentication
    session_authentication_class = SessionAuthentication

    def __init__(self):
        self.clerk = self.clerk_authentication_class()
        self.session = self.session_authentication_class()

    def authenticate(self, request):
        if "authorization" not in request.headers:
            return self.session.authenticate(request)

        if get_bearer_token(request) is None:
            raise exceptions.AuthenticationFailed(
                "Malformed Authorization header; expected 'Bearer <token>'."
            )

        result = self.clerk.authenticate(request)
        if result is None:
            # A token was supplied, so None means Clerk is not configured
            # (no usable CLERK_SECRET_KEY or CLERK_JWT_KEY).
            raise exceptions.AuthenticationFailed(
                "Clerk bearer authentication is not configured."
            )
        return result

    def authenticate_header(self, request):
        # Makes DRF answer 401 with WWW-Authenticate instead of 403.
        return "Bearer"
