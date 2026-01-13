"""
Tests for hybrid authentication (Clerk + Django admin).
"""

import time
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory

from django_clerk_users.middleware.auth import ClerkAuthMiddleware


@pytest.fixture
def request_factory():
    """Create a request factory."""
    return RequestFactory()


@pytest.fixture
def clerk_user(db):
    """Create a Clerk-authenticated user."""
    User = get_user_model()
    return User.objects.create(
        clerk_id="user_clerk123",
        email="clerk@example.com",
        first_name="Clerk",
        last_name="User",
        is_active=True,
    )


@pytest.fixture
def admin_user(db):
    """Create a Django admin user (no clerk_id)."""
    User = get_user_model()
    user = User.objects.create_user(
        email="admin@example.com",
        password="admin123",
        first_name="Admin",
        last_name="User",
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    return user


@pytest.fixture
def middleware():
    """Create middleware instance."""

    def get_response(request):
        return HttpResponse("OK")

    return ClerkAuthMiddleware(get_response)


def make_request_with_session(request_factory):
    """Create a request with a session."""
    request = request_factory.get("/")
    request.session = SessionStore()
    request.user = AnonymousUser()
    return request


@pytest.mark.django_db
class TestHybridAuthentication:
    """Test hybrid authentication (Clerk + Django admin)."""

    def test_django_admin_session_not_overridden(self, request_factory, admin_user):
        """Test that existing Django admin session is not overridden."""
        # Create request with Django session (no Clerk session marker)
        request = make_request_with_session(request_factory)
        request.user = admin_user  # User authenticated via Django's ModelBackend

        middleware = ClerkAuthMiddleware(lambda r: HttpResponse("OK"))
        middleware.process_request(request)

        # User should remain authenticated (middleware doesn't interfere)
        assert request.user == admin_user
        assert request.user.is_authenticated
        # Clerk attributes should not be set for non-Clerk sessions
        assert request.clerk_user is None
        assert request.clerk_payload is None
        assert request.org is None

    def test_middleware_respects_clerk_session(
        self, middleware, request_factory, clerk_user
    ):
        """Test that middleware respects existing Clerk sessions."""
        request = make_request_with_session(request_factory)
        request.user = clerk_user
        request.session["_auth_user_id"] = str(clerk_user.pk)
        request.session["_auth_user_backend"] = (
            "django_clerk_users.authentication.ClerkBackend"
        )
        request.session["last_clerk_check"] = int(time.time())
        request.session["clerk_org_id"] = "org_123"

        middleware.process_request(request)

        assert request.user == clerk_user
        assert request.clerk_user == clerk_user
        # The middleware preserves the org from the session
        assert request.org == "org_123"

    def test_respects_django_admin_session(
        self, middleware, request_factory, admin_user
    ):
        """Test that middleware respects traditional Django admin sessions."""
        request = make_request_with_session(request_factory)
        request.user = admin_user  # Simulate user logged in via Django admin
        # Note: No "last_clerk_check" in session - this is a non-Clerk session

        middleware.process_request(request)

        # User should remain authenticated (not be cleared)
        assert request.user == admin_user
        assert request.clerk_user is None  # Not a Clerk user
        assert request.clerk_payload is None
        assert request.org is None


@pytest.mark.django_db
class TestMiddlewareHybridAuth:
    """Test middleware with hybrid authentication (Clerk + Django admin)."""

    def test_respects_django_admin_session(
        self, middleware, request_factory, admin_user
    ):
        """Test that middleware respects existing Django admin sessions."""
        request = make_request_with_session(request_factory)
        request.user = admin_user

        # Simulate Django admin session (no Clerk markers)
        request.session["_auth_user_id"] = str(admin_user.pk)
        request.session["_auth_user_backend"] = (
            "django.contrib.auth.backends.ModelBackend"
        )

        middleware.process_request(request)

        # Should preserve the Django admin session
        assert request.user == admin_user
        assert request.clerk_user is None  # Not a Clerk user
        assert request.clerk_payload is None
        assert request.org is None
