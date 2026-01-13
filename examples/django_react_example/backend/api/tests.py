"""
Example tests demonstrating django-clerk-users testing utilities.

These tests show how to create test users via Clerk's Backend API
for integration testing authenticated endpoints.

Prerequisites:
    - CLERK_SECRET_KEY must be set (uses real Clerk development instance)
    - Your Clerk instance must have test mode enabled (default for development)

See: https://clerk.com/docs/testing/overview
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from django_clerk_users.testing import (
    TEST_OTP_CODE,
    ClerkTestClient,
    ClerkTestMixin,
    TestUserData,
    make_test_email,
    make_test_phone,
)


class TestEmailPhoneHelpers(TestCase):
    """Test the email and phone helper functions."""

    def test_make_test_email_default(self):
        """Test generating a default test email."""
        email = make_test_email()
        self.assertIn("+clerk_test", email)
        self.assertIn("@example.com", email)
        self.assertTrue(email.startswith("testuser+clerk_test_"))

    def test_make_test_email_custom(self):
        """Test generating a custom test email."""
        email = make_test_email(base="admin", domain="myapp.com")
        self.assertIn("+clerk_test", email)
        self.assertIn("@myapp.com", email)
        self.assertTrue(email.startswith("admin+clerk_test_"))

    def test_make_test_email_unique(self):
        """Test that generated emails are unique."""
        emails = [make_test_email() for _ in range(10)]
        self.assertEqual(len(emails), len(set(emails)))

    def test_make_test_phone_default(self):
        """Test generating a default test phone."""
        phone = make_test_phone()
        self.assertEqual(phone, "+12015550100")

    def test_make_test_phone_custom_area(self):
        """Test generating a test phone with custom area code."""
        phone = make_test_phone(area_code="415", suffix=42)
        self.assertEqual(phone, "+14155550142")

    def test_make_test_phone_suffix_clamped(self):
        """Test that phone suffix is clamped to 0-99."""
        self.assertEqual(make_test_phone(suffix=-1), "+12015550100")
        self.assertEqual(make_test_phone(suffix=100), "+12015550199")

    def test_otp_code_constant(self):
        """Test the OTP code constant."""
        self.assertEqual(TEST_OTP_CODE, "424242")


class TestClerkTestClientMocked(TestCase):
    """Test ClerkTestClient with mocked Clerk API."""

    def setUp(self):
        """Set up mock Clerk client."""
        self.mock_clerk = MagicMock()
        self.client = ClerkTestClient(clerk_client=self.mock_clerk)

    def test_create_test_user(self):
        """Test creating a test user."""
        # Mock response
        mock_user = MagicMock()
        mock_user.id = "user_test123"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.email_addresses = [{"email_address": "test+clerk_test@example.com"}]
        mock_user.phone_numbers = []
        self.mock_clerk.users.create.return_value = mock_user

        user = self.client.create_test_user(email="test+clerk_test@example.com")

        self.assertEqual(user.id, "user_test123")
        self.assertEqual(user.first_name, "Test")
        self.mock_clerk.users.create.assert_called_once()

    def test_create_session(self):
        """Test creating a session."""
        mock_session = MagicMock()
        mock_session.id = "sess_test123"
        mock_session.user_id = "user_test123"
        self.mock_clerk.sessions.create.return_value = mock_session

        session = self.client.create_session("user_test123")

        self.assertEqual(session["id"], "sess_test123")
        self.mock_clerk.sessions.create.assert_called_once_with(user_id="user_test123")

    def test_get_session_token(self):
        """Test getting a session token."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.id = "sess_test123"
        mock_session.user_id = "user_test123"
        self.mock_clerk.sessions.create.return_value = mock_session

        # Mock token creation
        mock_token = MagicMock()
        mock_token.jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
        self.mock_clerk.sessions.create_session_token.return_value = mock_token

        token = self.client.get_session_token("user_test123")

        self.assertEqual(token, "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...")

    def test_delete_user(self):
        """Test deleting a user."""
        result = self.client.delete_user("user_test123")

        self.assertTrue(result)
        self.mock_clerk.users.delete.assert_called_once_with(user_id="user_test123")

    def test_delete_user_failure(self):
        """Test handling delete failure."""
        self.mock_clerk.users.delete.side_effect = Exception("API Error")

        result = self.client.delete_user("user_test123")

        self.assertFalse(result)


