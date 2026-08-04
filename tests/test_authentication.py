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

    def test_near_expiring_payload_is_not_cached(self, settings):
        """Test that payloads near expiry are returned but not cached."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        # The default test secret is a documented placeholder that reads as
        # "unconfigured", which short-circuits verification before it starts.
        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_soon")
        now = int(time.time())
        payload = {"sub": "user_auth123", "exp": now + 30}
        request_state = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
            reason=None,
        )

        with (
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=request_state,
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
        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        settings.CLERK_CACHE_TIMEOUT = 300
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_later")
        now = int(time.time())
        payload = {"sub": "user_auth123", "exp": now + 120}
        request_state = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
            reason=None,
        )

        with (
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=request_state,
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
        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        settings.CLERK_CACHE_TIMEOUT = "not-an-int"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_later")
        payload = {"sub": "user_auth123"}
        request_state = SimpleNamespace(
            is_signed_in=True,
            payload=payload,
            reason=None,
        )

        with (
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=request_state,
            ),
            patch("django_clerk_users.authentication.utils.cache.set") as cache_set,
        ):
            result = get_clerk_payload_from_request(request)

        assert result == payload
        cache_set.assert_called_once()
        assert cache_set.call_args.kwargs["timeout"] == 300

    def test_empty_allowlist_is_passed_as_none_not_empty_list(self, settings):
        """Carried over from the AuthenticateRequestOptions fix.

        The azp check runs only when authorized_parties is not None, so an
        empty list would be an allowlist matching nothing and would reject
        every token. The verification engine changed underneath this, but the
        [] vs None distinction it guards did not.
        """
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        settings.CLERK_FRONTEND_HOSTS = []
        settings.CLERK_AUTH_PARTIES = []
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_no_azp")
        payload = {"sub": "user_auth123"}
        request_state = SimpleNamespace(is_signed_in=True, payload=payload, reason=None)

        with patch(
            "django_clerk_users.authentication.utils.authenticate_session_token",
            return_value=request_state,
        ) as verify:
            assert get_clerk_payload_from_request(request) == payload

        assert verify.call_args.kwargs["authorized_parties"] is None

    def test_configured_authorized_parties_reach_verification(self, settings):
        """A configured allowlist is forwarded unchanged."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        settings.CLERK_AUTH_PARTIES = ["https://app.example.com"]
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token_with_azp")
        payload = {"sub": "user_auth123"}
        request_state = SimpleNamespace(is_signed_in=True, payload=payload, reason=None)

        with patch(
            "django_clerk_users.authentication.utils.authenticate_session_token",
            return_value=request_state,
        ) as verify:
            assert get_clerk_payload_from_request(request) == payload

        assert verify.call_args.kwargs["authorized_parties"] == [
            "https://app.example.com"
        ]

    def test_unsigned_request_state_raises_for_present_bearer_token(self, settings):
        """Test that an invalid bearer token is not treated as anonymous."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        cache.clear()
        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer invalid_token")
        request_state = SimpleNamespace(
            is_signed_in=False,
            reason="token expired",
            payload=None,
        )

        with patch(
            "django_clerk_users.authentication.utils.authenticate_session_token",
            return_value=request_state,
        ):
            with pytest.raises(ClerkTokenError, match="token expired"):
                get_clerk_payload_from_request(request)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, []),
            (b"https://app.example.com", ["https://app.example.com"]),
            (b"\xff", []),
            (object(), []),
        ],
    )
    def test_auth_parties_normalize_top_level_setting_values(
        self, settings, value, expected
    ):
        from django_clerk_users.authentication.utils import _get_auth_parties

        settings.CLERK_AUTH_PARTIES = value

        assert _get_auth_parties() == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (b"  public-key  ", "public-key"),
            (b"\xff", None),
            (123, None),
            ("   ", None),
        ],
    )
    def test_jwt_key_normalization(self, settings, value, expected):
        from django_clerk_users.authentication.utils import _get_jwt_key

        settings.CLERK_JWT_KEY = value

        assert _get_jwt_key() == expected

    def test_nonpositive_cache_timeout_disables_payload_caching(self, settings):
        from django_clerk_users.authentication.utils import _payload_cache_timeout

        settings.CLERK_CACHE_TIMEOUT = 0

        assert _payload_cache_timeout({"exp": 9999999999}, now=1) == 0

    def test_invalid_exp_uses_configured_cache_timeout(self, settings):
        from django_clerk_users.authentication.utils import _payload_cache_timeout

        settings.CLERK_CACHE_TIMEOUT = 123

        assert _payload_cache_timeout({"exp": "invalid"}, now=1) == 123

    def test_bearer_token_accepts_bytes_header(self):
        from django_clerk_users.authentication.utils import get_bearer_token

        request = RequestFactory().get("/")
        request.headers = {"Authorization": b"Bearer bytes-token"}

        assert get_bearer_token(request) == "bytes-token"

    def test_missing_bearer_token_returns_none(self):
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        assert get_clerk_payload_from_request(RequestFactory().get("/")) is None

    def test_cached_payload_skips_verification(self):
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer cached")
        payload = {"sub": "user_cached"}

        with (
            patch(
                "django_clerk_users.authentication.utils.cache.get",
                return_value=payload,
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token"
            ) as verify,
        ):
            assert get_clerk_payload_from_request(request) == payload

        verify.assert_not_called()

    def test_unconfigured_clerk_returns_none_for_present_token(self, settings):
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        settings.CLERK_SECRET_KEY = ""
        settings.CLERK_JWT_KEY = None
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token")

        with patch(
            "django_clerk_users.authentication.utils.cache.get", return_value=None
        ):
            assert get_clerk_payload_from_request(request) is None

    @pytest.mark.parametrize(
        "request_state",
        [
            SimpleNamespace(is_signed_in=False, reason=None, message="bad signature"),
            SimpleNamespace(is_signed_in=False, reason=None, message=None),
        ],
    )
    def test_unsigned_request_uses_message_or_default_reason(
        self, settings, request_state
    ):
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer invalid")

        with (
            patch(
                "django_clerk_users.authentication.utils.cache.get", return_value=None
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=request_state,
            ),
        ):
            with pytest.raises(ClerkTokenError, match="Token validation failed"):
                get_clerk_payload_from_request(request)

    def test_signed_in_request_without_payload_raises(self, settings):
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer empty")
        request_state = SimpleNamespace(is_signed_in=True, payload=None)

        with (
            patch(
                "django_clerk_users.authentication.utils.cache.get", return_value=None
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=request_state,
            ),
        ):
            with pytest.raises(ClerkTokenError, match="no payload"):
                get_clerk_payload_from_request(request)

    def test_verification_errors_are_wrapped_as_token_errors(self, settings):
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        settings.CLERK_SECRET_KEY = "sk_test_unit_auth_secret"
        request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer broken")

        with (
            patch(
                "django_clerk_users.authentication.utils.cache.get", return_value=None
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                side_effect=RuntimeError("SDK unavailable"),
            ),
        ):
            with pytest.raises(ClerkTokenError, match="SDK unavailable"):
                get_clerk_payload_from_request(request)


class TestGetOrCreateUserFromPayload:
    def test_missing_subject_is_rejected(self, db):
        from django_clerk_users.authentication.utils import (
            get_or_create_user_from_payload,
        )
        from django_clerk_users.exceptions import ClerkAuthenticationError

        with pytest.raises(ClerkAuthenticationError, match="missing 'sub'"):
            get_or_create_user_from_payload({})

    def test_existing_user_is_returned_without_api_call(self, clerk_user):
        from django_clerk_users.authentication.utils import (
            get_or_create_user_from_payload,
        )

        with patch(
            "django_clerk_users.utils.update_or_create_clerk_user"
        ) as update_user:
            assert get_or_create_user_from_payload({"sub": clerk_user.clerk_id}) == (
                clerk_user,
                False,
            )

        update_user.assert_not_called()

    def test_missing_user_is_created_from_clerk(self, db):
        from django_clerk_users.authentication.utils import (
            get_or_create_user_from_payload,
        )

        created_user = MagicMock()
        with patch(
            "django_clerk_users.utils.update_or_create_clerk_user",
            return_value=(created_user, True),
        ) as update_user:
            assert get_or_create_user_from_payload({"sub": "user_new"}) == (
                created_user,
                True,
            )

        update_user.assert_called_once_with("user_new")

    def test_clerk_creation_error_is_wrapped(self, db):
        from django_clerk_users.authentication.utils import (
            get_or_create_user_from_payload,
        )
        from django_clerk_users.exceptions import ClerkAuthenticationError

        with patch(
            "django_clerk_users.utils.update_or_create_clerk_user",
            side_effect=RuntimeError("API unavailable"),
        ):
            with pytest.raises(ClerkAuthenticationError, match="API unavailable"):
                get_or_create_user_from_payload({"sub": "user_new"})


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
