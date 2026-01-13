"""
Tests for django-clerk-users middleware.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory

from django_clerk_users.middleware.auth import ClerkAuthMiddleware


@pytest.fixture
def request_factory():
    """Create a request factory."""
    return RequestFactory()


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_mid123",
        email="middleware@example.com",
        first_name="Middleware",
        last_name="User",
    )


@pytest.fixture
def inactive_user(db):
    """Create an inactive user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_inactive_mid",
        email="inactive_mid@example.com",
        is_active=False,
    )


@pytest.fixture
def middleware():
    """Create middleware instance."""

    def get_response(request):
        return HttpResponse("OK")

    return ClerkAuthMiddleware(get_response)


def make_request_with_session(request_factory):
    """Create a request with a session."""
    request = request_factory.get("/")
    request.session = SessionStore()
    request.user = AnonymousUser()
    return request


class TestMiddlewareInit:
    """Test middleware initialization."""

    def test_init_stores_get_response(self, middleware):
        """Test that middleware stores get_response callable."""
        assert middleware.get_response is not None
        assert callable(middleware.get_response)


class TestMiddlewareAnonymousUser:
    """Test middleware with anonymous users."""

    def test_no_token_sets_anonymous(self, middleware, request_factory):
        """Test that missing token sets anonymous user."""
        request = make_request_with_session(request_factory)

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=None,
        ):
            middleware.process_request(request)

        assert isinstance(request.user, AnonymousUser)
        assert request.clerk_user is None
        assert request.clerk_payload is None
        assert request.org is None


class TestMiddlewareTokenValidation:
    """Test middleware token validation."""

    def test_invalid_token_sets_anonymous(self, middleware, request_factory):
        """Test that invalid token sets anonymous user."""
        from django_clerk_users.exceptions import ClerkTokenError

        request = make_request_with_session(request_factory)

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            side_effect=ClerkTokenError("Invalid token"),
        ):
            middleware.process_request(request)

        assert isinstance(request.user, AnonymousUser)
        assert request.clerk_user is None

    def test_valid_token_authenticates_user(self, middleware, request_factory, clerk_user):
        """Test that valid token authenticates user."""
        request = make_request_with_session(request_factory)
        payload = {"sub": "user_mid123", "org_id": "org_test"}

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.middleware.auth.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                middleware.process_request(request)

        assert request.user == clerk_user
        assert request.clerk_user == clerk_user
        assert request.org == "org_test"


class TestMiddlewareSessionHandling:
    """Test middleware session handling."""

    def test_creates_session_on_auth(self, middleware, request_factory, clerk_user):
        """Test that session is created on authentication."""
        request = make_request_with_session(request_factory)
        payload = {"sub": "user_mid123", "org_id": None}

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.middleware.auth.get_or_create_user_from_payload",
                return_value=(clerk_user, False),
            ):
                middleware.process_request(request)

        # Check session data
        assert request.session.get("_auth_user_id") == str(clerk_user.pk)
        assert "django_clerk_users.authentication.ClerkBackend" in request.session.get(
            "_auth_user_backend", ""
        )

    def test_valid_session_skips_token_validation(self, middleware, request_factory, clerk_user):
        """Test that valid session skips token validation."""
        request = make_request_with_session(request_factory)

        # Simulate existing session
        request.user = clerk_user
        request.session["_auth_user_id"] = str(clerk_user.pk)
        request.session["last_clerk_check"] = int(time.time())
        request.session["clerk_org_id"] = "org_123"

        # Should not call get_clerk_payload_from_request for validation
        # (within revalidation window)
        middleware.process_request(request)

        assert request.clerk_user == clerk_user
        assert request.org == "org_123"


class TestMiddlewareInactiveUser:
    """Test middleware with inactive users."""

    def test_inactive_user_sets_anonymous(self, middleware, request_factory, inactive_user):
        """Test that inactive user is treated as anonymous."""
        request = make_request_with_session(request_factory)
        payload = {"sub": "user_inactive_mid"}

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.middleware.auth.get_or_create_user_from_payload",
                return_value=(inactive_user, False),
            ):
                middleware.process_request(request)

        assert isinstance(request.user, AnonymousUser)
        assert request.clerk_user is None


class TestMiddlewareUserCreation:
    """Test middleware user creation."""

    def test_creates_new_user(self, middleware, request_factory, db):
        """Test that middleware creates new user."""
        User = get_user_model()
        new_user = User.objects.create_user(
            clerk_id="user_new123",
            email="new@example.com",
        )

        request = make_request_with_session(request_factory)
        payload = {"sub": "user_new123"}

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.middleware.auth.get_or_create_user_from_payload",
                return_value=(new_user, True),
            ):
                middleware.process_request(request)

        assert request.user == new_user
        assert request.clerk_user == new_user


class TestMiddlewareErrorHandling:
    """Test middleware error handling."""

    def test_auth_error_sets_anonymous(self, middleware, request_factory):
        """Test that authentication error sets anonymous user."""
        from django_clerk_users.exceptions import ClerkAuthenticationError

        request = make_request_with_session(request_factory)
        payload = {"sub": "user_error"}

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.middleware.auth.get_or_create_user_from_payload",
                side_effect=ClerkAuthenticationError("Auth failed"),
            ):
                middleware.process_request(request)

        assert isinstance(request.user, AnonymousUser)
        assert request.clerk_user is None

    def test_debug_mode_raises_errors(self, request_factory, clerk_user):
        """Test that debug mode raises unexpected errors."""

        def get_response(request):
            return HttpResponse("OK")

        middleware = ClerkAuthMiddleware(get_response)
        middleware.debug = True

        request = make_request_with_session(request_factory)
        payload = {"sub": "user_mid123"}

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=payload,
        ):
            with patch(
                "django_clerk_users.middleware.auth.get_or_create_user_from_payload",
                side_effect=RuntimeError("Unexpected error"),
            ):
                with pytest.raises(RuntimeError, match="Unexpected error"):
                    middleware.process_request(request)


class TestMiddlewareRevalidation:
    """Test session revalidation."""

    def test_revalidation_on_expired_check(self, middleware, request_factory, clerk_user):
        """Test that expired session triggers revalidation."""
        request = make_request_with_session(request_factory)

        # Simulate existing session with expired check
        request.user = clerk_user
        request.session["_auth_user_id"] = str(clerk_user.pk)
        request.session["last_clerk_check"] = int(time.time()) - 400  # 400 seconds ago

        # Mock token validation for revalidation
        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value={"sub": "user_mid123", "org_id": "org_new"},
        ):
            middleware.process_request(request)

        # Should update org from new payload
        assert request.org == "org_new"


class TestMiddlewareCall:
    """Test middleware __call__ method."""

    def test_call_returns_response(self, middleware, request_factory):
        """Test that __call__ returns response."""
        request = make_request_with_session(request_factory)

        with patch(
            "django_clerk_users.middleware.auth.get_clerk_payload_from_request",
            return_value=None,
        ):
            response = middleware(request)

        assert response.status_code == 200
        assert response.content == b"OK"