class TestUserDataParsing(TestCase):
    """Test TestUserData parsing."""

    def test_from_dict_response(self):
        """Test parsing from dict response."""
        response = {
            "id": "user_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "email_addresses": [{"email_address": "jane@example.com"}],
            "phone_numbers": [{"phone_number": "+15551234567"}],
        }

        user = TestUserData.from_clerk_response(response)

        self.assertEqual(user.id, "user_123")
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.email, "jane@example.com")
        self.assertEqual(user.phone_number, "+15551234567")

    def test_from_object_response(self):
        """Test parsing from object response."""
        response = MagicMock()
        response.id = "user_456"
        response.first_name = "John"
        response.last_name = "Smith"
        response.email_addresses = [{"email_address": "john@example.com"}]
        response.phone_numbers = None

        user = TestUserData.from_clerk_response(response)

        self.assertEqual(user.id, "user_456")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.email, "john@example.com")
        self.assertIsNone(user.phone_number)


# =============================================================================
# Integration Tests (require real Clerk API)
# =============================================================================
# Uncomment these tests when running against a real Clerk development instance.
# Make sure CLERK_SECRET_KEY is set to your development instance key.

# class TestClerkTestClientIntegration(TestCase):
#     """
#     Integration tests using real Clerk API.
#
#     These tests require:
#     - CLERK_SECRET_KEY environment variable set
#     - A Clerk development instance with test mode enabled
#     """
#
#     @classmethod
#     def setUpClass(cls):
#         super().setUpClass()
#         cls.clerk_client = ClerkTestClient()
#         cls.created_users = []
#
#     @classmethod
#     def tearDownClass(cls):
#         # Clean up all created users
#         for user_id in cls.created_users:
#             cls.clerk_client.delete_user(user_id)
#         super().tearDownClass()
#
#     def test_create_and_authenticate_user(self):
#         """Test full flow: create user, get token, make request."""
#         # Create a test user
#         user = self.clerk_client.create_test_user(
#             first_name="Integration",
#             last_name="Test"
#         )
#         self.created_users.append(user.id)
#
#         # Get a session token
#         token = self.clerk_client.get_session_token(user.id)
#         self.assertTrue(token.startswith("eyJ"))  # JWT format
#
#         # Make authenticated request
#         response = self.client.get(
#             "/api/protected/",
#             HTTP_AUTHORIZATION=f"Bearer {token}"
#         )
#         self.assertEqual(response.status_code, 200)


# class TestProtectedEndpointIntegration(ClerkTestMixin, TestCase):
#     """
#     Example using ClerkTestMixin for cleaner test setup.
#
#     The mixin automatically:
#     - Creates a test user in setUp()
#     - Provides self.test_user and self.session_token
#     - Cleans up users in tearDown()
#     """
#
#     def test_protected_view_authenticated(self):
#         """Test accessing protected view with valid token."""
#         response = self.client.get(
#             "/api/protected/",
#             **self.get_auth_header()
#         )
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertIn("user", data)
#
#     def test_protected_view_unauthenticated(self):
#         """Test accessing protected view without token."""
#         response = self.client.get("/api/protected/")
#         self.assertEqual(response.status_code, 401)
#
#     def test_user_profile_view(self):
#         """Test user profile endpoint."""
#         response = self.client.get(
#             "/api/profile/",
#             **self.get_auth_header()
#         )
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertEqual(data["profile"]["first_name"], "Test")
#
#     def test_multiple_users(self):
#         """Test with multiple test users."""
#         # Create another user
#         admin_user = self.create_test_user(
#             email=make_test_email(base="admin"),
#             first_name="Admin",
#             last_name="User"
#         )
#
#         # Get profile for admin user
#         response = self.client.get(
#             "/api/profile/",
#             **self.get_auth_header(admin_user)
#         )
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertEqual(data["profile"]["first_name"], "Admin")
