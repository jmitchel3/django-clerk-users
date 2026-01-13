"""
Testing utilities for django-clerk-users.

Provides helpers for creating test users via Clerk's Backend API,
useful for integration testing and local development.

See: https://clerk.com/docs/testing/overview

Usage:
    from django_clerk_users.testing import ClerkTestClient

    # In your test setup
    client = ClerkTestClient()
    user_data = client.create_test_user(email="test+clerk_test@example.com")
    token = client.get_session_token(user_data["id"])

    # Make authenticated requests
    response = self.client.get(
        "/api/protected/",
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

Test Email/Phone Patterns:
    - Test emails: Use `+clerk_test` suffix (e.g., "jane+clerk_test@example.com")
    - Test phones: Use `+1 (XXX) 555-0100` through `+1 (XXX) 555-0199`
    - Fixed OTP code for both: 424242
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django_clerk_users.client import get_clerk_client

if TYPE_CHECKING:
    from clerk_backend_api import Clerk


# Test mode constants
TEST_OTP_CODE = "424242"
TEST_EMAIL_SUFFIX = "+clerk_test"
TEST_PHONE_PREFIX = "+1"
TEST_PHONE_PATTERN = "555-01"  # 555-0100 through 555-0199


def make_test_email(base: str = "testuser", domain: str = "example.com") -> str:
    """
    Generate a test email address with the +clerk_test suffix.

    These emails won't trigger actual email delivery in test mode
    and use the fixed OTP code 424242.

    Args:
        base: The base username (default: "testuser")
        domain: The email domain (default: "example.com")

    Returns:
        A test email like "testuser+clerk_test@example.com"
    """
    unique_id = uuid.uuid4().hex[:8]
    return f"{base}+clerk_test_{unique_id}@{domain}"


def make_test_phone(area_code: str = "201", suffix: int = 0) -> str:
    """
    Generate a test phone number using Clerk's reserved test range.

    These phone numbers won't trigger actual SMS delivery in test mode
    and use the fixed OTP code 424242.

    Args:
        area_code: US area code (default: "201")
        suffix: Number from 0-99 for the 555-01XX range (default: 0)

    Returns:
        A test phone like "+12015550100"
    """
    suffix = max(0, min(99, suffix))  # Clamp to 0-99
    return f"+1{area_code}55501{suffix:02d}"


@dataclass
class TestUserData:
    """Data returned when creating a test user."""

    id: str
    email: str | None
    first_name: str | None
    last_name: str | None
    phone_number: str | None
    raw_response: dict[str, Any]

    @classmethod
    def from_clerk_response(cls, response: Any) -> "TestUserData":
        """Create TestUserData from a Clerk API response."""
        # Handle both dict and object responses
        if hasattr(response, "id"):
            return cls(
                id=response.id,
                email=getattr(response, "email_addresses", [{}])[0].get("email_address")
                if getattr(response, "email_addresses", None)
                else None,
                first_name=getattr(response, "first_name", None),
                last_name=getattr(response, "last_name", None),
                phone_number=getattr(response, "phone_numbers", [{}])[0].get(
                    "phone_number"
                )
                if getattr(response, "phone_numbers", None)
                else None,
                raw_response=response.__dict__
                if hasattr(response, "__dict__")
                else {},
            )
        else:
            # Dict response
            return cls(
                id=response.get("id", ""),
                email=response.get("email_addresses", [{}])[0].get("email_address"),
                first_name=response.get("first_name"),
                last_name=response.get("last_name"),
                phone_number=response.get("phone_numbers", [{}])[0].get("phone_number")
                if response.get("phone_numbers")
                else None,
                raw_response=response,
            )


class ClerkTestClient:
    """
    Client for creating test users and sessions via Clerk's Backend API.

    This client wraps Clerk's Backend API to provide convenient methods
    for testing scenarios. It's designed for use in development and test
    environments only.

    Example:
        client = ClerkTestClient()

        # Create a test user
        user = client.create_test_user()

        # Get a session token for authenticated requests
        token = client.get_session_token(user.id)

        # Use in Django test client
        response = self.client.get(
            "/api/protected/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        # Cleanup after test
        client.delete_user(user.id)
    """

    def __init__(self, clerk_client: "Clerk | None" = None):
        """
        Initialize the test client.

        Args:
            clerk_client: Optional Clerk client instance. If not provided,
                          uses the configured client from django settings.
        """
        self._client = clerk_client

    @property
    def client(self) -> "Clerk":
        """Get the Clerk client, initializing if needed."""
        if self._client is None:
            self._client = get_clerk_client()
        return self._client

    def create_test_user(
        self,
        email: str | None = None,
        first_name: str = "Test",
        last_name: str = "User",
        password: str | None = None,
        phone_number: str | None = None,
        **kwargs: Any,
    ) -> TestUserData:
        """
        Create a test user via Clerk's Backend API.

        Args:
            email: Email address. If None, generates a test email.
            first_name: User's first name (default: "Test")
            last_name: User's last name (default: "User")
            password: Optional password. If not provided, user is passwordless.
            phone_number: Optional phone number for SMS auth.
            **kwargs: Additional fields to pass to Clerk API.

        Returns:
            TestUserData with the created user's information.

        Example:
            # Create user with auto-generated test email
            user = client.create_test_user()

            # Create user with specific email (use +clerk_test for test mode)
            user = client.create_test_user(email="admin+clerk_test@example.com")

            # Create user with password for email/password auth
            user = client.create_test_user(password="testpass123")
        """
        if email is None:
            email = make_test_email()

        create_params: dict[str, Any] = {
            "email_address": [email],
            "first_name": first_name,
            "last_name": last_name,
            **kwargs,
        }

        if password:
            create_params["password"] = password

        if phone_number:
            create_params["phone_number"] = [phone_number]

        response = self.client.users.create(**create_params)
        return TestUserData.from_clerk_response(response)

    def create_session(self, user_id: str) -> dict[str, Any]:
        """
        Create a session for a user.

        Args:
            user_id: The Clerk user ID.

        Returns:
            Session data including the session ID.
        """
        response = self.client.sessions.create(user_id=user_id)
        if hasattr(response, "__dict__"):
            return {"id": response.id, "user_id": response.user_id}
        return response

    def get_session_token(self, user_id: str, session_id: str | None = None) -> str:
        """
        Get a session token for making authenticated API requests.

        Creates a session if session_id is not provided, then generates
        a session token.

        Note: Clerk session tokens are short-lived (60 seconds). For longer
        tests, you may need to refresh the token.

        Args:
            user_id: The Clerk user ID.
            session_id: Optional existing session ID. If not provided,
                       creates a new session.

        Returns:
            A JWT session token for use in Authorization header.

        Example:
            token = client.get_session_token(user.id)
            response = requests.get(
                "http://localhost:8000/api/protected/",
                headers={"Authorization": f"Bearer {token}"}
            )
        """
        if session_id is None:
            session = self.create_session(user_id)
            session_id = session["id"]

        response = self.client.sessions.create_session_token(session_id=session_id)

        if hasattr(response, "jwt"):
            return response.jwt
        return response.get("jwt", "")

    def delete_user(self, user_id: str) -> bool:
        """
        Delete a test user.

        Call this in test teardown to clean up created users.

        Args:
            user_id: The Clerk user ID to delete.

        Returns:
            True if deletion was successful.
        """
        try:
            self.client.users.delete(user_id=user_id)
            return True
        except Exception:
            return False

    def get_testing_token(self) -> str:
        """
        Get a testing token for bypassing bot detection.

        Testing tokens are used to bypass Clerk's bot detection when
        making Frontend API requests during automated testing.

        Returns:
            A testing token string.

        See: https://clerk.com/docs/testing/testing-tokens
        """
        response = self.client.testing_tokens.create()
        if hasattr(response, "token"):
            return response.token
        return response.get("token", "")


class ClerkTestMixin:
    """
    Mixin for Django TestCase classes that need Clerk test users.

    Provides setUp/tearDown helpers for creating and cleaning up test users.

    Example:
        from django.test import TestCase
        from django_clerk_users.testing import ClerkTestMixin

        class MyAPITestCase(ClerkTestMixin, TestCase):
            def test_protected_endpoint(self):
                # self.test_user and self.session_token are available
                response = self.client.get(
                    "/api/protected/",
                    HTTP_AUTHORIZATION=f"Bearer {self.session_token}"
                )
                self.assertEqual(response.status_code, 200)
    """

    clerk_test_client: ClerkTestClient
    test_user: TestUserData
    session_token: str
    _created_users: list[str]

    def setUp(self) -> None:
        """Set up test fixtures including a test user."""
        super().setUp()  # type: ignore[misc]
        self.clerk_test_client = ClerkTestClient()
        self._created_users = []

        # Create a default test user
        self.test_user = self.create_test_user()
        self.session_token = self.clerk_test_client.get_session_token(self.test_user.id)

    def tearDown(self) -> None:
        """Clean up created test users."""
        for user_id in self._created_users:
            self.clerk_test_client.delete_user(user_id)
        super().tearDown()  # type: ignore[misc]

    def create_test_user(self, **kwargs: Any) -> TestUserData:
        """
        Create a test user and track it for cleanup.

        Args:
            **kwargs: Arguments to pass to ClerkTestClient.create_test_user()

        Returns:
            TestUserData for the created user.
        """
        user = self.clerk_test_client.create_test_user(**kwargs)
        self._created_users.append(user.id)
        return user

    def get_auth_header(self, user: TestUserData | None = None) -> dict[str, str]:
        """
        Get an Authorization header dict for a user.

        Args:
            user: The user to get a token for. Defaults to self.test_user.

        Returns:
            Dict with HTTP_AUTHORIZATION key for use with Django test client.
        """
        if user is None:
            return {"HTTP_AUTHORIZATION": f"Bearer {self.session_token}"}

        token = self.clerk_test_client.get_session_token(user.id)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
