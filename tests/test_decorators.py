"""
Tests for django-clerk-users decorators.
"""

import json
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.test import RequestFactory

from django_clerk_users.decorators import (
    clerk_org_required,
    clerk_staff_required,
    clerk_superuser_required,
    clerk_user_required,
)


@pytest.fixture
def request_factory():
    """Create a request factory."""
    return RequestFactory()


@pytest.fixture
def authenticated_user(db):
    """Create an authenticated user."""
    User = get_user_model()
    user = User.objects.create_user(
        clerk_id="user_dec123",
        email="decorator@example.com",
    )
    return user


@pytest.fixture
def staff_user(db):
    """Create a staff user."""
    User = get_user_model()
    user = User.objects.create_user(
        clerk_id="user_staff",
        email="staff@example.com",
        is_staff=True,
    )
    return user


@pytest.fixture
def superuser(db):
    """Create a superuser."""
    User = get_user_model()
    user = User.objects.create_superuser(
        clerk_id="user_super",
        email="super@example.com",
    )
    return user


def sample_view(request):
    """Sample view function for testing."""
    return JsonResponse({"success": True})


class TestClerkUserRequired:
    """Test clerk_user_required decorator."""

    def test_authenticated_user_passes(self, request_factory, authenticated_user):
        """Test that authenticated user can access the view."""
        request = request_factory.get("/")
        request.clerk_user = authenticated_user

        decorated_view = clerk_user_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 200
        assert json.loads(response.content) == {"success": True}

    def test_unauthenticated_user_denied(self, request_factory):
        """Test that unauthenticated user is denied."""
        request = request_factory.get("/")
        request.clerk_user = None

        decorated_view = clerk_user_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data
        assert "Authentication required" in data["error"]

    def test_missing_clerk_user_attr(self, request_factory):
        """Test when clerk_user attribute is missing."""
        request = request_factory.get("/")
        # Don't set clerk_user at all

        decorated_view = clerk_user_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 401

    def test_anonymous_user_denied(self, request_factory):
        """Test that anonymous user is denied."""
        from django.contrib.auth.models import AnonymousUser

        request = request_factory.get("/")
        request.clerk_user = AnonymousUser()

        decorated_view = clerk_user_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 401


class TestClerkOrgRequired:
    """Test clerk_org_required decorator."""

    def test_user_with_org_passes(self, request_factory, authenticated_user):
        """Test that user with organization can access the view."""
        request = request_factory.get("/")
        request.clerk_user = authenticated_user
        request.org = "org_123"

        decorated_view = clerk_org_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 200

    def test_user_without_org_denied(self, request_factory, authenticated_user):
        """Test that user without organization is denied."""
        request = request_factory.get("/")
        request.clerk_user = authenticated_user
        request.org = None

        decorated_view = clerk_org_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 403
        data = json.loads(response.content)
        assert "Organization context required" in data["error"]

    def test_unauthenticated_user_denied(self, request_factory):
        """Test that unauthenticated user is denied before org check."""
        request = request_factory.get("/")
        request.clerk_user = None
        request.org = "org_123"

        decorated_view = clerk_org_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 401


class TestClerkStaffRequired:
    """Test clerk_staff_required decorator."""

    def test_staff_user_passes(self, request_factory, staff_user):
        """Test that staff user can access the view."""
        request = request_factory.get("/")
        request.clerk_user = staff_user

        decorated_view = clerk_staff_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 200

    def test_non_staff_user_denied(self, request_factory, authenticated_user):
        """Test that non-staff user is denied."""
        request = request_factory.get("/")
        request.clerk_user = authenticated_user

        decorated_view = clerk_staff_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 403
        data = json.loads(response.content)
        assert "Staff access required" in data["error"]

    def test_unauthenticated_user_denied(self, request_factory):
        """Test that unauthenticated user is denied."""
        request = request_factory.get("/")
        request.clerk_user = None

        decorated_view = clerk_staff_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 401


class TestClerkSuperuserRequired:
    """Test clerk_superuser_required decorator."""

    def test_superuser_passes(self, request_factory, superuser):
        """Test that superuser can access the view."""
        request = request_factory.get("/")
        request.clerk_user = superuser

        decorated_view = clerk_superuser_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 200

    def test_staff_user_denied(self, request_factory, staff_user):
        """Test that staff (but not superuser) is denied."""
        request = request_factory.get("/")
        request.clerk_user = staff_user

        decorated_view = clerk_superuser_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 403
        data = json.loads(response.content)
        assert "Superuser access required" in data["error"]

    def test_regular_user_denied(self, request_factory, authenticated_user):
        """Test that regular user is denied."""
        request = request_factory.get("/")
        request.clerk_user = authenticated_user

        decorated_view = clerk_superuser_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 403

    def test_unauthenticated_user_denied(self, request_factory):
        """Test that unauthenticated user is denied."""
        request = request_factory.get("/")
        request.clerk_user = None

        decorated_view = clerk_superuser_required(sample_view)
        response = decorated_view(request)

        assert response.status_code == 401


class TestDecoratorPreservesFunctionMetadata:
    """Test that decorators preserve function metadata."""

    def test_clerk_user_required_preserves_name(self):
        """Test that function name is preserved."""

        @clerk_user_required
        def my_view(request):
            pass

        assert my_view.__name__ == "my_view"

    def test_clerk_org_required_preserves_name(self):
        """Test that function name is preserved."""

        @clerk_org_required
        def my_org_view(request):
            pass

        assert my_org_view.__name__ == "my_org_view"

    def test_clerk_staff_required_preserves_name(self):
        """Test that function name is preserved."""

        @clerk_staff_required
        def admin_view(request):
            pass

        assert admin_view.__name__ == "admin_view"

    def test_clerk_superuser_required_preserves_name(self):
        """Test that function name is preserved."""

        @clerk_superuser_required
        def super_view(request):
            pass

        assert super_view.__name__ == "super_view"
