"""
Tests for django_clerk_users.testing module.
"""

from unittest.mock import MagicMock, patch

import pytest


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


class TestTestUserData:
    """Test TestUserData parsing."""

    def test_from_dict_response(self):
        """Test parsing from dict response."""
        from django_clerk_users.testing import TestUserData

        response = {
            "id": "user_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "email_addresses": [{"email_address": "jane@example.com"}],
            "phone_numbers": [{"phone_number": "+15551234567"}],
        }

        user = TestUserData.from_clerk_response(response)

        assert user.id == "user_123"
        assert user.first_name == "Jane"
        assert user.last_name == "Doe"
        assert user.email == "jane@example.com"
        assert user.phone_number == "+15551234567"

    def test_from_object_response(self):
        """Test parsing from object response."""
        from django_clerk_users.testing import TestUserData

        response = MagicMock()
        response.id = "user_456"
        response.first_name = "John"
        response.last_name = "Smith"
        response.email_addresses = [{"email_address": "john@example.com"}]
        response.phone_numbers = None

        user = TestUserData.from_clerk_response(response)

        assert user.id == "user_456"
        assert user.first_name == "John"
        assert user.email == "john@example.com"
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
        mock_user.email_addresses = [{"email_address": "test+clerk_test@example.com"}]
        mock_user.phone_numbers = []
        mock_clerk.users.create.return_value = mock_user

        user = client.create_test_user(email="test+clerk_test@example.com")

        assert user.id == "user_test123"
        assert user.first_name == "Test"
        mock_clerk.users.create.assert_called_once()

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
        mock_clerk.sessions.create.assert_called_once_with(user_id="user_test123")

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
        mock_clerk.sessions.create_session_token.return_value = mock_token

        token = client.get_session_token("user_test123")

        assert token == "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

    def test_delete_user(self):
        """Test deleting a user."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        client = ClerkTestClient(clerk_client=mock_clerk)

        result = client.delete_user("user_test123")

        assert result is True
        mock_clerk.users.delete.assert_called_once_with(user_id="user_test123")

    def test_delete_user_failure(self):
        """Test handling delete failure."""
        from django_clerk_users.testing import ClerkTestClient

        mock_clerk = MagicMock()
        mock_clerk.users.delete.side_effect = Exception("API Error")
        client = ClerkTestClient(clerk_client=mock_clerk)

        result = client.delete_user("user_test123")

        assert result is False


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
