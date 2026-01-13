"""
Basic tests for django-clerk-users package.
"""

import pytest


class TestPackageImports:
    """Test that package imports work correctly."""

    def test_import_django_clerk_users(self):
        """Test that django_clerk_users can be imported."""
        import django_clerk_users

        assert django_clerk_users.__version__

    def test_import_version(self):
        """Test that version is accessible."""
        from django_clerk_users import __version__

        assert __version__ is not None

    def test_import_exceptions(self):
        """Test that exceptions can be imported."""
        from django_clerk_users.exceptions import (
            ClerkAPIError,
            ClerkAuthenticationError,
            ClerkConfigurationError,
            ClerkError,
            ClerkOrganizationNotFoundError,
            ClerkTokenError,
            ClerkUserNotFoundError,
            ClerkWebhookError,
        )

        assert ClerkError
        assert ClerkConfigurationError
        assert ClerkAuthenticationError
        assert ClerkTokenError
        assert ClerkWebhookError
        assert ClerkAPIError
        assert ClerkUserNotFoundError
        assert ClerkOrganizationNotFoundError

    def test_import_settings(self):
        """Test that settings can be imported."""
        from django_clerk_users.settings import (
            CLERK_AUTH_PARTIES,
            CLERK_CACHE_TIMEOUT,
            CLERK_FRONTEND_HOSTS,
            CLERK_SECRET_KEY,
            CLERK_SESSION_REVALIDATION_SECONDS,
            CLERK_WEBHOOK_SIGNING_KEY,
        )

        assert CLERK_SECRET_KEY is not None
        assert CLERK_WEBHOOK_SIGNING_KEY is not None
        assert isinstance(CLERK_FRONTEND_HOSTS, list)
        assert isinstance(CLERK_AUTH_PARTIES, list)
        assert isinstance(CLERK_SESSION_REVALIDATION_SECONDS, int)
        assert isinstance(CLERK_CACHE_TIMEOUT, int)


class TestDjangoSetup:
    """Test Django integration."""

    def test_django_configured(self):
        """Test that Django can be set up with the package installed."""
        from django.conf import settings

        assert settings.configured
        assert "django_clerk_users" in settings.INSTALLED_APPS

    def test_auth_user_model(self):
        """Test that AUTH_USER_MODEL is set correctly."""
        from django.conf import settings

        assert settings.AUTH_USER_MODEL == "django_clerk_users.ClerkUser"

    def test_get_user_model(self):
        """Test that get_user_model returns ClerkUser."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        assert User.__name__ == "ClerkUser"


class TestModels:
    """Test model definitions."""

    def test_clerk_user_model(self):
        """Test ClerkUser model exists and has required fields."""
        from django_clerk_users.models import ClerkUser

        # Check required fields
        assert hasattr(ClerkUser, "uid")
        assert hasattr(ClerkUser, "clerk_id")
        assert hasattr(ClerkUser, "email")
        assert hasattr(ClerkUser, "first_name")
        assert hasattr(ClerkUser, "last_name")
        assert hasattr(ClerkUser, "is_active")
        assert hasattr(ClerkUser, "is_staff")
        assert hasattr(ClerkUser, "is_superuser")
        assert hasattr(ClerkUser, "created_at")
        assert hasattr(ClerkUser, "updated_at")

    def test_abstract_clerk_user(self):
        """Test AbstractClerkUser is abstract."""
        from django_clerk_users.models import AbstractClerkUser

        assert AbstractClerkUser._meta.abstract is True

    def test_clerk_user_manager(self):
        """Test ClerkUserManager exists."""
        from django_clerk_users.models import ClerkUser, ClerkUserManager

        assert isinstance(ClerkUser.objects, ClerkUserManager)


class TestAuthentication:
    """Test authentication components."""

    def test_import_clerk_backend(self):
        """Test ClerkBackend can be imported."""
        from django_clerk_users.authentication import ClerkBackend

        assert ClerkBackend

    def test_import_auth_utils(self):
        """Test authentication utilities can be imported."""
        from django_clerk_users.authentication import (
            get_clerk_payload_from_request,
            get_or_create_user_from_payload,
        )

        assert get_clerk_payload_from_request
        assert get_or_create_user_from_payload


class TestMiddleware:
    """Test middleware components."""

    def test_import_middleware(self):
        """Test middleware can be imported."""
        from django_clerk_users.middleware import ClerkAuthMiddleware

        assert ClerkAuthMiddleware


class TestWebhooks:
    """Test webhook components."""

    def test_import_webhook_view(self):
        """Test webhook view can be imported."""
        from django_clerk_users.webhooks import clerk_webhook_view

        assert clerk_webhook_view

    def test_import_webhook_security(self):
        """Test webhook security can be imported."""
        from django_clerk_users.webhooks import (
            clerk_webhook_required,
            verify_clerk_webhook,
        )

        assert clerk_webhook_required
        assert verify_clerk_webhook

    def test_import_webhook_signals(self):
        """Test webhook signals can be imported."""
        from django_clerk_users.webhooks import (
            clerk_user_created,
            clerk_user_deleted,
            clerk_user_updated,
        )

        assert clerk_user_created
        assert clerk_user_updated
        assert clerk_user_deleted


class TestDecorators:
    """Test decorator components."""

    def test_import_decorators(self):
        """Test decorators can be imported."""
        from django_clerk_users.decorators import (
            clerk_org_required,
            clerk_staff_required,
            clerk_superuser_required,
            clerk_user_required,
        )

        assert clerk_user_required
        assert clerk_org_required
        assert clerk_staff_required
        assert clerk_superuser_required


class TestOrganizations:
    """Test organizations sub-app."""

    def test_import_organization_models(self):
        """Test organization models can be imported."""
        from django_clerk_users.organizations.models import (
            Organization,
            OrganizationInvitation,
            OrganizationMember,
        )

        assert Organization
        assert OrganizationMember
        assert OrganizationInvitation

    def test_import_organization_middleware(self):
        """Test organization middleware can be imported."""
        from django_clerk_users.organizations.middleware import (
            ClerkOrganizationMiddleware,
        )

        assert ClerkOrganizationMiddleware
