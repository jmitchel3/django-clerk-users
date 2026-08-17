"""
Tests for cache backend failures.

An unavailable cache backend must degrade to a cache miss, never to an HTTP
500 or a spurious 401. Every cache in this package sits in front of an
authoritative source (Clerk or the database), so failing open costs a
re-verification or a re-query and can never make the library accept something
it would otherwise reject.

See https://github.com/jmitchel3/django-clerk-users/issues/32.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory

from django_clerk_users.caching import (
    get_cached_organization,
    get_cached_user,
    get_user_cache_key,
    invalidate_clerk_user_cache,
    invalidate_organization_cache,
    safe_cache_add,
    safe_cache_delete,
    safe_cache_get,
    safe_cache_set,
    set_cached_organization,
    set_cached_user,
)

try:
    import rest_framework  # noqa: F401

    HAS_DRF = True
except ImportError:
    HAS_DRF = False


class CacheDown(Exception):
    """Stand-in for a backend error such as a Redis connection failure."""


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def clerk_user(db):
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_cache_down",
        email="cache-down@example.com",
    )


class TestSafeCacheHelpers:
    """Test the helpers directly."""

    def test_get_returns_value_when_backend_is_healthy(self):
        cache.set("clerk:test", "value")
        assert safe_cache_get("clerk:test") == "value"

    def test_get_returns_default_on_backend_error(self, caplog):
        with (
            patch(
                "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
            ),
            caplog.at_level(logging.WARNING, logger="django_clerk_users.caching"),
        ):
            assert safe_cache_get("clerk:test", "fallback") == "fallback"

        assert "treating as a cache miss" in caplog.text

    def test_set_reports_success_and_failure(self, caplog):
        assert safe_cache_set("clerk:test", "value", timeout=60) is True
        assert cache.get("clerk:test") == "value"

        with (
            patch(
                "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
            ),
            caplog.at_level(logging.WARNING, logger="django_clerk_users.caching"),
        ):
            assert safe_cache_set("clerk:test", "value", timeout=60) is False

        assert "continuing uncached" in caplog.text

    def test_delete_logs_at_error_because_stale_data_survives(self, caplog):
        assert safe_cache_delete("clerk:test") is True

        with (
            patch(
                "django_clerk_users.caching.cache.delete", side_effect=CacheDown("down")
            ),
            caplog.at_level(logging.ERROR, logger="django_clerk_users.caching"),
        ):
            assert safe_cache_delete("clerk:test") is False

        assert "stale data may be served" in caplog.text
        assert caplog.records[-1].levelno == logging.ERROR

    def test_add_returns_default_on_backend_error(self):
        assert safe_cache_add("clerk:test", True, timeout=60) is True
        assert safe_cache_add("clerk:test", True, timeout=60) is False

        with patch(
            "django_clerk_users.caching.cache.add", side_effect=CacheDown("down")
        ):
            assert safe_cache_add("clerk:test", True, timeout=60) is True
            assert (
                safe_cache_add("clerk:test", True, timeout=60, default=False) is False
            )

    def test_traceback_is_attached_only_when_debug_logging_is_on(self, caplog):
        with (
            patch(
                "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
            ),
            caplog.at_level(logging.WARNING, logger="django_clerk_users.caching"),
        ):
            safe_cache_get("clerk:test")
        assert not caplog.records[-1].exc_info

        caplog.clear()
        with (
            patch(
                "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
            ),
            caplog.at_level(logging.DEBUG, logger="django_clerk_users.caching"),
        ):
            safe_cache_get("clerk:test")
        assert caplog.records[-1].exc_info is not None


class TestAuthenticationSurvivesCacheOutage:
    """Test the path that took down authentication entirely."""

    def _request(self, token="valid-token"):
        return RequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {token}")

    def _signed_in(self, payload):
        return SimpleNamespace(is_signed_in=True, payload=payload, reason=None)

    def test_failed_cache_read_falls_back_to_verifying_the_token(self, settings):
        """A raising cache.get must not propagate out as a 500."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        settings.CLERK_SECRET_KEY = "sk_test_cache_down"
        payload = {"sub": "user_cache_down"}

        with (
            patch(
                "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=self._signed_in(payload),
            ) as verify,
        ):
            result = get_clerk_payload_from_request(self._request())

        assert result == payload
        verify.assert_called_once()

    def test_failed_cache_write_still_returns_the_verified_payload(self, settings):
        """A raising cache.set must not become a spurious 401."""
        from django_clerk_users.authentication.utils import (
            get_clerk_payload_from_request,
        )

        settings.CLERK_SECRET_KEY = "sk_test_cache_down"
        payload = {"sub": "user_cache_down"}

        with (
            patch(
                "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=self._signed_in(payload),
            ),
        ):
            result = get_clerk_payload_from_request(self._request())

        assert result == payload

    @pytest.mark.skipif(not HAS_DRF, reason="Django REST Framework not installed")
    def test_drf_authentication_returns_the_user_instead_of_raising(
        self, settings, clerk_user
    ):
        """The reported symptom: DRF's authenticate() let the error become a 500."""
        from django_clerk_users.authentication.drf import ClerkAuthentication

        settings.CLERK_SECRET_KEY = "sk_test_cache_down"
        payload = {"sub": clerk_user.clerk_id}

        with (
            patch(
                "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
            ),
            patch(
                "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
            ),
            patch(
                "django_clerk_users.authentication.utils.authenticate_session_token",
                return_value=self._signed_in(payload),
            ),
        ):
            user, auth = ClerkAuthentication().authenticate(self._request())

        assert user == clerk_user
        assert auth == payload


