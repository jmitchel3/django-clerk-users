"""
Tests for django-clerk-users utils module.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from django_clerk_users.exceptions import ClerkAPIError, ClerkUserNotFoundError
from django_clerk_users.utils import (
    get_clerk_user,
    get_user_metadata,
    sync_user_from_clerk,
    update_or_create_clerk_user,
    update_user_metadata,
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
        clerk_id="user_util123",
        email="util@example.com",
        first_name="Util",
        last_name="User",
    )


@pytest.fixture
def mock_clerk_client():
    """Create a mock Clerk client."""
    return MagicMock()


def make_mock_clerk_user(user_id, email, first_name="Test", last_name="User"):
    """Create a mock Clerk user object."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.first_name = first_name
    mock_user.last_name = last_name
    mock_user.image_url = "https://example.com/image.jpg"
    mock_user.primary_email_address_id = "email_123"

    email_obj = MagicMock()
    email_obj.id = "email_123"
    email_obj.email_address = email
    mock_user.email_addresses = [email_obj]

    return mock_user


class TestUpdateOrCreateClerkUser:
    """Test update_or_create_clerk_user function."""

    def test_create_new_user(self, db, mock_clerk_client):
        """Test creating a new user from Clerk."""
        mock_clerk_user = make_mock_clerk_user(
            "user_new123",
            "new@example.com",
            "New",
            "Person",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_new123")

        assert created is True
        assert user.clerk_id == "user_new123"
        assert user.email == "new@example.com"
        assert user.first_name == "New"
        assert user.last_name == "Person"

    def test_update_existing_user(self, clerk_user, mock_clerk_client):
        """Test updating an existing user from Clerk."""
        mock_clerk_user = make_mock_clerk_user(
            "user_util123",
            "updated@example.com",
            "Updated",
            "Name",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_util123")

        assert created is False
        assert user.email == "updated@example.com"
        assert user.first_name == "Updated"

    def test_user_not_found_in_clerk(self, db, mock_clerk_client):
        """Test handling when user not found in Clerk."""
        mock_clerk_client.users.get.return_value = None

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            with pytest.raises(ClerkUserNotFoundError):
                update_or_create_clerk_user("nonexistent")

    def test_user_without_email(self, db, mock_clerk_client):
        """Test handling user without email address."""
        mock_user = MagicMock()
        mock_user.email_addresses = []
        mock_clerk_client.users.get.return_value = mock_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            with pytest.raises(ClerkAPIError, match="no email"):
                update_or_create_clerk_user("user_no_email")

    def test_api_error(self, db, mock_clerk_client):
        """Test handling Clerk API errors."""
        mock_clerk_client.users.get.side_effect = Exception("API Error")

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            with pytest.raises(ClerkAPIError):
                update_or_create_clerk_user("user_error")

    def test_fallback_to_first_email(self, db, mock_clerk_client):
        """Test fallback to first email when no primary email ID."""
        mock_user = MagicMock()
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.image_url = ""
        mock_user.primary_email_address_id = None

        email_obj = MagicMock()
        email_obj.id = "email_456"
        email_obj.email_address = "fallback@example.com"
        mock_user.email_addresses = [email_obj]

        mock_clerk_client.users.get.return_value = mock_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_fallback")

        assert user.email == "fallback@example.com"


class TestGetClerkUser:
    """Test get_clerk_user function."""

    def test_get_existing_user(self, clerk_user):
        """Test getting an existing user."""
        user = get_clerk_user("user_util123")
        assert user == clerk_user

    def test_get_nonexistent_user(self, db):
        """Test getting a nonexistent user."""
        user = get_clerk_user("nonexistent")
        assert user is None

    def test_uses_cache(self, clerk_user):
        """Test that function uses cache."""
        # First call populates cache
        get_clerk_user("user_util123")

        # Verify cache is used (would need to check cache key exists)
        from django_clerk_users.caching import get_user_cache_key

        cache_key = get_user_cache_key("user_util123")
        assert cache.get(cache_key) is not None


class TestSyncUserFromClerk:
    """Test sync_user_from_clerk function."""

    def test_sync_invalidates_cache(self, clerk_user, mock_clerk_client):
        """Test that sync invalidates cache before fetching."""
        from django_clerk_users.caching import get_user_cache_key, set_cached_user

        # Pre-populate cache
        set_cached_user("user_util123", clerk_user)

        mock_clerk_user = make_mock_clerk_user(
            "user_util123",
            "synced@example.com",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user = sync_user_from_clerk("user_util123")

        assert user.email == "synced@example.com"

    def test_sync_failure_returns_none(self, db, mock_clerk_client):
        """Test that sync failure returns None."""
        mock_clerk_client.users.get.side_effect = Exception("Sync error")

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user = sync_user_from_clerk("user_sync_fail")

        assert user is None


class TestGetUserMetadata:
    """Test get_user_metadata function."""

    def test_get_metadata_success(self, mock_clerk_client):
        """Test getting user metadata."""
        mock_user = MagicMock()
        mock_user.public_metadata = {"role": "admin"}
        mock_user.private_metadata = {"internal_id": "123"}
        mock_clerk_client.users.get.return_value = mock_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            metadata = get_user_metadata("user_123")

        assert metadata["public"] == {"role": "admin"}
        assert metadata["private"] == {"internal_id": "123"}

    def test_get_metadata_user_not_found(self, mock_clerk_client):
        """Test getting metadata for nonexistent user."""
        mock_clerk_client.users.get.return_value = None

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            metadata = get_user_metadata("nonexistent")

        assert metadata == {"public": {}, "private": {}}

    def test_get_metadata_api_error(self, mock_clerk_client):
        """Test getting metadata with API error."""
        mock_clerk_client.users.get.side_effect = Exception("API Error")

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            metadata = get_user_metadata("user_error")

        assert metadata == {"public": {}, "private": {}}


class TestUpdateUserMetadata:
    """Test update_user_metadata function."""

    def test_update_public_metadata(self, mock_clerk_client):
        """Test updating public metadata."""
        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            result = update_user_metadata(
                "user_123",
                public_metadata={"new_key": "new_value"},
            )

        assert result is True
        mock_clerk_client.users.update.assert_called_once()

    def test_update_private_metadata(self, mock_clerk_client):
        """Test updating private metadata."""
        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            result = update_user_metadata(
                "user_123",
                private_metadata={"secret": "value"},
            )

        assert result is True
        mock_clerk_client.users.update.assert_called_once()

    def test_update_both_metadata(self, mock_clerk_client):
        """Test updating both public and private metadata."""
        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            result = update_user_metadata(
                "user_123",
                public_metadata={"public": "data"},
                private_metadata={"private": "data"},
            )

        assert result is True

    def test_update_no_metadata(self, mock_clerk_client):
        """Test update with no metadata provided."""
        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            result = update_user_metadata("user_123")

        assert result is True
        mock_clerk_client.users.update.assert_not_called()

    def test_update_api_error(self, mock_clerk_client):
        """Test update with API error."""
        mock_clerk_client.users.update.side_effect = Exception("API Error")

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            result = update_user_metadata(
                "user_123",
                public_metadata={"key": "value"},
            )

        assert result is False
