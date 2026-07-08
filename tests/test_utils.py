"""
Tests for django-clerk-users utils module.
"""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError

from django_clerk_users.caching import get_user_cache_key, set_cached_user
from django_clerk_users.exceptions import (
    ClerkAPIError,
    ClerkUserMergeConflictError,
    ClerkUserNotFoundError,
)
from django_clerk_users.utils import (
    _clerk_list_data,
    _clerk_timeout_options,
    absorb_clerk_user_duplicate,
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


def make_mock_clerk_user(
    user_id,
    email=None,
    first_name="Test",
    last_name="User",
    username=None,
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


class TestClerkTimeoutOptions:
    """Test Clerk SDK timeout option handling in utility paths."""

    def test_uses_runtime_timeout_setting(self, settings):
        settings.CLERK_API_TIMEOUT_MS = "1234"

        assert _clerk_timeout_options() == {"timeout_ms": 1234}

    def test_invalid_timeout_falls_back_to_default(self, settings):
        settings.CLERK_API_TIMEOUT_MS = "not-an-int"

        assert _clerk_timeout_options() == {"timeout_ms": 10000}


class TestClerkListData:
    """Test Clerk SDK list response normalization."""

    def test_accepts_plain_list_response(self):
        assert _clerk_list_data(["a", "b"]) == ["a", "b"]

    def test_accepts_paginated_data_attribute(self):
        response = SimpleNamespace(data=("a", "b"))

        assert _clerk_list_data(response) == ["a", "b"]

    def test_accepts_mapping_data_response(self):
        assert _clerk_list_data({"data": ("a", "b")}) == ["a", "b"]

    def test_none_response_is_empty(self):
        assert _clerk_list_data(None) == []


class TestUpdateOrCreateClerkUser:
    """Test update_or_create_clerk_user function."""

    def test_create_new_user(self, db, mock_clerk_client):
        """Test creating a new user from Clerk."""
        mock_clerk_user = make_mock_clerk_user(
            "user_new123",
            email="new@example.com",
            first_name="New",
            last_name="Person",
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

    def test_create_recovers_from_concurrent_clerk_id_race(self, db, mock_clerk_client):
        """Test concurrent first-login races return the winning local user."""
        User = get_user_model()
        mock_clerk_user = make_mock_clerk_user(
            "user_race",
            email="race@example.com",
            first_name="Race",
            last_name="Winner",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user
        original_create = User.objects.create

        def create_winning_row_then_raise(*args, **kwargs):
            original_create(*args, **kwargs)
            raise IntegrityError("duplicate clerk_id")

        with (
            patch(
                "django_clerk_users.utils.get_clerk_client",
                return_value=mock_clerk_client,
            ),
            patch(
                "django_clerk_users.utils.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch.object(
                User.objects,
                "create",
                side_effect=create_winning_row_then_raise,
            ),
        ):
            user, created = update_or_create_clerk_user("user_race")

        assert created is False
        assert user.clerk_id == "user_race"
        assert user.email == "race@example.com"
        assert User.objects.filter(clerk_id="user_race").count() == 1
        assert get_clerk_user("user_race").pk == user.pk

    def test_update_existing_user(self, clerk_user, mock_clerk_client):
        """Test updating an existing user from Clerk."""
        mock_clerk_user = make_mock_clerk_user(
            "user_util123",
            email="updated@example.com",
            first_name="Updated",
            last_name="Name",
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

    def test_update_existing_user_email_conflict_is_not_treated_as_race(
        self, db, mock_clerk_client
    ):
        """Test non-create uniqueness errors still surface as Clerk sync failures."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_email_conflict",
            email="current@example.com",
        )
        User.objects.create_user(email="taken@example.com")

        mock_clerk_user = make_mock_clerk_user(
            "user_email_conflict",
            email="taken@example.com",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with (
            patch(
                "django_clerk_users.utils.get_clerk_client",
                return_value=mock_clerk_client,
            ),
            pytest.raises(ClerkAPIError),
        ):
            update_or_create_clerk_user("user_email_conflict")

        user.refresh_from_db()
        assert user.email == "current@example.com"

    def test_user_not_found_in_clerk(self, db, mock_clerk_client):
        """Test handling when user not found in Clerk."""
        mock_clerk_client.users.get.return_value = None

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            with pytest.raises(ClerkUserNotFoundError):
                update_or_create_clerk_user("nonexistent")

    def test_user_without_email_but_with_username(self, db, mock_clerk_client):
        """Test creating user with username but no email."""
        mock_clerk_user = make_mock_clerk_user(
            "user_username_only",
            email=None,
            username="usernameonly",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_username_only")

        assert created is True
        assert user.clerk_id == "user_username_only"
        assert user.email is None
        assert user.username == "usernameonly"

    def test_user_with_clerk_id_only(self, db, mock_clerk_client):
        """Test creating user with only clerk_id (no email, no username)."""
        mock_clerk_user = make_mock_clerk_user(
            "user_clerk_id_only",
            email=None,
            username=None,
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_clerk_id_only")

        assert created is True
        assert user.clerk_id == "user_clerk_id_only"
        assert user.email is None
        assert user.username is None

    def test_user_with_both_email_and_username(self, db, mock_clerk_client):
        """Test creating user with both email and username."""
        mock_clerk_user = make_mock_clerk_user(
            "user_both",
            email="both@example.com",
            username="bothuser",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_both")

        assert created is True
        assert user.email == "both@example.com"
        assert user.username == "bothuser"

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
        mock_user.username = None

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

    def test_link_existing_user_by_email(self, db, mock_clerk_client):
        """Test linking existing Django user to Clerk by email."""
        User = get_user_model()
        existing_user = User.objects.create_user(
            email="existing@example.com",
            password="testpass",
        )
        assert existing_user.clerk_id is None

        mock_clerk_user = make_mock_clerk_user(
            "user_link_email",
            email="existing@example.com",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_link_email")

        assert created is False
        assert user.pk == existing_user.pk
        assert user.clerk_id == "user_link_email"

    def test_link_existing_user_by_username(self, db, mock_clerk_client):
        """Test linking existing Django user to Clerk by username."""
        User = get_user_model()
        # Create user with username but no clerk_id
        existing_user = User(
            email="linkbyusername@example.com",
            username="existinguser",
        )
        existing_user.set_password("testpass")
        existing_user.save()
        assert existing_user.clerk_id is None

        mock_clerk_user = make_mock_clerk_user(
            "user_link_username",
            email=None,
            username="existinguser",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_link_username")

        assert created is False
        assert user.pk == existing_user.pk
        assert user.clerk_id == "user_link_username"

    def test_update_adds_username_to_email_only_user(self, db, mock_clerk_client):
        """Test updating a user to add username."""
        User = get_user_model()
        existing_user = User.objects.create_user(
            clerk_id="user_add_username",
            email="addusername@example.com",
        )
        assert existing_user.username is None

        mock_clerk_user = make_mock_clerk_user(
            "user_add_username",
            email="addusername@example.com",
            username="newusername",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_add_username")

        assert created is False
        assert user.username == "newusername"

    def test_update_adds_email_to_username_only_user(self, db, mock_clerk_client):
        """Test updating a user to add email."""
        User = get_user_model()
        existing_user = User.objects.create_user(
            clerk_id="user_add_email",
            username="addemail",
        )
        assert existing_user.email is None

        mock_clerk_user = make_mock_clerk_user(
            "user_add_email",
            email="newemail@example.com",
            username="addemail",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user, created = update_or_create_clerk_user("user_add_email")

        assert created is False
        assert user.email == "newemail@example.com"


class TestAbsorbClerkUserDuplicate:
    """Test adopting Clerk IDs from fresh duplicate users."""

    def test_no_duplicate_returns_false(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="historical@students.internal",
            clerk_id=None,
        )

        assert absorb_clerk_user_duplicate(target, email="claimed@example.com") is False

    def test_absorbs_fresh_duplicate_by_email(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="historical@students.internal",
            clerk_id=None,
        )
        duplicate = User.objects.create_user(
            email="claimed@example.com",
            clerk_id="user_claimed",
        )
        set_cached_user("user_claimed", duplicate)

        absorbed = absorb_clerk_user_duplicate(
            target,
            email="CLAIMED@example.com",
        )

        target.refresh_from_db()
        assert absorbed is True
        assert target.clerk_id == "user_claimed"
        assert not User.objects.filter(pk=duplicate.pk).exists()
        assert cache.get(get_user_cache_key("user_claimed")) is None

    def test_absorbs_explicit_duplicate_user_without_deleting(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="target@example.com",
            clerk_id=None,
        )
        duplicate = User.objects.create_user(
            email="duplicate@example.com",
            clerk_id="user_duplicate",
        )

        absorbed = absorb_clerk_user_duplicate(
            target,
            duplicate_user=duplicate,
            delete_duplicate=False,
        )

        target.refresh_from_db()
        duplicate.refresh_from_db()
        assert absorbed is True
        assert target.clerk_id == "user_duplicate"
        assert duplicate.clerk_id is None

    def test_replaces_target_clerk_id_and_invalidates_both_cache_keys(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="historical@students.internal",
            clerk_id="user_old",
        )
        duplicate = User.objects.create_user(
            email="claimed@example.com",
            clerk_id="user_new",
        )
        set_cached_user("user_old", target)
        set_cached_user("user_new", duplicate)

        absorbed = absorb_clerk_user_duplicate(
            target,
            email="claimed@example.com",
        )

        target.refresh_from_db()
        assert absorbed is True
        assert target.clerk_id == "user_new"
        assert cache.get(get_user_cache_key("user_old")) is None
        assert cache.get(get_user_cache_key("user_new")) is None

    def test_refuses_to_replace_target_clerk_id_when_disabled(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="historical@students.internal",
            clerk_id="user_old",
        )
        duplicate = User.objects.create_user(
            email="claimed@example.com",
            clerk_id="user_new",
        )

        with pytest.raises(ClerkUserMergeConflictError, match="already has Clerk ID"):
            absorb_clerk_user_duplicate(
                target,
                email="claimed@example.com",
                replace_existing_clerk_id=False,
            )

        target.refresh_from_db()
        duplicate.refresh_from_db()
        assert target.clerk_id == "user_old"
        assert duplicate.clerk_id == "user_new"

    def test_default_predicate_refuses_duplicate_with_password(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="historical@students.internal",
            clerk_id=None,
        )
        duplicate = User.objects.create_user(
            email="claimed@example.com",
            clerk_id="user_claimed",
            password="not-a-shell",
        )

        with pytest.raises(ClerkUserMergeConflictError, match="not safe"):
            absorb_clerk_user_duplicate(target, email="claimed@example.com")

        assert User.objects.filter(pk=duplicate.pk).exists()
        target.refresh_from_db()
        assert target.clerk_id is None

    def test_app_predicate_controls_duplicate_disposal(self, db):
        User = get_user_model()
        target = User.objects.create_user(
            email="historical@students.internal",
            clerk_id=None,
        )
        duplicate = User.objects.create_user(
            email="claimed@example.com",
            clerk_id="user_claimed",
            password="not-a-shell",
        )

        absorbed = absorb_clerk_user_duplicate(
            target,
            email="claimed@example.com",
            safe_to_delete=lambda user: user.pk == duplicate.pk,
        )

        target.refresh_from_db()
        assert absorbed is True
        assert target.clerk_id == "user_claimed"
        assert not User.objects.filter(pk=duplicate.pk).exists()

    def test_requires_email_or_duplicate_user(self, db):
        User = get_user_model()
        target = User.objects.create_user(email="target@example.com")

        with pytest.raises(ValueError, match="email or duplicate_user"):
            absorb_clerk_user_duplicate(target)


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
        from django_clerk_users.caching import set_cached_user

        # Pre-populate cache
        set_cached_user("user_util123", clerk_user)

        mock_clerk_user = make_mock_clerk_user(
            "user_util123",
            email="synced@example.com",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user = sync_user_from_clerk("user_util123")

        assert user.email == "synced@example.com"

    def test_sync_username_only_user(self, db, mock_clerk_client):
        """Test syncing a username-only user."""
        mock_clerk_user = make_mock_clerk_user(
            "user_sync_username",
            email=None,
            username="syncusername",
        )
        mock_clerk_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_clerk_client,
        ):
            user = sync_user_from_clerk("user_sync_username")

        assert user is not None
        assert user.email is None
        assert user.username == "syncusername"

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
