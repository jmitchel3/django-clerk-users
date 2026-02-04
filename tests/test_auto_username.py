"""
Tests for auto-generated username functionality.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model

User = get_user_model()


class TestGenerateUniqueUsername:
    """Tests for the generate_unique_username manager method."""

    def test_generate_unique_username_default_prefix(self, db):
        """Test generating username with default prefix."""
        username = User.objects.generate_unique_username()

        assert username.startswith("user_")
        assert len(username) == 13  # "user_" (5) + uuid8 (8)

    def test_generate_unique_username_custom_prefix(self, db):
        """Test generating username with custom prefix."""
        username = User.objects.generate_unique_username(prefix="testuser")

        assert username.startswith("testuser_")
        assert len(username) == 17  # "testuser_" (9) + uuid8 (8)

    def test_generate_unique_username_is_unique(self, db):
        """Test that generated usernames don't collide with existing users."""
        # Create users with several usernames
        for i in range(5):
            User.objects.create(
                clerk_id=f"clerk_{i}",
                username=f"user_{i:08d}",
            )

        # Generate new usernames
        generated = set()
        for _ in range(10):
            username = User.objects.generate_unique_username()
            assert username not in generated
            generated.add(username)


class TestAutoGenerateUsernameSetting:
    """Tests for CLERK_AUTO_GENERATE_USERNAME setting."""

    @patch("django_clerk_users.utils.get_clerk_client")
    @patch("django_clerk_users.settings.CLERK_AUTO_GENERATE_USERNAME", False)
    def test_auto_generate_disabled_by_default(self, mock_get_client, db):
        """Test that auto-generation is disabled by default."""
        from django_clerk_users.utils import update_or_create_clerk_user

        # Mock Clerk API response without username
        mock_clerk_user = MagicMock()
        mock_clerk_user.email_addresses = []
        mock_clerk_user.primary_email_address_id = None
        mock_clerk_user.username = None
        mock_clerk_user.first_name = "Test"
        mock_clerk_user.last_name = "User"
        mock_clerk_user.image_url = ""

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user
        mock_get_client.return_value = mock_client

        user, created = update_or_create_clerk_user("clerk_test_123")

        assert created is True
        assert user.username is None

    @patch("django_clerk_users.utils.get_clerk_client")
    @patch("django_clerk_users.settings.CLERK_AUTO_GENERATE_USERNAME", True)
    def test_auto_generate_when_enabled(self, mock_get_client, db):
        """Test that username is auto-generated when setting is enabled."""
        from django_clerk_users.utils import update_or_create_clerk_user

        # Mock Clerk API response without username
        mock_clerk_user = MagicMock()
        mock_clerk_user.email_addresses = []
        mock_clerk_user.primary_email_address_id = None
        mock_clerk_user.username = None
        mock_clerk_user.first_name = "Test"
        mock_clerk_user.last_name = "User"
        mock_clerk_user.image_url = ""

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user
        mock_get_client.return_value = mock_client

        user, created = update_or_create_clerk_user("clerk_test_456")

        assert created is True
        assert user.username is not None
        assert user.username.startswith("user_")

    @patch("django_clerk_users.utils.get_clerk_client")
    @patch("django_clerk_users.settings.CLERK_AUTO_GENERATE_USERNAME", True)
    def test_no_auto_generate_when_username_exists(self, mock_get_client, db):
        """Test that existing Clerk username is preserved when auto-generate is enabled."""
        from django_clerk_users.utils import update_or_create_clerk_user

        # Mock Clerk API response with username
        mock_clerk_user = MagicMock()
        mock_clerk_user.email_addresses = []
        mock_clerk_user.primary_email_address_id = None
        mock_clerk_user.username = "existing_username"
        mock_clerk_user.first_name = "Test"
        mock_clerk_user.last_name = "User"
        mock_clerk_user.image_url = ""

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user
        mock_get_client.return_value = mock_client

        user, created = update_or_create_clerk_user("clerk_test_789")

        assert created is True
        assert user.username == "existing_username"


