"""
Tests for django-clerk-users authentication backend.
"""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory

from django_clerk_users.authentication.backends import ClerkBackend
from django_clerk_users.exceptions import ClerkTokenError


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_auth123",
        email="auth@example.com",
        first_name="Auth",
        last_name="User",
    )


@pytest.fixture
def inactive_user(db):
    """Create an inactive user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_inactive",
        email="inactive@example.com",
        is_active=False,
    )


@pytest.fixture
def backend():
    """Create a ClerkBackend instance."""
    return ClerkBackend()


class TestClerkBackend:
    """Test ClerkBackend authentication."""

    def test_authenticate_with_clerk_id(self, backend, clerk_user):
        """Test authentication with valid clerk_id."""
        user = backend.authenticate(request=None, clerk_id="user_auth123")
        assert user == clerk_user

    def test_authenticate_without_clerk_id(self, backend, clerk_user):
        """Test authentication without clerk_id returns None."""
        user = backend.authenticate(request=None)
        assert user is None

    def test_authenticate_with_empty_clerk_id(self, backend, clerk_user):
        """Test authentication with empty clerk_id returns None."""
        user = backend.authenticate(request=None, clerk_id="")
        assert user is None

    def test_authenticate_nonexistent_user(self, backend, db):
        """Test authentication with nonexistent clerk_id returns None."""
        user = backend.authenticate(request=None, clerk_id="nonexistent")
        assert user is None

    def test_authenticate_inactive_user(self, backend, inactive_user):
        """Test authentication with inactive user returns None."""
        user = backend.authenticate(request=None, clerk_id="user_inactive")
        assert user is None

    def test_get_user_by_pk(self, backend, clerk_user):
        """Test getting user by primary key."""
        user = backend.get_user(clerk_user.pk)
        assert user == clerk_user

    def test_get_user_nonexistent(self, backend, db):
        """Test getting nonexistent user returns None."""
        user = backend.get_user(99999)
        assert user is None

    def test_get_user_inactive(self, backend, inactive_user):
        """Test getting inactive user returns None."""
        user = backend.get_user(inactive_user.pk)
        assert user is None


class TestBearerToken:
    """Test bearer token extraction."""

    def test_get_bearer_token_valid(self):
        """Test extracting valid bearer token."""
        from django_clerk_users.authentication.utils import get_bearer_token

        request = RequestFactory().get("/")
        request.headers = {"Authorization": "Bearer test_token_123"}

        token = get_bearer_token(request)
        assert token == "test_token_123"

    def test_get_bearer_token_is_case_insensitive(self):
        """Test extracting bearer tokens with lower-case auth schemes."""
        from django_clerk_users.authentication.utils import get_bearer_token

        request = RequestFactory().get("/", HTTP_AUTHORIZATION="bearer test_token_123")

        token = get_bearer_token(request)
        assert token == "test_token_123"

    def test_get_bearer_token_missing(self):
        """Test missing authorization header."""
        from django_clerk_users.authentication.utils import get_bearer_token

        request = RequestFactory().get("/")
        token = get_bearer_token(request)
        assert token is None

    def test_get_bearer_token_wrong_scheme(self):
        """Test non-bearer authorization header."""
        from django_clerk_users.authentication.utils import get_bearer_token

        request = RequestFactory().get("/")
        request.headers = {"Authorization": "Basic abc123"}

        token = get_bearer_token(request)
        assert token is None


class TestClerkPayloadFromRequest:
    """Test Clerk request payload validation behavior."""

    def test_auth_parties_accept_comma_separated_setting(self, settings):
        """Test authorized parties can be configured from comma-separated env text."""
        from django_clerk_users.authentication.utils import _get_auth_parties

        settings.CLERK_AUTH_PARTIES = (
            "https://app.example.com, https://admin.example.com,, "
        )

        assert _get_auth_parties() == [
            "https://app.example.com",
            "https://admin.example.com",
        ]

    def test_auth_parties_accept_iterables(self, settings):
        """Test authorized parties normalize iterable settings."""
        from django_clerk_users.authentication.utils import _get_auth_parties

        settings.CLERK_AUTH_PARTIES = (
            "https://app.example.com",
            b"https://admin.example.com",
            "",
            None,
        )

        assert _get_auth_parties() == [
            "https://app.example.com",
            "https://admin.example.com",
        ]

    def test_auth_parties_skip_invalid_byte_items(self, settings):
        """Test invalid bytes in authorized parties do not crash normalization."""
        from django_clerk_users.authentication.utils import _get_auth_parties

        settings.CLERK_AUTH_PARTIES = (
            "https://app.example.com",
            b"\xff",
        )

        assert _get_auth_parties() == ["https://app.example.com"]

    def test_auth_parties_fall_back_to_frontend_hosts(self, settings):
        """Test CLERK_FRONTEND_HOSTS can drive authorized parties."""
        from django_clerk_users.authentication.utils import _get_auth_parties

        if hasattr(settings, "CLERK_AUTH_PARTIES"):
            delattr(settings, "CLERK_AUTH_PARTIES")
        settings.CLERK_FRONTEND_HOSTS = "https://app.example.com"

        assert _get_auth_parties() == ["https://app.example.com"]

    def test_near_expiring_payload_is_not_cached(self):
        """Test that payloads near expiry are returned but not cached."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_soon")
        now = int(time.time())
        payload = {"sub": "user_auth123", "exp": now + 30}
        clerk = MagicMock()
        clerk.authenticate_request.return_value = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
        )

        with (
            patch(
                "django_clerk_users.authentication.utils.get_clerk_client",
                return_value=clerk,
            ),
            patch("django_clerk_users.authentication.utils.cache.set") as cache_set,
        ):
            result = get_clerk_payload_from_request(request)

        assert result == payload
        cache_set.assert_not_called()

    def test_payload_cache_timeout_stops_before_expiry(self, settings):
        """Test payload cache timeout stops one minute before token expiry."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_CACHE_TIMEOUT = 300
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_later")
        now = int(time.time())
        payload = {"sub": "user_auth123", "exp": now + 120}
        clerk = MagicMock()
        clerk.authenticate_request.return_value = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
        )

        with (
            patch(
                "django_clerk_users.authentication.utils.get_clerk_client",
                return_value=clerk,
            ),
            patch("django_clerk_users.authentication.utils.cache.set") as cache_set,
        ):
            result = get_clerk_payload_from_request(request)

        assert result == payload
        cache_set.assert_called_once()
        assert cache_set.call_args.kwargs["timeout"] == 60

    def test_invalid_cache_timeout_falls_back_to_default(self, settings):
        """Test invalid CLERK_CACHE_TIMEOUT does not break token validation."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_CACHE_TIMEOUT = "not-an-int"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_later")
        payload = {"sub": "user_auth123"}
        clerk = MagicMock()
        clerk.authenticate_request.return_value = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
        )

        with (
            patch(
                "django_clerk_users.authentication.utils.get_clerk_client",
                return_value=clerk,
            ),
            patch("django_clerk_users.authentication.utils.cache.set") as cache_set,
        ):
            result = get_clerk_payload_from_request(request)

        assert result == payload
        cache_set.assert_called_once()
        assert cache_set.call_args.kwargs["timeout"] == 300

    def test_options_are_built_when_no_authorized_parties_configured(self, settings):
        """Test verification still passes an options object with an empty allowlist.

        The SDK reads ``options.secret_key`` unconditionally, so passing
        ``options=None`` raises an AttributeError that surfaces as a generic
        token failure.
        """
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_FRONTEND_HOSTS = []
        settings.CLERK_AUTH_PARTIES = []
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_no_azp")
        payload = {"sub": "user_auth123"}
        clerk = MagicMock()
        clerk.authenticate_request.return_value = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
        )

        with patch(
            "django_clerk_users.authentication.utils.get_clerk_client",
            return_value=clerk,
        ):
            result = get_clerk_payload_from_request(request)

        assert result == payload
        options = clerk.authenticate_request.call_args.kwargs["options"]
        assert options is not None
        # None, not [], so the SDK skips the azp check instead of treating it
        # as an allowlist that matches nothing.
        assert options.authorized_parties is None

    def test_configured_authorized_parties_reach_the_sdk(self, settings):
        """Test a configured allowlist is forwarded to the SDK options."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_AUTH_PARTIES = ["https://app.example.com"]
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_with_azp")
        payload = {"sub": "user_auth123"}
        clerk = MagicMock()
        clerk.authenticate_request.return_value = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
        )

        with patch(
            "django_clerk_users.authentication.utils.get_clerk_client",
            return_value=clerk,
        ):
            result = get_clerk_payload_from_request(request)

        assert result == payload
        options = clerk.authenticate_request.call_args.kwargs["options"]
        assert options.authorized_parties == ["https://app.example.com"]

    def test_empty_allowlist_does_not_reject_a_valid_token(self, settings):
        """Test the empty-allowlist path against the real SDK verification rule.

        Guards the ``[]`` vs ``None`` distinction: the SDK only skips the azp
        check when ``authorized_parties is None``. Passing ``[]`` would reject
        every token.
        """
        from clerk_backend_api.security.types import AuthenticateRequestOptions

        from django_clerk_users.authentication.utils import _get_auth_parties

        settings.CLERK_FRONTEND_HOSTS = []
        settings.CLERK_AUTH_PARTIES = []

        options = AuthenticateRequestOptions(
            authorized_parties=_get_auth_parties() or None
        )

        assert options.authorized_parties is None

    def test_unsigned_request_state_raises_for_present_bearer_token(self):
        """Test that an invalid bearer token is not treated as anonymous."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer invalid_token")
        clerk = MagicMock()
        clerk.authenticate_request.return_value = SimpleNamespace(
            is_signed_in=False,
            message="token expired",
            payload=None,
        )

        with patch(
            "django_clerk_users.authentication.utils.get_clerk_client",
            return_value=clerk,
        ):
            with pytest.raises(ClerkTokenError, match="token expired"):
                get_clerk_payload_from_request(request)