class TestUserAndOrgCachesSurviveOutage:
    """Test the caching helpers used from the authenticated request path."""

    def test_get_cached_user_falls_back_to_the_database(self, clerk_user):
        with patch(
            "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
        ):
            assert get_cached_user(clerk_user.clerk_id) == clerk_user

    def test_get_cached_user_returns_the_user_when_the_write_fails(self, clerk_user):
        with patch(
            "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
        ):
            assert get_cached_user(clerk_user.clerk_id) == clerk_user

    def test_get_cached_user_returns_none_for_a_missing_user(self, db):
        with patch(
            "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
        ):
            assert get_cached_user("user_does_not_exist") is None

    def test_set_cached_user_does_not_raise(self, clerk_user):
        with patch(
            "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
        ):
            set_cached_user(clerk_user.clerk_id, clerk_user)

    def test_invalidate_user_cache_does_not_raise(self, clerk_user):
        cache.set(get_user_cache_key(clerk_user.clerk_id), clerk_user)
        with patch(
            "django_clerk_users.caching.cache.delete", side_effect=CacheDown("down")
        ):
            invalidate_clerk_user_cache(clerk_user.clerk_id)

    def test_get_cached_organization_falls_back_to_the_database(self, db):
        from django_clerk_users.organizations.models import Organization

        org = Organization.objects.create(
            clerk_id="org_cache_down",
            name="Cache Down Org",
            slug="cache-down-org",
        )

        with patch(
            "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
        ):
            assert get_cached_organization(org.clerk_id) == org

    def test_get_cached_organization_returns_none_for_a_missing_org(self, db):
        with patch(
            "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
        ):
            assert get_cached_organization("org_does_not_exist") is None

    def test_set_and_invalidate_organization_cache_do_not_raise(self, db):
        with patch(
            "django_clerk_users.caching.cache.set", side_effect=CacheDown("down")
        ):
            set_cached_organization("org_cache_down", None)
        with patch(
            "django_clerk_users.caching.cache.delete", side_effect=CacheDown("down")
        ):
            invalidate_organization_cache("org_cache_down")


class TestMiddlewareAndWebhooksSurviveOutage:
    """Test the remaining entry points that reach the cache."""

    def test_organization_middleware_does_not_500(self, db):
        """ClerkOrganizationMiddleware reads the cache with nothing catching it."""
        from django_clerk_users.organizations.middleware import (
            ClerkOrganizationMiddleware,
        )
        from django_clerk_users.organizations.models import (
            Organization,
            OrganizationMember,
        )

        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_org_cache_down",
            email="org-cache-down@example.com",
        )
        org = Organization.objects.create(
            clerk_id="org_mw_cache_down",
            name="Middleware Cache Down",
            slug="middleware-cache-down",
        )
        OrganizationMember.objects.create(
            clerk_membership_id="mem_cache_down",
            organization=org,
            user=user,
        )

        middleware = ClerkOrganizationMiddleware(lambda request: HttpResponse("OK"))
        request = RequestFactory().get("/", HTTP_X_ORGANIZATION_ID=org.clerk_id)
        request.user = user

        with patch(
            "django_clerk_users.caching.cache.get", side_effect=CacheDown("down")
        ):
            response = middleware(request)

        assert response.status_code == 200
        assert request.organization == org

    def test_duplicate_webhook_check_treats_an_outage_as_a_new_event(self):
        """Dropping a webhook because dedup is unavailable is worse than a retry."""
        from django_clerk_users.webhooks.handlers import is_duplicate_webhook

        with patch(
            "django_clerk_users.caching.cache.add", side_effect=CacheDown("down")
        ):
            assert is_duplicate_webhook("user.created", "evt_cache_down") is False
