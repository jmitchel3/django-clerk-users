"""
Tests for django-clerk-users models.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_test123",
        email="test@example.com",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def superuser(db):
    """Create a test superuser."""
    User = get_user_model()
    return User.objects.create_superuser(
        clerk_id="user_super123",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
    )


class TestClerkUserModel:
    """Test ClerkUser model."""

    def test_create_user(self, db):
        """Test creating a basic user."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_abc123",
            email="test@example.com",
        )

        assert user.clerk_id == "user_abc123"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.has_usable_password() is False

    def test_create_user_with_password(self, db):
        """Test creating a user with a password."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_pwd123",
            email="pwd@example.com",
            password="testpass123",
        )

        assert user.has_usable_password() is True
        assert user.check_password("testpass123") is True

    def test_create_superuser(self, db):
        """Test creating a superuser."""
        User = get_user_model()
        user = User.objects.create_superuser(
            clerk_id="user_supertest",
            email="super@example.com",
        )

        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.is_active is True

    def test_create_superuser_must_be_staff(self, db):
        """Test that superuser must have is_staff=True."""
        User = get_user_model()
        with pytest.raises(ValueError, match="Superuser must have is_staff=True"):
            User.objects.create_superuser(
                clerk_id="user_fail1",
                email="fail1@example.com",
                is_staff=False,
            )

    def test_create_superuser_must_be_superuser(self, db):
        """Test that superuser must have is_superuser=True."""
        User = get_user_model()
        with pytest.raises(ValueError, match="Superuser must have is_superuser=True"):
            User.objects.create_superuser(
                clerk_id="user_fail2",
                email="fail2@example.com",
                is_superuser=False,
            )

    def test_create_user_without_clerk_id(self, db):
        """Test that clerk_id is optional (for Django admin users)."""
        User = get_user_model()
        # Should not raise - clerk_id is optional now
        user = User.objects.create_user(email="admin@example.com", password="testpass")
        assert user.clerk_id is None
        assert user.email == "admin@example.com"

    def test_create_user_without_email_and_clerk_id(self, db):
        """Test that email is required for admin users (no clerk_id)."""
        User = get_user_model()
        with pytest.raises(ValueError, match="email must be set for admin users"):
            User.objects.create_user(email=None, clerk_id=None)

    def test_create_clerk_user_without_email(self, db):
        """Test that Clerk users can be created without email."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_no_email",
            email=None,
            username="testuser",
        )
        assert user.email is None
        assert user.username == "testuser"
        assert user.clerk_id == "user_no_email"

    def test_create_clerk_user_with_username_only(self, db):
        """Test creating a Clerk user with username but no email."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_username_only",
            username="usernameonly",
        )
        assert user.email is None
        assert user.username == "usernameonly"
        assert user.clerk_id == "user_username_only"

    def test_create_clerk_user_with_clerk_id_only(self, db):
        """Test creating a Clerk user with only clerk_id (no email, no username)."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_clerk_id_only",
            email=None,
            username=None,
        )
        assert user.email is None
        assert user.username is None
        assert user.clerk_id == "user_clerk_id_only"

    def test_create_clerk_user_with_both_email_and_username(self, db):
        """Test creating a Clerk user with both email and username."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_both",
            email="both@example.com",
            username="bothuser",
        )
        assert user.email == "both@example.com"
        assert user.username == "bothuser"
        assert user.clerk_id == "user_both"

    def test_user_str(self, clerk_user):
        """Test user string representation."""
        assert str(clerk_user) == "test@example.com"

    def test_user_str_username_fallback(self, db):
        """Test user string falls back to username when no email."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_str_username",
            username="myusername",
        )
        assert str(user) == "myusername"

    def test_user_str_clerk_id_fallback(self, db):
        """Test user string falls back to clerk_id when no email or username."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_str_clerkid",
        )
        assert str(user) == "user_str_clerkid"

    def test_user_str_uid_fallback(self, db):
        """Test user string falls back to uid when no other identifiers."""
        User = get_user_model()
        # Create user directly bypassing manager to have null clerk_id
        user = User(email=None, username=None, clerk_id=None)
        user.set_unusable_password()
        user.save()
        assert str(user) == str(user.uid)

    def test_user_uid_is_uuid(self, clerk_user):
        """Test that uid is a valid UUID."""
        assert isinstance(clerk_user.uid, uuid.UUID)

    def test_user_public_id(self, clerk_user):
        """Test public_id property."""
        assert clerk_user.public_id == str(clerk_user.uid)

    def test_user_full_name(self, clerk_user):
        """Test full_name property."""
        assert clerk_user.full_name == "Test User"

    def test_user_full_name_empty_names(self, db):
        """Test full_name with empty names."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_noname",
            email="noname@example.com",
        )
        assert user.full_name == ""

    def test_get_full_name(self, clerk_user):
        """Test get_full_name method."""
        assert clerk_user.get_full_name() == "Test User"

    def test_get_short_name(self, clerk_user):
        """Test get_short_name method."""
        assert clerk_user.get_short_name() == "Test"

    def test_get_short_name_no_first_name(self, db):
        """Test get_short_name without first name."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_nofirst",
            email="nofirst@example.com",
        )
        assert user.get_short_name() == "nofirst"

    def test_get_short_name_username_fallback(self, db):
        """Test get_short_name falls back to username when no first name."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_short_username",
            username="shortusername",
        )
        assert user.get_short_name() == "shortusername"

    def test_get_short_name_uid_fallback(self, db):
        """Test get_short_name falls back to uid prefix when no other identifiers."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_short_uid",
            email=None,
            username=None,
        )
        expected = str(user.uid)[:8]
        assert user.get_short_name() == expected

    def test_superuser_has_all_perms(self, superuser):
        """Test superuser has all permissions."""
        assert superuser.has_perm("any.permission") is True
        assert superuser.has_module_perms("any_app") is True

    def test_regular_user_default_perms(self, clerk_user):
        """Test regular user default permissions."""
        # Regular user without explicit perms returns False
        assert clerk_user.has_perm("some.perm") is False
        assert clerk_user.has_module_perms("some_app") is False

    def test_user_timestamps(self, clerk_user):
        """Test user timestamps."""
        assert clerk_user.created_at is not None
        assert clerk_user.updated_at is not None

    def test_username_field(self):
        """Test USERNAME_FIELD is email."""
        from django_clerk_users.models import ClerkUser

        assert ClerkUser.USERNAME_FIELD == "email"

    def test_required_fields(self):
        """Test REQUIRED_FIELDS is empty (clerk_id is optional for hybrid auth)."""
        from django_clerk_users.models import ClerkUser

        # REQUIRED_FIELDS should be empty to support creating admin users via createsuperuser
        assert ClerkUser.REQUIRED_FIELDS == []


class TestClerkUserManager:
    """Test ClerkUserManager methods."""

    def test_get_by_clerk_id(self, clerk_user):
        """Test get_by_clerk_id method."""
        User = get_user_model()
        found = User.objects.get_by_clerk_id("user_test123")
        assert found == clerk_user

    def test_get_by_clerk_id_not_found(self, db):
        """Test get_by_clerk_id returns None for missing user."""
        User = get_user_model()
        found = User.objects.get_by_clerk_id("nonexistent")
        assert found is None

    def test_get_by_email(self, clerk_user):
        """Test get_by_email method."""
        User = get_user_model()
        found = User.objects.get_by_email("test@example.com")
        assert found == clerk_user

    def test_get_by_email_case_insensitive(self, clerk_user):
        """Test get_by_email handles case insensitivity in domain."""
        User = get_user_model()
        # Django normalizes email by lowercasing the domain part
        # So TEST@EXAMPLE.COM becomes TEST@example.com
        found = User.objects.get_by_email("test@EXAMPLE.COM")
        assert found == clerk_user

    def test_get_by_email_not_found(self, db):
        """Test get_by_email returns None for missing user."""
        User = get_user_model()
        found = User.objects.get_by_email("nonexistent@example.com")
        assert found is None

    def test_get_by_username(self, db):
        """Test get_by_username method."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_byusername",
            username="findme",
        )
        found = User.objects.get_by_username("findme")
        assert found == user

    def test_get_by_username_not_found(self, db):
        """Test get_by_username returns None for missing user."""
        User = get_user_model()
        found = User.objects.get_by_username("nonexistent")
        assert found is None

    def test_username_unique_constraint(self, db):
        """Test that username must be unique (when not null)."""
        User = get_user_model()
        User.objects.create_user(
            clerk_id="user_unique1",
            username="uniqueuser",
        )
        with pytest.raises(Exception):  # IntegrityError
            User.objects.create_user(
                clerk_id="user_unique2",
                username="uniqueuser",  # Duplicate
            )

    def test_multiple_null_usernames_allowed(self, db):
        """Test that multiple users can have null username."""
        User = get_user_model()
        user1 = User.objects.create_user(
            clerk_id="user_null1",
            email="null1@example.com",
            username=None,
        )
        user2 = User.objects.create_user(
            clerk_id="user_null2",
            email="null2@example.com",
            username=None,
        )
        assert user1.username is None
        assert user2.username is None

    def test_normalize_email(self, db):
        """Test email normalization on create."""
        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_norm",
            email="TEST@EXAMPLE.COM",
        )
        # Email domain should be lowercased
        assert "@example.com" in user.email.lower()


