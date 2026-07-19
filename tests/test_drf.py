"""
Tests for django-clerk-users DRF authentication.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

# Check if DRF is available
try:
    import rest_framework  # noqa: F401

    HAS_DRF = True
except ImportError:
    HAS_DRF = False

pytestmark = pytest.mark.skipif(
    not HAS_DRF, reason="Django REST Framework not installed"
)


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_drf123",
        email="drf@example.com",
        first_name="DRF",
        last_name="User",
    )


@pytest.fixture
def inactive_user(db):
    """Create an inactive user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_drf_inactive",
        email="drf_inactive@example.com",
        is_active=False,
    )


@pytest.fixture
def request_factory():
    """Create a request factory."""
    return RequestFactory()


class TestClerkAuthenticationImport:
    """Test ClerkAuthentication import handling."""

    def test_import_from_drf_module(self):
        """Test that ClerkAuthentication can be imported."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        assert ClerkAuthentication is not None

    def test_import_from_authentication_package(self):
        """Test that ClerkAuthentication can be imported from authentication package."""
        from django_clerk_users.authentication import ClerkAuthentication

        assert ClerkAuthentication is not None


class TestClerkAuthentication:
    """Test ClerkAuthentication class."""

    def test_authenticate_no_token(self, request_factory):
        """Test authentication with no token returns None."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        request = request_factory.get("/")

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=None,
        ):
            result = auth.authenticate(request)

        assert result is None

    def test_authenticate_valid_token(self, request_factory, clerk_user):
        """Test authentication with valid token."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        request = request_factory.get("/")
        payload = {"sub": "user_drf123"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                result = auth.authenticate(request)

        assert result is not None
        user, auth_payload = result
        assert user == clerk_user
        assert auth_payload == payload

    def test_authenticate_attaches_payload_to_request(
        self, request_factory, clerk_user
    ):
        """Test that authentication attaches payload to request."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        request = request_factory.get("/")
        payload = {"sub": "user_drf123", "org_id": "org_test"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                auth.authenticate(request)

        assert hasattr(request, "clerk_payload")
        assert request.clerk_payload == payload

    def test_authenticate_exposes_active_org(self, request_factory, clerk_user):
        """The active Clerk org id from the token is exposed as request.org,
        mirroring what ClerkAuthMiddleware does on the WSGI path."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        request = request_factory.get("/")
        payload = {"sub": "user_drf123", "org_id": "org_test"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                auth.authenticate(request)

        assert request.org == "org_test"

    def test_authenticate_org_none_when_absent(self, request_factory, clerk_user):
        """request.org is None when the token carries no org_id."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        request = request_factory.get("/")
        payload = {"sub": "user_drf123"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                auth.authenticate(request)

        assert request.org is None

    def test_authenticate_exposes_org_on_underlying_request(
        self, request_factory, clerk_user
    ):
        """Given a DRF Request wrapper, org is also set on the underlying
        Django HttpRequest so middleware / non-DRF consumers can read it."""
        from rest_framework.request import Request

        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        drf_request = Request(request_factory.get("/"))
        payload = {"sub": "user_drf123", "org_id": "org_wrap"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                auth.authenticate(drf_request)

        assert drf_request.org == "org_wrap"
        assert drf_request._request.org == "org_wrap"

    def test_authenticate_invalid_token_raises(self, request_factory):
        """Test that invalid token raises AuthenticationFailed."""
        from django_clerk_users.authentication.drf import ClerkAuthentication
        from django_clerk_users.exceptions import ClerkTokenError
        from rest_framework.exceptions import AuthenticationFailed

        auth = ClerkAuthentication()
        request = request_factory.get("/")

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            side_effect=ClerkTokenError("Invalid token"),
        ):
            with pytest.raises(AuthenticationFailed):
                auth.authenticate(request)

    def test_authenticate_user_creation_fails_raises(self, request_factory):
        """Test that user creation failure raises AuthenticationFailed."""
        from django_clerk_users.authentication.drf import ClerkAuthentication
        from django_clerk_users.exceptions import ClerkAuthenticationError
        from rest_framework.exceptions import AuthenticationFailed

        auth = ClerkAuthentication()
        request = request_factory.get("/")
        payload = {"sub": "user_new"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                side_effect=ClerkAuthenticationError("Creation failed"),
            ):
                with pytest.raises(AuthenticationFailed):
                    auth.authenticate(request)

    def test_authenticate_inactive_user_raises(self, request_factory, inactive_user):
        """Test that inactive user raises AuthenticationFailed."""
        from django_clerk_users.authentication.drf import ClerkAuthentication
        from rest_framework.exceptions import AuthenticationFailed

        auth = ClerkAuthentication()
        request = request_factory.get("/")
        payload = {"sub": "user_drf_inactive"}

        with patch(
            "django_clerk_users.authentication.drf.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.authentication.drf.get_or_create_user_from_payload",
                return_value=(inactive_user, False),
            ):
                with pytest.raises(AuthenticationFailed, match="inactive"):
                    auth.authenticate(request)

    def test_authenticate_header(self, request_factory):
        """Test authenticate_header returns Bearer."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        auth = ClerkAuthentication()
        request = request_factory.get("/")

        header = auth.authenticate_header(request)

        assert header == "Bearer"
