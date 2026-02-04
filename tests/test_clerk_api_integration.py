"""
Integration tests that work with the real Clerk API.

These tests are SKIPPED by default unless you have real Clerk credentials.
To run them:
    1. Set CLERK_SECRET_KEY environment variable to a real Clerk secret key
    2. Run: uv run pytest tests/test_clerk_api_integration.py -v

Note: These tests create and delete real users in your Clerk instance.
      Use a test/development Clerk application, not production.
"""

import os

import pytest
from django.contrib.auth import get_user_model

from django_clerk_users.settings import CLERK_SECRET_KEY

# Skip all tests in this module if no real Clerk credentials
REAL_CLERK_KEY = os.environ.get("CLERK_SECRET_KEY", CLERK_SECRET_KEY)
HAS_REAL_CREDENTIALS = (
    REAL_CLERK_KEY
    and not REAL_CLERK_KEY.startswith("sk_test_mock")
    and REAL_CLERK_KEY.startswith("sk_")
)

pytestmark = pytest.mark.skipif(
    not HAS_REAL_CREDENTIALS,
    reason="Real Clerk credentials required. Set CLERK_SECRET_KEY environment variable.",
)


@pytest.fixture
def clerk_client():
    """Get a ClerkTestClient for creating test users."""
    from django_clerk_users.client import get_clerk_client
    from django_clerk_users.testing import ClerkTestClient

    # Clear the cache to ensure we use the current CLERK_SECRET_KEY
    get_clerk_client.cache_clear()

    return ClerkTestClient()


@pytest.fixture
def created_users(clerk_client):
    """Track created users for cleanup."""
    users = []
    yield users
    # Cleanup: delete all created users
    for user_id in users:
        try:
            clerk_client.delete_user(user_id)
        except Exception:
            pass  # Best effort cleanup


class TestClerkAPIUserCreation:
    """Test creating users via real Clerk API."""

    def test_create_user_with_email(self, clerk_client, created_users):
        """Test creating a user with email via Clerk API."""
        user_data = clerk_client.create_test_user()
        created_users.append(user_data.id)

        assert user_data.id is not None
        assert user_data.id.startswith("user_")
        assert user_data.email is not None
        assert "+clerk_test" in user_data.email
        assert user_data.first_name == "Test"
        assert user_data.last_name == "User"

    def test_create_user_with_username(self, clerk_client, created_users):
        """Test creating a user with username via Clerk API."""
        user_data = clerk_client.create_test_user(
            username="testuser_integration",
        )
        created_users.append(user_data.id)

        assert user_data.id is not None
        assert user_data.username == "testuser_integration"
        # Should also have email since skip_email=False by default
        assert user_data.email is not None

    @pytest.mark.skip(reason="Requires Clerk instance configured to allow username-only users")
    def test_create_username_only_user(self, clerk_client, created_users):
        """Test creating a username-only user (no email) via Clerk API.

        Note: This test requires the Clerk instance to have email set as optional.
        Configure this in Clerk Dashboard > User & Authentication > Email, Phone, Username.
        """
        user_data = clerk_client.create_test_user(
            skip_email=True,
            username="username_only_test",
        )
        created_users.append(user_data.id)

        assert user_data.id is not None
        assert user_data.username == "username_only_test"
        assert user_data.email is None

    def test_create_user_with_both_email_and_username(self, clerk_client, created_users):
        """Test creating a user with both email and username."""
        from django_clerk_users.testing import make_test_email

        email = make_test_email("both")
        user_data = clerk_client.create_test_user(
            email=email,
            username="both_user_test",
        )
        created_users.append(user_data.id)

        assert user_data.id is not None
        assert user_data.email == email
        assert user_data.username == "both_user_test"