class TestClerkClientConfiguration:
    """Test Clerk SDK client configuration handling."""

    def test_placeholder_secret_key_is_treated_as_unconfigured(self, settings):
        """Test that documented placeholder secrets do not create SDK clients."""
        from django_clerk_users.client import get_clerk_client
        from django_clerk_users.exceptions import ClerkConfigurationError

        settings.CLERK_SECRET_KEY = "sk_test_mock_secret_key"
        get_clerk_client.cache_clear()

        try:
            with pytest.raises(ClerkConfigurationError):
                get_clerk_client()
        finally:
            get_clerk_client.cache_clear()

    def test_invalid_secret_key_prefix_is_treated_as_unconfigured(self, settings):
        """Test invalid-looking secret keys do not create SDK clients."""
        from django_clerk_users.client import get_clerk_client
        from django_clerk_users.exceptions import ClerkConfigurationError

        settings.CLERK_SECRET_KEY = "not-a-clerk-secret"
        get_clerk_client.cache_clear()

        try:
            with pytest.raises(ClerkConfigurationError):
                get_clerk_client()
        finally:
            get_clerk_client.cache_clear()

    def test_invalid_secret_key_bytes_are_treated_as_unconfigured(self, settings):
        """Test undecodable byte-string secret keys do not create SDK clients."""
        from django_clerk_users.client import get_clerk_client
        from django_clerk_users.exceptions import ClerkConfigurationError

        settings.CLERK_SECRET_KEY = b"\xff"
        get_clerk_client.cache_clear()

        try:
            with pytest.raises(ClerkConfigurationError):
                get_clerk_client()
        finally:
            get_clerk_client.cache_clear()


class TestGetUserFromClerkId:
    """Test get_user_from_clerk_id utility."""

    def test_get_existing_user(self, clerk_user):
        """Test getting an existing user."""
        from django_clerk_users.authentication.utils import get_user_from_clerk_id

        user = get_user_from_clerk_id("user_auth123")
        assert user == clerk_user

    def test_get_nonexistent_user(self, db):
        """Test getting a nonexistent user."""
        from django_clerk_users.authentication.utils import get_user_from_clerk_id

        user = get_user_from_clerk_id("nonexistent")
        assert user is None