class TestSetPassword:
    """Tests for set_password with Clerk sync."""

    @patch("django_clerk_users.client.get_clerk_client")
    def test_set_password_syncs_to_clerk_by_default(self, mock_get_client, db):
        """Test that set_password syncs to Clerk by default."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        user = User.objects.create(clerk_id="clerk_password_test", email="pw@test.com")
        user.set_password("new_password123")

        # Verify Clerk was called
        mock_client.users.update.assert_called_once_with(
            user_id="clerk_password_test", password="new_password123"
        )

    @patch("django_clerk_users.client.get_clerk_client")
    def test_set_password_sync_disabled(self, mock_get_client, db):
        """Test that sync_to_clerk=False skips Clerk sync."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        user = User.objects.create(clerk_id="clerk_no_sync_test", email="nosync@test.com")
        user.set_password("new_password123", sync_to_clerk=False)

        # Verify Clerk was NOT called
        mock_client.users.update.assert_not_called()

    def test_set_password_skips_clerk_for_user_without_clerk_id(self, db):
        """Test that sync is skipped for users without a clerk_id."""
        # User without clerk_id (like a Django admin user)
        user = User.objects.create(clerk_id=None, email="admin@test.com")

        # Should not raise - just skips Clerk sync
        user.set_password("admin_password")

        # Verify password was set in Django
        assert user.check_password("admin_password")

    @patch("django_clerk_users.client.get_clerk_client")
    def test_set_password_handles_clerk_error(self, mock_get_client, db):
        """Test that Clerk errors don't break password setting."""
        mock_client = MagicMock()
        mock_client.users.update.side_effect = Exception("Clerk API error")
        mock_get_client.return_value = mock_client

        user = User.objects.create(clerk_id="clerk_error_test", email="error@test.com")
        user.set_password("new_password123")

        # Password should still be set in Django despite Clerk error
        assert user.check_password("new_password123")
