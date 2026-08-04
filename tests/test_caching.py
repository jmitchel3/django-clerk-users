"""
Tests for django-clerk-users caching utilities.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from django_clerk_users.caching import (
    ORG_CACHE_PREFIX,
    USER_CACHE_PREFIX,
    _get_org_cache_timeout,
    _get_user_cache_timeout,
    get_cached_organization,
    get_cached_user,
    get_org_cache_key,
    get_user_cache_key,
    invalidate_clerk_user_cache,
    invalidate_organization_cache,
    set_cached_organization,
    set_cached_user,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_cache123",
        email="cache@example.com",
    )


class TestCacheKeys:
    """Test cache key generation."""

    def test_user_cache_key(self):
        """Test user cache key format."""
        key = get_user_cache_key("user_123")
        assert key == f"{USER_CACHE_PREFIX}user_123"

    def test_org_cache_key(self):
        """Test organization cache key format."""
        key = get_org_cache_key("org_456")
        assert key == f"{ORG_CACHE_PREFIX}org_456"

    def test_invalid_timeouts_fall_back_and_log(self, settings, caplog):
        settings.CLERK_CACHE_TIMEOUT = "invalid"
        settings.CLERK_ORG_CACHE_TIMEOUT = None

        with caplog.at_level("WARNING"):
            assert _get_user_cache_timeout() == 300
            assert _get_org_cache_timeout() == 900

        assert "Invalid CLERK_CACHE_TIMEOUT" in caplog.text
        assert "Invalid CLERK_ORG_CACHE_TIMEOUT" in caplog.text


class TestUserCaching:
    """Test user caching functions."""

    def test_get_cached_user_from_db(self, clerk_user):
        """Test getting user when not in cache (fetches from DB)."""
        user = get_cached_user("user_cache123", query_db=True)
        assert user == clerk_user

    def test_get_cached_user_from_cache(self, clerk_user):
        """Test getting user from cache after first fetch."""
        # First fetch populates cache
        get_cached_user("user_cache123", query_db=True)

        # Second fetch should use cache
        user = get_cached_user("user_cache123", query_db=False)
        assert user == clerk_user

    def test_get_cached_user_not_found(self, db):
        """Test getting nonexistent user caches False."""
        user = get_cached_user("nonexistent", query_db=True)
        assert user is None

        # Check that "not found" is cached
        cache_key = get_user_cache_key("nonexistent")
        assert cache.get(cache_key) is False

    def test_get_cached_user_empty_clerk_id(self):
        """Test getting user with empty clerk_id."""
        user = get_cached_user("", query_db=True)
        assert user is None

    def test_get_cached_user_none_clerk_id(self):
        """Test getting user with None clerk_id."""
        user = get_cached_user(None, query_db=True)
        assert user is None

    def test_get_cached_user_no_db_query(self, clerk_user):
        """Test getting user without DB query when not cached."""
        user = get_cached_user("user_cache123", query_db=False)
        assert user is None  # Not in cache yet

    def test_get_cached_user_inactive(self, db):
        """Test that inactive users are not cached."""
        User = get_user_model()
        User.objects.create_user(
            clerk_id="user_inactive",
            email="inactive@example.com",
            is_active=False,
        )

        user = get_cached_user("user_inactive", query_db=True)
        assert user is None

    def test_set_cached_user(self, clerk_user):
        """Test setting user in cache."""
        set_cached_user("user_test", clerk_user)

        cache_key = get_user_cache_key("user_test")
        assert cache.get(cache_key) == clerk_user

    def test_set_cached_user_none(self):
        """Test setting None user caches False."""
        set_cached_user("user_none", None)

        cache_key = get_user_cache_key("user_none")
        assert cache.get(cache_key) is False

    def test_set_cached_user_uses_runtime_timeout(self, clerk_user, settings):
        """Test CLERK_CACHE_TIMEOUT is read when caching."""
        settings.CLERK_CACHE_TIMEOUT = "17"

        with patch("django_clerk_users.caching.cache.set") as cache_set:
            set_cached_user("user_test", clerk_user)

        cache_set.assert_called_once_with(
            get_user_cache_key("user_test"),
            clerk_user,
            timeout=17,
        )

    def test_invalidate_user_cache(self, clerk_user):
        """Test invalidating user cache."""
        # Populate cache
        set_cached_user("user_cache123", clerk_user)

        # Verify it's cached
        cache_key = get_user_cache_key("user_cache123")
        assert cache.get(cache_key) is not None

        # Invalidate
        invalidate_clerk_user_cache("user_cache123")

        # Verify it's gone
        assert cache.get(cache_key) is None


class TestOrganizationCaching:
    """Test organization caching functions."""

    def test_get_cached_organization_from_db(self, db):
        """Test getting an organization when not in cache fetches from DB."""
        from django_clerk_users.organizations.models import Organization

        organization = Organization.objects.create(
            clerk_id="org_cache",
            name="Cached Org",
            slug="cached-org",
        )

        assert get_cached_organization("org_cache") == organization

    @pytest.mark.parametrize("clerk_id", ["", None])
    def test_get_cached_organization_rejects_empty_ids(self, clerk_id):
        assert get_cached_organization(clerk_id) is None

    def test_get_cached_organization_can_skip_database(self):
        assert get_cached_organization("org_uncached", query_db=False) is None

    def test_get_cached_organization_returns_positive_cache_hit(self):
        cached = {"id": "org_cached"}
        cache.set(get_org_cache_key("org_cached"), cached)

        assert get_cached_organization("org_cached", query_db=False) == cached

    def test_get_cached_organization_returns_none_for_negative_cache_hit(self):
        cache.set(get_org_cache_key("org_missing"), False)

        assert get_cached_organization("org_missing", query_db=False) is None

    def test_get_cached_organization_not_found(self, db):
        """Test missing organizations are cached as False."""
        organization = get_cached_organization("org_missing")

        assert organization is None
        assert cache.get(get_org_cache_key("org_missing")) is False

    def test_get_cached_organization_propagates_unexpected_db_errors(self, db):
        """Test database failures are not hidden as cache misses."""
        with patch(
            "django_clerk_users.organizations.models.Organization.objects.get",
            side_effect=RuntimeError("database unavailable"),
        ):
            with pytest.raises(RuntimeError, match="database unavailable"):
                get_cached_organization("org_error")

    def test_set_cached_organization_uses_runtime_timeout(self, settings):
        """Test CLERK_ORG_CACHE_TIMEOUT is read when caching."""
        settings.CLERK_ORG_CACHE_TIMEOUT = "23"

        with patch("django_clerk_users.caching.cache.set") as cache_set:
            set_cached_organization("org_test", None)

        cache_set.assert_called_once_with(
            get_org_cache_key("org_test"),
            False,
            timeout=23,
        )

    def test_set_cached_organization_preserves_an_object(self):
        organization = {"id": "org_cached"}

        set_cached_organization("org_cached", organization)

        assert cache.get(get_org_cache_key("org_cached")) == organization

    def test_invalidate_organization_cache(self):
        """Test invalidating organization cache."""
        # Manually set something in cache
        cache_key = get_org_cache_key("org_123")
        cache.set(cache_key, {"name": "Test Org"})

        # Verify it's cached
        assert cache.get(cache_key) is not None

        # Invalidate
        invalidate_organization_cache("org_123")

        # Verify it's gone
        assert cache.get(cache_key) is None


class TestCachedNotFound:
    """Test caching of 'not found' results."""

    def test_cached_false_returns_none(self, db):
        """Test that cached False returns None."""
        # Cache a "not found" result
        cache_key = get_user_cache_key("missing_user")
        cache.set(cache_key, False)

        # Should return None (not False)
        user = get_cached_user("missing_user", query_db=False)
        assert user is None

    def test_cache_miss_vs_not_found(self, db):
        """Test distinguishing cache miss from cached not-found."""
        # Cache miss (not in cache at all)
        user1 = get_cached_user("never_cached", query_db=False)
        assert user1 is None

        # Cached not-found
        cache_key = get_user_cache_key("cached_missing")
        cache.set(cache_key, False)
        user2 = get_cached_user("cached_missing", query_db=False)
        assert user2 is None

        # Both return None, but internal behavior differs
        # (second one doesn't query DB, first would if query_db=True)
