"""
Integration tests for username support in django-clerk-users.

These tests verify the full flow of username support across the package.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test."""
    cache.clear()
    yield
    cache.clear()


def make_mock_clerk_user(
    user_id,
    email=None,
    username=None,
    first_name="Test",
    last_name="User",
):
    """Create a mock Clerk user object."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.first_name = first_name
    mock_user.last_name = last_name
    mock_user.image_url = "https://example.com/image.jpg"
    mock_user.username = username

    if email:
        mock_user.primary_email_address_id = "email_123"
        email_obj = MagicMock()
        email_obj.id = "email_123"
        email_obj.email_address = email
        mock_user.email_addresses = [email_obj]
    else:
        mock_user.primary_email_address_id = None
        mock_user.email_addresses = []

    return mock_user


class TestFullUsernameFlow:
    """Test complete flows with username-only users."""

    def test_create_sync_update_flow(self, db):
        """Test full flow: create → sync → update for username-only user."""
        from django_clerk_users.utils import (
            get_clerk_user,
            sync_user_from_clerk,
            update_or_create_clerk_user,
        )

        mock_client = MagicMock()

        # Step 1: Create user via webhook (username only)
        mock_clerk_user = make_mock_clerk_user(
            "user_flow_1",
            username="flowuser",
        )
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            user, created = update_or_create_clerk_user("user_flow_1")

        assert created is True
        assert user.username == "flowuser"
        assert user.email is None

        # Step 2: Get user from cache
        cached_user = get_clerk_user("user_flow_1")
        assert cached_user == user

        # Step 3: Update user (add email)
        mock_clerk_user_updated = make_mock_clerk_user(
            "user_flow_1",
            email="flowemail@example.com",
            username="flowuser",
        )
        mock_client.users.get.return_value = mock_clerk_user_updated

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            synced_user = sync_user_from_clerk("user_flow_1")

        assert synced_user.email == "flowemail@example.com"
        assert synced_user.username == "flowuser"
        assert synced_user.pk == user.pk  # Same user

    def test_webhook_flow_username_to_email(self, db):
        """Test webhook flow: user starts with username, adds email later."""
        from django_clerk_users.webhooks.handlers import (
            handle_user_created,
            handle_user_updated,
        )

        mock_client = MagicMock()

        # Step 1: user.created with username only
        mock_clerk_user = make_mock_clerk_user(
            "user_webhook_flow",
            username="webhookuser",
        )
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            user = handle_user_created({"id": "user_webhook_flow"})

        assert user.username == "webhookuser"
        assert user.email is None
        user_pk = user.pk

        # Step 2: user.updated adds email
        mock_clerk_user_updated = make_mock_clerk_user(
            "user_webhook_flow",
            email="webhookuser@example.com",
            username="webhookuser",
        )
        mock_client.users.get.return_value = mock_clerk_user_updated

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            updated_user = handle_user_updated({"id": "user_webhook_flow"})

        assert updated_user.email == "webhookuser@example.com"
        assert updated_user.username == "webhookuser"
        assert updated_user.pk == user_pk  # Same user


class TestMixedUserScenarios:
    """Test scenarios with mixed user types."""

    def test_mixed_users_coexist(self, db):
        """Test that email-only, username-only, and both users can coexist."""
        User = get_user_model()

        # Email only user
        email_user = User.objects.create_user(
            clerk_id="user_email_only",
            email="emailonly@example.com",
        )

        # Username only user
        username_user = User.objects.create_user(
            clerk_id="user_username_only",
            username="usernameonly",
        )

        # Both email and username user
        both_user = User.objects.create_user(
            clerk_id="user_both",
            email="both@example.com",
            username="bothuser",
        )

        # Clerk ID only user
        clerk_only_user = User.objects.create_user(
            clerk_id="user_clerk_only",
        )

        # Verify all users exist
        assert User.objects.count() == 4
        assert email_user.email == "emailonly@example.com"
        assert email_user.username is None
        assert username_user.username == "usernameonly"
        assert username_user.email is None
        assert both_user.email == "both@example.com"
        assert both_user.username == "bothuser"
        assert clerk_only_user.email is None
        assert clerk_only_user.username is None

    def test_lookup_methods_work_for_all_types(self, db):
        """Test that manager lookup methods work for all user types."""
        User = get_user_model()

        User.objects.create_user(
            clerk_id="user_lookup_1",
            email="lookup@example.com",
        )
        User.objects.create_user(
            clerk_id="user_lookup_2",
            username="lookupuser",
        )
        User.objects.create_user(
            clerk_id="user_lookup_3",
            email="both@example.com",
            username="lookupboth",
        )

        # Test get_by_clerk_id
        assert User.objects.get_by_clerk_id("user_lookup_1") is not None
        assert User.objects.get_by_clerk_id("user_lookup_2") is not None
        assert User.objects.get_by_clerk_id("user_lookup_3") is not None

        # Test get_by_email
        assert User.objects.get_by_email("lookup@example.com") is not None
        assert User.objects.get_by_email("both@example.com") is not None

        # Test get_by_username
        assert User.objects.get_by_username("lookupuser") is not None
        assert User.objects.get_by_username("lookupboth") is not None


class TestBackwardCompatibility:
    """Test backward compatibility with existing email-based users."""

    def test_existing_email_users_still_work(self, db):
        """Test that existing users with email still work as before."""
        User = get_user_model()

        # Create user the old way (email required)
        user = User.objects.create_user(
            clerk_id="user_compat",
            email="compat@example.com",
            first_name="Compat",
            last_name="User",
        )

        # All existing functionality should work
        assert str(user) == "compat@example.com"
        assert user.get_short_name() == "Compat"
        assert user.get_full_name() == "Compat User"
        assert User.objects.get_by_email("compat@example.com") == user
        assert User.objects.get_by_clerk_id("user_compat") == user

    def test_sync_existing_email_user_adds_username(self, db):
        """Test syncing existing email user when Clerk adds username."""
        from django_clerk_users.utils import update_or_create_clerk_user

        User = get_user_model()

        # Create existing email user
        existing = User.objects.create_user(
            clerk_id="user_existing_email",
            email="existing@example.com",
        )
        assert existing.username is None

        # Sync from Clerk where user now has username
        mock_client = MagicMock()
        mock_clerk_user = make_mock_clerk_user(
            "user_existing_email",
            email="existing@example.com",
            username="newlyaddedusername",
        )
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            user, created = update_or_create_clerk_user("user_existing_email")

        assert created is False
        assert user.pk == existing.pk
        assert user.email == "existing@example.com"
        assert user.username == "newlyaddedusername"


class TestUserDisplayMethods:
    """Test __str__ and get_short_name fallback behavior."""

    def test_str_fallback_chain(self, db):
        """Test __str__ falls back correctly: email → username → clerk_id → uid."""
        User = get_user_model()

        # Email present
        user1 = User.objects.create_user(
            clerk_id="user_str1",
            email="str1@example.com",
            username="str1user",
        )
        assert str(user1) == "str1@example.com"

        # No email, has username
        user2 = User.objects.create_user(
            clerk_id="user_str2",
            username="str2user",
        )
        assert str(user2) == "str2user"

        # No email, no username, has clerk_id
        user3 = User.objects.create_user(
            clerk_id="user_str3",
        )
        assert str(user3) == "user_str3"

        # No email, no username, no clerk_id (uses uid)
        user4 = User(email=None, username=None, clerk_id=None)
        user4.set_unusable_password()
        user4.save()
        assert str(user4) == str(user4.uid)

    def test_get_short_name_fallback_chain(self, db):
        """Test get_short_name falls back: first_name → username → email prefix → uid prefix."""
        User = get_user_model()

        # Has first_name
        user1 = User.objects.create_user(
            clerk_id="user_short1",
            email="short1@example.com",
            username="short1user",
            first_name="First",
        )
        assert user1.get_short_name() == "First"

        # No first_name, has username
        user2 = User.objects.create_user(
            clerk_id="user_short2",
            username="short2user",
        )
        assert user2.get_short_name() == "short2user"

        # No first_name, no username, has email
        user3 = User.objects.create_user(
            clerk_id="user_short3",
            email="short3@example.com",
        )
        assert user3.get_short_name() == "short3"

        # No first_name, no username, no email (uses uid prefix)
        user4 = User.objects.create_user(
            clerk_id="user_short4",
        )
        expected = str(user4.uid)[:8]
        assert user4.get_short_name() == expected


class TestCacheWithUsername:
    """Test caching works correctly with username-only users."""

    def test_cache_username_only_user(self, db):
        """Test that username-only users are cached correctly."""
        from django_clerk_users.caching import (
            get_cached_user,
            get_user_cache_key,
            set_cached_user,
        )
        from django_clerk_users.utils import get_clerk_user

        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_cache_username",
            username="cacheduser",
        )

        # Set in cache
        set_cached_user("user_cache_username", user)

        # Verify cache hit
        cached = get_cached_user("user_cache_username")
        assert cached == user
        assert cached.username == "cacheduser"

        # Verify get_clerk_user uses cache
        fetched = get_clerk_user("user_cache_username")
        assert fetched == user


class TestAdminUserCreation:
    """Test admin user creation still requires email."""

    def test_admin_user_requires_email(self, db):
        """Test that admin users (no clerk_id) still require email."""
        User = get_user_model()

        with pytest.raises(ValueError, match="email must be set for admin users"):
            User.objects.create_user(
                email=None,
                password="testpass",
            )

    def test_admin_superuser_requires_email(self, db):
        """Test that superusers still require email."""
        User = get_user_model()

        with pytest.raises(ValueError, match="email must be set for admin users"):
            User.objects.create_superuser(
                email=None,
                password="testpass",
            )

    def test_admin_user_with_email_works(self, db):
        """Test that admin users with email work correctly."""
        User = get_user_model()

        admin = User.objects.create_user(
            email="admin@example.com",
            password="testpass",
        )

        assert admin.email == "admin@example.com"
        assert admin.clerk_id is None
        assert admin.has_usable_password() is True
