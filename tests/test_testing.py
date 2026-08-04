"""
Tests for django_clerk_users.testing module.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestTestingHelpers:
    """Test the testing helper functions."""

    def test_make_test_email_default(self):
        """Test generating a default test email."""
        from django_clerk_users.testing import make_test_email

        email = make_test_email()
        assert "+clerk_test" in email
        assert "@example.com" in email
        assert email.startswith("testuser+clerk_test_")

    def test_make_test_email_custom(self):
        """Test generating a custom test email."""
        from django_clerk_users.testing import make_test_email

        email = make_test_email(base="admin", domain="myapp.com")
        assert "+clerk_test" in email
        assert "@myapp.com" in email
        assert email.startswith("admin+clerk_test_")

    def test_make_test_email_unique(self):
        """Test that generated emails are unique."""
        from django_clerk_users.testing import make_test_email

        emails = [make_test_email() for _ in range(10)]
        assert len(emails) == len(set(emails))

    def test_make_test_phone_default(self):
        """Test generating a default test phone."""
        from django_clerk_users.testing import make_test_phone

        phone = make_test_phone()
        assert phone == "+12015550100"

    def test_make_test_phone_custom(self):
        """Test generating a custom test phone."""
        from django_clerk_users.testing import make_test_phone

        phone = make_test_phone(area_code="415", suffix=42)
        assert phone == "+14155550142"

    def test_make_test_phone_suffix_clamped(self):
        """Test that phone suffix is clamped to 0-99."""
        from django_clerk_users.testing import make_test_phone

        assert make_test_phone(suffix=-1) == "+12015550100"
        assert make_test_phone(suffix=100) == "+12015550199"

    def test_otp_code_constant(self):
        """Test the OTP code constant."""
        from django_clerk_users.testing import TEST_OTP_CODE

        assert TEST_OTP_CODE == "424242"

    def test_make_test_username_default(self):
        """Test generating a default test username."""
        from django_clerk_users.testing import make_test_username

        username = make_test_username()
        assert username.startswith("testuser_")
        assert len(username) == len("testuser_") + 8  # 8 char unique suffix

    def test_make_test_username_custom_prefix(self):
        """Test generating a test username with custom prefix."""
        from django_clerk_users.testing import make_test_username

        username = make_test_username(prefix="admin")
        assert username.startswith("admin_")

    def test_make_test_username_unique(self):
        """Test that generated usernames are unique."""
        from django_clerk_users.testing import make_test_username

        usernames = [make_test_username() for _ in range(10)]
        assert len(usernames) == len(set(usernames))


class TestTestUserData:
    """Test TestUserData parsing."""

    def test_from_dict_response(self):
        """Test parsing from dict response."""
        from django_clerk_users.testing import TestUserData

        response = {
            "id": "user_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "username": "janedoe",
            "email_addresses": [{"email_address": "jane@example.com"}],
            "phone_numbers": [{"phone_number": "+15551234567"}],
        }

        user = TestUserData.from_clerk_response(response)

        assert user.id == "user_123"
        assert user.first_name == "Jane"
        assert user.last_name == "Doe"
        assert user.username == "janedoe"
        assert user.email == "jane@example.com"
        assert user.phone_number == "+15551234567"

    def test_from_dict_response_username_only(self):
        """Test parsing from dict response with username but no email."""
        from django_clerk_users.testing import TestUserData

        response = {
            "id": "user_789",
            "first_name": "Test",
            "last_name": "User",
            "username": "usernameonly",
            "email_addresses": [],
            "phone_numbers": [],
        }

        user = TestUserData.from_clerk_response(response)

        assert user.id == "user_789"
        assert user.username == "usernameonly"
        assert user.email is None
        assert user.phone_number is None

    def test_from_object_response(self):
        """Test parsing from object response."""
        from django_clerk_users.testing import TestUserData

        response = MagicMock()
        response.id = "user_456"
        response.first_name = "John"
        response.last_name = "Smith"
        response.username = "johnsmith"
        response.email_addresses = [{"email_address": "john@example.com"}]
        response.phone_numbers = None

        user = TestUserData.from_clerk_response(response)

        assert user.id == "user_456"
        assert user.first_name == "John"
        assert user.username == "johnsmith"
        assert user.email == "john@example.com"
        assert user.phone_number is None

    def test_from_object_response_username_only(self):
        """Test parsing from object response with username but no email."""
        from django_clerk_users.testing import TestUserData

        response = MagicMock()
        response.id = "user_abc"
        response.first_name = "Test"
        response.last_name = "User"
        response.username = "testusername"
        response.email_addresses = []
        response.phone_numbers = []

        user = TestUserData.from_clerk_response(response)

        assert user.id == "user_abc"
        assert user.username == "testusername"
        assert user.email is None
        assert user.phone_number is None


class TestClerkTestClient:
    """Test ClerkTestClient with mocked Clerk API."""

    def test_create_test_user(self):
        """Test creating a test user."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        # Mock response
        mock_user = MagicMock()
        mock_user.id = "user_test123"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.username = None
        mock_user.email_addresses = [{"email_address": "test+clerk_test@example.com"}]
        mock_user.phone_numbers = []
        mock_clerk.users.create.return_value = mock_user

        user = client.create_test_user(email="test+clerk_test@example.com")

        assert user.id == "user_test123"
        assert user.first_name == "Test"
        mock_clerk.users.create.assert_called_once()

    def test_create_test_user_with_username(self):
        """Test creating a test user with username."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        mock_user = MagicMock()
        mock_user.id = "user_username123"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.username = "testusername"
        mock_user.email_addresses = [{"email_address": "test+clerk_test@example.com"}]
        mock_user.phone_numbers = []
        mock_clerk.users.create.return_value = mock_user

        user = client.create_test_user(username="testusername")

        assert user.id == "user_username123"
        assert user.username == "testusername"
        # Should be called with username parameter
        call_kwargs = mock_clerk.users.create.call_args[1]
        assert call_kwargs["username"] == "testusername"

    def test_create_username_only_user(self):
        """Test creating a username-only user (no email)."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        mock_user = MagicMock()
        mock_user.id = "user_usernameonly"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.username = "usernameonly"
        mock_user.email_addresses = []
        mock_user.phone_numbers = []
        mock_clerk.users.create.return_value = mock_user

        user = client.create_test_user(skip_email=True, username="usernameonly")

        assert user.id == "user_usernameonly"
        assert user.username == "usernameonly"
        assert user.email is None
        # Should NOT have email_address in call
        call_kwargs = mock_clerk.users.create.call_args[1]
        assert "email_address" not in call_kwargs
        assert call_kwargs["username"] == "usernameonly"

    def test_create_username_only_user_auto_username(self):
        """Test creating a username-only user with auto-generated username."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        mock_user = MagicMock()
        mock_user.id = "user_auto"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.username = "testuser_abc12345"
        mock_user.email_addresses = []
        mock_user.phone_numbers = []
        mock_clerk.users.create.return_value = mock_user

        client.create_test_user(skip_email=True)

        # Should have auto-generated a username
        call_kwargs = mock_clerk.users.create.call_args[1]
        assert "username" in call_kwargs
        assert call_kwargs["username"].startswith("testuser_")

    def test_create_session(self):
        """Test creating a session."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        mock_session = MagicMock()
        mock_session.id = "sess_test123"
        mock_session.user_id = "user_test123"
        mock_clerk.sessions.create.return_value = mock_session

        session = client.create_session("user_test123")

        assert session["id"] == "sess_test123"
        mock_clerk.sessions.create.assert_called_once_with(
            request={"user_id": "user_test123"},
            timeout_ms=10000,
        )

    def test_get_session_token(self):
        """Test getting a session token."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        # Mock session creation
        mock_session = MagicMock()
        mock_session.id = "sess_test123"
        mock_session.user_id = "user_test123"
        mock_clerk.sessions.create.return_value = mock_session

        # Mock token creation
        mock_token = MagicMock()
        mock_token.jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
        mock_clerk.sessions.create_token.return_value = mock_token

        token = client.get_session_token("user_test123")

        assert token == "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

    def test_delete_user(self):
        """Test deleting a user."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        result = client.delete_user("user_test123")

        assert result is True
        mock_clerk.users.delete.assert_called_once_with(
            user_id="user_test123",
            timeout_ms=10000,
        )

    def test_delete_user_failure(self):
        """Test handling delete failure."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        mock_clerk.users.delete.side_effect = Exception("API Error")
        client = ClerkTestClient(clerk_client=mock_clerk)

        result = client.delete_user("user_test123")

        assert result is False

    def test_client_is_loaded_lazily(self):
        from django_clerk_users.testing import ClerkTestClient

        configured_client = MagicMock()
        client = ClerkTestClient()

        with patch(
            "django_clerk_users.testing.get_clerk_client",
            return_value=configured_client,
        ) as get_client:
            assert client.client is configured_client
            assert client.client is configured_client

        get_client.assert_called_once_with()

    def test_create_user_accepts_explicit_email_password_and_phone_without_auto_email(
        self,
    ):
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user_explicit"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.username = "explicit"
        mock_user.email_addresses = [{"email_address": "explicit@example.com"}]
        mock_user.phone_numbers = [{"phone_number": "+12015550123"}]
        mock_clerk.users.create.return_value = mock_user

        user = ClerkTestClient(clerk_client=mock_clerk).create_test_user(
            email="explicit@example.com",
            username="explicit",
            password="secret",
            phone_number="+12015550123",
            skip_email=True,
            public_metadata={"role": "tester"},
        )

        assert user.id == "user_explicit"
        assert mock_clerk.users.create.call_args.kwargs == {
            "first_name": "Test",
            "last_name": "User",
            "public_metadata": {"role": "tester"},
            "email_address": ["explicit@example.com"],
            "username": "explicit",
            "password": "secret",
            "phone_number": ["+12015550123"],
            "timeout_ms": 10000,
        }

    def test_create_session_returns_mapping_response_unchanged(self):
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        response = {"id": "sess_mapping", "user_id": "user_123"}
        mock_clerk.sessions.create.return_value = response

        assert (
            ClerkTestClient(clerk_client=mock_clerk).create_session("user_123")
            is response
        )

    def test_get_session_token_uses_existing_session_and_mapping_response(self):
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        mock_clerk.sessions.create_token.return_value = {"jwt": "mapping-token"}
        client = ClerkTestClient(clerk_client=mock_clerk)

        assert (
            client.get_session_token("user_123", session_id="sess_existing")
            == "mapping-token"
        )
        mock_clerk.sessions.create.assert_not_called()
        mock_clerk.sessions.create_token.assert_called_once_with(
            session_id="sess_existing", timeout_ms=10000
        )

    def test_get_testing_token_supports_object_and_mapping_responses(self):
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)
        mock_clerk.testing_tokens.create.side_effect = [
            SimpleNamespace(token="object-token"),
            {"token": "mapping-token"},
        ]

        assert client.get_testing_token() == "object-token"
        assert client.get_testing_token() == "mapping-token"


def test_clerk_test_mixin_manages_users_tokens_and_parent_hooks():
    from django_clerk_users.testing import ClerkTestMixin

    events = []

    class Parent:
        def setUp(self):
            events.append("parent-setup")

        def tearDown(self):
            events.append("parent-teardown")

    class Harness(ClerkTestMixin, Parent):
        pass

    default_user = SimpleNamespace(id="user_default")
    extra_user = SimpleNamespace(id="user_extra")
    explicit_user = SimpleNamespace(id="user_explicit")
    mock_client = MagicMock()
    mock_client.create_test_user.side_effect = [default_user, extra_user]
    mock_client.get_session_token.side_effect = ["default-token", "explicit-token"]

    with patch("django_clerk_users.testing.ClerkTestClient", return_value=mock_client):
        harness = Harness()
        harness.setUp()
        assert harness.test_user is default_user
        assert harness.session_token == "default-token"
        assert harness.get_auth_header() == {
            "HTTP_AUTHORIZATION": "Bearer default-token"
        }
        assert harness.get_auth_header(explicit_user) == {
            "HTTP_AUTHORIZATION": "Bearer explicit-token"
        }
        assert harness.create_test_user(role="admin") is extra_user
        harness.tearDown()

    assert events == ["parent-setup", "parent-teardown"]
    assert harness._created_users == ["user_default", "user_extra"]
    assert mock_client.delete_user.call_args_list == [
        (("user_default",), {}),
        (("user_extra",), {}),
    ]


class TestPackageExports:
    """Test that testing utilities are exported from main package."""

    def test_import_clerk_test_client(self):
        """Test importing ClerkTestClient from main package."""
        from django_clerk_users import ClerkTestClient

        assert ClerkTestClient is not None

    def test_import_make_test_email(self):
        """Test importing make_test_email from main package."""
        from django_clerk_users import make_test_email

        assert callable(make_test_email)

    def test_import_make_test_phone(self):
        """Test importing make_test_phone from main package."""
        from django_clerk_users import make_test_phone

        assert callable(make_test_phone)

    def test_import_make_test_username(self):
        """Test importing make_test_username from main package."""
        from django_clerk_users import make_test_username

        assert callable(make_test_username)

    def test_import_test_otp_code(self):
        """Test importing TEST_OTP_CODE from main package."""
        from django_clerk_users import TEST_OTP_CODE

        assert TEST_OTP_CODE == "424242"

    def test_import_test_user_data(self):
        """Test importing TestUserData from main package."""
        from django_clerk_users import TestUserData

        assert TestUserData is not None

    def test_import_clerk_test_mixin(self):
        """Test importing ClerkTestMixin from main package."""
        from django_clerk_users import ClerkTestMixin

        assert ClerkTestMixin is not None