class TestGenerateUsernameForUser:
    """Tests for generate_username_for_user utility function."""

    def test_generate_for_user_by_pk(self, db):
        """Test generating username for user by primary key."""
        from django_clerk_users.utils import generate_username_for_user

        user = User.objects.create(clerk_id="clerk_pk_test", username=None)

        result = generate_username_for_user(user.pk)

        user.refresh_from_db()
        assert result is not None
        assert result.startswith("user_")
        assert user.username == result

    def test_generate_for_user_by_clerk_id(self, db):
        """Test generating username for user by clerk_id."""
        from django_clerk_users.utils import generate_username_for_user

        user = User.objects.create(clerk_id="clerk_id_test", username=None)

        result = generate_username_for_user("clerk_id_test")

        user.refresh_from_db()
        assert result is not None
        assert result.startswith("user_")
        assert user.username == result

    def test_generate_with_custom_prefix(self, db):
        """Test generating username with custom prefix."""
        from django_clerk_users.utils import generate_username_for_user

        user = User.objects.create(clerk_id="clerk_prefix_test", username=None)

        result = generate_username_for_user(user.pk, prefix="custom")

        user.refresh_from_db()
        assert result is not None
        assert result.startswith("custom_")
        assert user.username == result

    def test_skip_if_username_exists(self, db):
        """Test that existing username is preserved without force flag."""
        from django_clerk_users.utils import generate_username_for_user

        user = User.objects.create(clerk_id="clerk_skip_test", username="existing")

        result = generate_username_for_user(user.pk)

        user.refresh_from_db()
        assert result == "existing"
        assert user.username == "existing"

    def test_force_regenerate(self, db):
        """Test force regenerating username."""
        from django_clerk_users.utils import generate_username_for_user

        user = User.objects.create(clerk_id="clerk_force_test", username="existing")

        result = generate_username_for_user(user.pk, force=True)

        user.refresh_from_db()
        assert result is not None
        assert result != "existing"
        assert user.username == result

    def test_user_not_found(self, db):
        """Test handling of non-existent user."""
        from django_clerk_users.utils import generate_username_for_user

        result = generate_username_for_user(99999)

        assert result is None

    def test_generate_for_user_by_pk_string(self, db):
        """Test generating username for user by pk as string."""
        from django_clerk_users.utils import generate_username_for_user

        user = User.objects.create(clerk_id="clerk_pk_str_test", username=None)

        # Pass pk as string (fallback path when clerk_id lookup fails)
        result = generate_username_for_user(str(user.pk))

        user.refresh_from_db()
        assert result is not None
        assert result.startswith("user_")
        assert user.username == result

    def test_generate_for_user_invalid_string_id(self, db):
        """Test handling of invalid string ID that's not a clerk_id or pk."""
        from django_clerk_users.utils import generate_username_for_user

        result = generate_username_for_user("not_a_valid_id")

        assert result is None


class TestGenerateUsernamesForUsersWithout:
    """Tests for generate_usernames_for_users_without utility function."""

    def test_backfill_usernames(self, db):
        """Test backfilling usernames for users without one."""
        from django_clerk_users.utils import generate_usernames_for_users_without

        # Create users without usernames
        User.objects.create(clerk_id="clerk_backfill_1", username=None)
        User.objects.create(clerk_id="clerk_backfill_2", username=None)
        User.objects.create(clerk_id="clerk_backfill_3", username="has_username")

        count = generate_usernames_for_users_without()

        assert count == 2

        # Verify all users now have usernames
        users = User.objects.filter(clerk_id__startswith="clerk_backfill_")
        for user in users:
            assert user.username is not None

    def test_backfill_with_custom_prefix(self, db):
        """Test backfilling usernames with custom prefix."""
        from django_clerk_users.utils import generate_usernames_for_users_without

        User.objects.create(clerk_id="clerk_custom_1", username=None)
        User.objects.create(clerk_id="clerk_custom_2", username=None)

        count = generate_usernames_for_users_without(prefix="member")

        assert count == 2

        users = User.objects.filter(clerk_id__startswith="clerk_custom_")
        for user in users:
            assert user.username.startswith("member_")

    def test_no_users_to_backfill(self, db):
        """Test when all users already have usernames."""
        from django_clerk_users.utils import generate_usernames_for_users_without

        User.objects.create(clerk_id="clerk_none_1", username="user1")
        User.objects.create(clerk_id="clerk_none_2", username="user2")

        count = generate_usernames_for_users_without()

        assert count == 0


class TestExports:
    """Test that username utilities are properly exported."""

    def test_generate_username_for_user_export(self):
        """Test that generate_username_for_user is exported."""
        from django_clerk_users import generate_username_for_user

        assert callable(generate_username_for_user)

    def test_generate_usernames_for_users_without_export(self):
        """Test that generate_usernames_for_users_without is exported."""
        from django_clerk_users import generate_usernames_for_users_without

        assert callable(generate_usernames_for_users_without)