class TestClerkAPISyncIntegration:
    """Test syncing Clerk users to Django database."""

    def test_sync_email_user_to_django(self, db, clerk_client, created_users):
        """Test syncing an email user from Clerk to Django."""
        from django_clerk_users.utils import update_or_create_clerk_user

        # Create user in Clerk
        clerk_user = clerk_client.create_test_user()
        created_users.append(clerk_user.id)

        # Sync to Django
        django_user, created = update_or_create_clerk_user(clerk_user.id)

        assert created is True
        assert django_user.clerk_id == clerk_user.id
        assert django_user.email == clerk_user.email
        assert django_user.first_name == "Test"
        assert django_user.last_name == "User"

    @pytest.mark.skip(reason="Requires Clerk instance configured to allow username-only users")
    def test_sync_username_user_to_django(self, db, clerk_client, created_users):
        """Test syncing a username-only user from Clerk to Django.

        Note: This test requires the Clerk instance to have email set as optional.
        """
        from django_clerk_users.utils import update_or_create_clerk_user

        # Create username-only user in Clerk
        clerk_user = clerk_client.create_test_user(
            skip_email=True,
            username="sync_username_test",
        )
        created_users.append(clerk_user.id)

        # Sync to Django
        django_user, created = update_or_create_clerk_user(clerk_user.id)

        assert created is True
        assert django_user.clerk_id == clerk_user.id
        assert django_user.email is None
        assert django_user.username == "sync_username_test"

    def test_sync_both_email_and_username_user(self, db, clerk_client, created_users):
        """Test syncing a user with both email and username."""
        from django_clerk_users.utils import update_or_create_clerk_user

        clerk_user = clerk_client.create_test_user(
            username="sync_both_test",
        )
        created_users.append(clerk_user.id)

        django_user, created = update_or_create_clerk_user(clerk_user.id)

        assert created is True
        assert django_user.email == clerk_user.email
        assert django_user.username == "sync_both_test"

    def test_update_existing_django_user(self, db, clerk_client, created_users):
        """Test that syncing updates existing Django user."""
        from django_clerk_users.utils import update_or_create_clerk_user

        # Create and sync initial user
        clerk_user = clerk_client.create_test_user(
            first_name="Initial",
            last_name="Name",
        )
        created_users.append(clerk_user.id)

        django_user, created = update_or_create_clerk_user(clerk_user.id)
        assert created is True
        assert django_user.first_name == "Initial"

        # Sync again (should update, not create)
        django_user2, created2 = update_or_create_clerk_user(clerk_user.id)

        assert created2 is False
        assert django_user2.pk == django_user.pk


class TestClerkAPISessionToken:
    """Test session token generation."""

    def test_get_session_token(self, clerk_client, created_users):
        """Test getting a session token for a user."""
        user_data = clerk_client.create_test_user()
        created_users.append(user_data.id)

        token = clerk_client.get_session_token(user_data.id)

        assert token is not None
        assert len(token) > 0
        # JWT tokens have 3 parts separated by dots
        assert token.count(".") == 2

    @pytest.mark.skip(reason="Requires Clerk instance configured to allow username-only users")
    def test_get_session_token_username_only_user(self, clerk_client, created_users):
        """Test getting a session token for a username-only user.

        Note: This test requires the Clerk instance to have email set as optional.
        """
        user_data = clerk_client.create_test_user(
            skip_email=True,
            username="token_test_user",
        )
        created_users.append(user_data.id)

        token = clerk_client.get_session_token(user_data.id)

        assert token is not None
        assert token.count(".") == 2


class TestClerkAPIUsernameSync:
    """Test syncing generated usernames back to Clerk."""

    def test_generate_username_syncs_to_clerk(self, db, clerk_client, created_users):
        """Test that generate_username_for_user syncs the username to Clerk."""
        from django_clerk_users.client import get_clerk_client
        from django_clerk_users.utils import generate_username_for_user, update_or_create_clerk_user

        # 1. Create user in Clerk without a username
        clerk_user = clerk_client.create_test_user()
        created_users.append(clerk_user.id)

        # 2. Sync to Django
        django_user, _ = update_or_create_clerk_user(clerk_user.id)
        assert django_user.username is None  # No username from Clerk

        # 3. Generate username locally (should sync to Clerk)
        generated_username = generate_username_for_user(django_user.pk)

        assert generated_username is not None
        assert generated_username.startswith("user_")

        # 4. Verify username was synced to Clerk
        clerk = get_clerk_client()
        updated_clerk_user = clerk.users.get(user_id=clerk_user.id)
        assert updated_clerk_user.username == generated_username

    def test_generate_username_sync_disabled(self, db, clerk_client, created_users):
        """Test that sync_to_clerk=False skips Clerk sync."""
        from django_clerk_users.client import get_clerk_client
        from django_clerk_users.utils import generate_username_for_user, update_or_create_clerk_user

        # 1. Create user in Clerk without a username
        clerk_user = clerk_client.create_test_user()
        created_users.append(clerk_user.id)

        # 2. Sync to Django
        django_user, _ = update_or_create_clerk_user(clerk_user.id)

        # 3. Generate username locally WITHOUT syncing to Clerk
        generated_username = generate_username_for_user(django_user.pk, sync_to_clerk=False)

        assert generated_username is not None

        # 4. Verify username was NOT synced to Clerk
        clerk = get_clerk_client()
        clerk_user_after = clerk.users.get(user_id=clerk_user.id)
        assert clerk_user_after.username is None


