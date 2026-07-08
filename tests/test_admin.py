"""
Tests for Django admin registration helpers.
"""

from __future__ import annotations

from django.contrib.admin import AdminSite

from django_clerk_users.admin import ClerkUserAdmin, register_clerk_user_admin
from django_clerk_users.models import ClerkUser
from django_clerk_users.organizations.admin import (
    OrganizationAdmin,
    OrganizationInvitationAdmin,
    OrganizationMemberAdmin,
    register_organization_admins,
)
from django_clerk_users.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)


def test_clerk_user_admin_registration_helper_is_idempotent():
    """Test default ClerkUser admin registration on an isolated admin site."""
    site = AdminSite(name="clerk-user-admin-test")

    assert register_clerk_user_admin(site) is True
    assert site.is_registered(ClerkUser)
    assert isinstance(site._registry[ClerkUser], ClerkUserAdmin)
    assert register_clerk_user_admin(site) is False


def test_clerk_user_admin_registration_helper_skips_swapped_model(monkeypatch):
    """Test swapped ClerkUser models are not registered."""
    site = AdminSite(name="clerk-user-admin-swapped-test")

    monkeypatch.setattr(
        "django_clerk_users.admin._model_is_swapped", lambda model: True
    )

    assert register_clerk_user_admin(site) is False
    assert not site.is_registered(ClerkUser)


def test_organization_admin_registration_helper_is_idempotent():
    """Test organization admin registration helper on an isolated admin site."""
    site = AdminSite(name="organization-admin-test")

    assert register_organization_admins(site) == [
        Organization,
        OrganizationMember,
        OrganizationInvitation,
    ]
    assert isinstance(site._registry[Organization], OrganizationAdmin)
    assert isinstance(site._registry[OrganizationMember], OrganizationMemberAdmin)
    assert isinstance(
        site._registry[OrganizationInvitation],
        OrganizationInvitationAdmin,
    )
    assert register_organization_admins(site) == []
