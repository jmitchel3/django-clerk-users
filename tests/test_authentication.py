"""
Tests for django-clerk-users authentication backend.
"""

import pytest
from django.contrib.auth import get_user_model

from django_clerk_users.authentication.backends import ClerkBackend


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_auth123",
        email="auth@example.com",
        first_name="Auth",
        last_name="User",
    )


@pytest.fixture
def inactive_user(db):
    """Create an inactive user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_inactive",
        email="inactive@example.com",
        is_active=False,
    )


@pytest.fixture
def backend():
    """Create a ClerkBackend instance."""
    return ClerkBackend()


class TestClerkBackend:
    """Test ClerkBackend authentication."""

    def test_authenticate_with_clerk_id(self, backend, clerk_user):
        """Test authentication with valid clerk_id."""
        user = backend.authenticate(request=None, clerk_id="user_auth123")
        assert user == clerk_user

    def test_authenticate_without_clerk_id(self, backend, clerk_user):
        """Test authentication without clerk_id returns None."""
        user = backend.authenticate(request=None)
        assert user is None

    def test_authenticate_with_empty_clerk_id(self, backend, clerk_user):
        """Test authentication with empty clerk_id returns None."""
        user = backend.authenticate(request=None, clerk_id="")
        assert user is None

    def test_authenticate_nonexistent_user(self, backend, db):
        """Test authentication with nonexistent clerk_id returns None."""
        user = backend.authenticate(request=None, clerk_id="nonexistent")
        assert user is None

    def test_authenticate_inactive_user(self, backend, inactive_user):
        """Test authentication with inactive user returns None."""
        user = backend.authenticate(request=None, clerk_id="user_inactive")
        assert user is None

    def test_get_user_by_pk(self, backend, clerk_user):
        """Test getting user by primary key."""
        user = backend.get_user(clerk_user.pk)
        assert user == clerk_user

    def test_get_user_nonexistent(self, backend, db):
        """Test getting nonexistent user returns None."""
        user = backend.get_user(99999)
        assert user is None

    def test_get_user_inactive(self, backend, inactive_user):
        """Test getting inactive user returns None."""
        user = backend.get_user(inactive_user.pk)
        assert user is None


class TestBearerToken:
    """Test bearer token extraction."""

    def test_get_bearer_token_valid(self):
        """Test extracting valid bearer token."""
        from django_clerk_users.authentication.utils import get_bearer_token
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.headers = {"Authorization": "Bearer test_token_123"}

        token = get_bearer_token(request)
        assert token == "test_token_123"

    def test_get_bearer_token_missing(self):
        """Test missing authorization header."""
        from django_clerk_users.authentication.utils import get_bearer_token
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        token = get_bearer_token(request)
        assert token is None

    def test_get_bearer_token_wrong_scheme(self):
        """Test non-bearer authorization header."""
        from django_clerk_users.authentication.utils import get_bearer_token
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.headers = {"Authorization": "Basic abc123"}

        token = get_bearer_token(request)
        assert token is None


class TestGetUserFromClerkId:
    """Test get_user_from_clerk_id utility."""

    def test_get_existing_user(self, clerk_user):
        """Test getting an existing user."""
        from django_clerk_users.authentication.utils import get_user_from_clerk_id

        user = get_user_from_clerk_id("user_auth123")
        assert user == clerk_user

    def test_get_nonexistent_user(self, db):
        """Test getting a nonexistent user."""
        from django_clerk_users.authentication.utils import get_user_from_clerk_id

        user = get_user_from_clerk_id("nonexistent")
        assert user is None