class TestClerkAPIFullFlow:
    """Test complete authentication flows."""

    def test_full_flow_email_user(self, db, clerk_client, created_users):
        """Test complete flow: create in Clerk -> sync -> get user."""
        from django_clerk_users.utils import get_clerk_user, update_or_create_clerk_user

        # 1. Create user in Clerk
        clerk_user = clerk_client.create_test_user()
        created_users.append(clerk_user.id)

        # 2. Sync to Django
        django_user, _ = update_or_create_clerk_user(clerk_user.id)

        # 3. Retrieve by clerk_id
        retrieved = get_clerk_user(clerk_user.id)

        assert retrieved is not None
        assert retrieved.pk == django_user.pk
        assert retrieved.email == clerk_user.email

    @pytest.mark.skip(reason="Requires Clerk instance configured to allow username-only users")
    def test_full_flow_username_only_user(self, db, clerk_client, created_users):
        """Test complete flow for username-only user.

        Note: This test requires the Clerk instance to have email set as optional.
        """
        from django_clerk_users.utils import get_clerk_user, update_or_create_clerk_user

        User = get_user_model()

        # 1. Create username-only user in Clerk
        clerk_user = clerk_client.create_test_user(
            skip_email=True,
            username="fullflow_username",
        )
        created_users.append(clerk_user.id)

        # 2. Sync to Django
        django_user, _ = update_or_create_clerk_user(clerk_user.id)

        # 3. Verify user properties
        assert django_user.email is None
        assert django_user.username == "fullflow_username"
        assert str(django_user) == "fullflow_username"

        # 4. Retrieve by clerk_id
        retrieved = get_clerk_user(clerk_user.id)
        assert retrieved is not None
        assert retrieved.username == "fullflow_username"

        # 5. Retrieve by username using manager
        by_username = User.objects.get_by_username("fullflow_username")
        assert by_username is not None
        assert by_username.pk == django_user.pk

    @pytest.mark.skip(reason="Requires Clerk instance configured to allow username-only users")
    def test_user_display_methods(self, db, clerk_client, created_users):
        """Test __str__ and get_short_name for various user types.

        Note: This test requires the Clerk instance to have email set as optional
        because it tests username-only users.
        """
        from django_clerk_users.utils import update_or_create_clerk_user

        # Email user
        email_user_clerk = clerk_client.create_test_user(first_name="")
        created_users.append(email_user_clerk.id)
        email_user, _ = update_or_create_clerk_user(email_user_clerk.id)
        assert str(email_user) == email_user.email
        assert email_user.get_short_name() == email_user.email.split("@")[0]

        # Username-only user
        username_user_clerk = clerk_client.create_test_user(
            skip_email=True,
            username="display_test",
            first_name="",
        )
        created_users.append(username_user_clerk.id)
        username_user, _ = update_or_create_clerk_user(username_user_clerk.id)
        assert str(username_user) == "display_test"
        assert username_user.get_short_name() == "display_test"

        # User with first_name
        named_user_clerk = clerk_client.create_test_user(first_name="Alice")
        created_users.append(named_user_clerk.id)
        named_user, _ = update_or_create_clerk_user(named_user_clerk.id)
        assert named_user.get_short_name() == "Alice"
