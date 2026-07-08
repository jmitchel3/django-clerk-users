"""
Tests for organization webhook handlers.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

from django_clerk_users.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)
from django_clerk_users.organizations.webhooks import (
    handle_organization_created,
    handle_invitation_accepted,
    handle_invitation_created,
    handle_invitation_revoked,
    handle_membership_created,
    handle_membership_deleted,
    handle_membership_updated,
    handle_organization_deleted,
    handle_organization_updated,
    process_organization_event,
    update_or_create_organization,
)


@pytest.fixture
def user(db):
    """Create a Clerk-linked user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_org_webhook",
        email="org-webhook@example.com",
    )


@pytest.fixture
def organization(db):
    """Create an organization."""
    return Organization.objects.create(
        clerk_id="org_webhook",
        name="Webhook Org",
        slug="webhook-org",
    )


def test_update_or_create_organization_syncs_clerk_fields(db):
    """Test organization sync maps Clerk fields onto the local model."""
    client = MagicMock()
    client.organizations.get.return_value = SimpleNamespace(
        name="Synced Org",
        slug="synced-org",
        image_url="https://example.com/logo.png",
        public_metadata={"tier": "pro"},
        private_metadata={"internal": "123"},
        members_count=7,
        pending_invitations_count=2,
        max_allowed_memberships=50,
        created_at=1704067200000,
    )

    with patch("django_clerk_users.client.get_clerk_client", return_value=client):
        organization, created = update_or_create_organization("org_synced")

    assert created is True
    assert organization is not None
    assert organization.name == "Synced Org"
    assert organization.slug == "synced-org"
    assert organization.public_metadata == {"tier": "pro"}
    assert organization.private_metadata == {"internal": "123"}
    assert organization.members_count == 7
    assert organization.pending_invitations_count == 2
    assert organization.max_allowed_memberships == 50


def test_handle_organization_created_uses_webhook_payload_without_api(db):
    """Test organization.created can sync directly from verified event data."""
    payload = {
        "id": "org_payload",
        "name": "Payload Org",
        "slug": "payload-org",
        "image_url": "https://example.com/payload.png",
        "public_metadata": {"tier": "enterprise"},
        "private_metadata": {"internal": "yes"},
        "members_count": 4,
        "pending_invitations_count": 1,
        "max_allowed_memberships": 25,
        "created_at": 1704067200000,
    }

    with patch(
        "django_clerk_users.client.get_clerk_client",
        side_effect=AssertionError("Clerk API should not be called"),
    ):
        result = handle_organization_created(payload)

    organization = Organization.objects.get(clerk_id="org_payload")
    assert result is True
    assert organization.name == "Payload Org"
    assert organization.slug == "payload-org"
    assert organization.image_url == "https://example.com/payload.png"
    assert organization.public_metadata == {"tier": "enterprise"}
    assert organization.private_metadata == {"internal": "yes"}
    assert organization.members_count == 4
    assert organization.pending_invitations_count == 1
    assert organization.max_allowed_memberships == 25


def test_handle_organization_updated_preserves_missing_payload_fields(organization):
    """Test partial organization.updated payloads do not clobber cached fields."""
    organization.public_metadata = {"tier": "starter"}
    organization.save(update_fields=["public_metadata"])

    with patch(
        "django_clerk_users.client.get_clerk_client",
        side_effect=AssertionError("Clerk API should not be called"),
    ):
        result = handle_organization_updated(
            {"id": organization.clerk_id, "name": "Renamed Org"}
        )

    organization.refresh_from_db()
    assert result is True
    assert organization.name == "Renamed Org"
    assert organization.slug == "webhook-org"
    assert organization.public_metadata == {"tier": "starter"}


def test_handle_organization_deleted_soft_deletes(organization):
    """Test organization.deleted marks the organization inactive."""
    result = handle_organization_deleted({"id": organization.clerk_id})

    organization.refresh_from_db()
    assert result is True
    assert organization.is_active is False


def test_handle_membership_created_creates_membership(organization, user):
    """Test membership creation webhook writes a local membership."""
    result = handle_membership_created(
        {
            "id": "mem_created",
            "organization": {"id": organization.clerk_id},
            "public_user_data": {"user_id": user.clerk_id},
            "role": "admin",
            "public_metadata": {"title": "Lead"},
            "private_metadata": {"cost_center": "eng"},
            "created_at": 1704067200000,
        }
    )

    membership = OrganizationMember.objects.get(clerk_membership_id="mem_created")
    assert result is True
    assert membership.organization == organization
    assert membership.user == user
    assert membership.role == "admin"
    assert membership.public_metadata == {"title": "Lead"}
    assert membership.private_metadata == {"cost_center": "eng"}


def test_handle_membership_created_creates_missing_org_from_payload(user):
    """Test membership.created can create the organization from nested payload."""
    payload = {
        "id": "mem_nested_org",
        "organization": {
            "id": "org_nested",
            "name": "Nested Org",
            "slug": "nested-org",
        },
        "public_user_data": {"user_id": user.clerk_id},
        "role": "org:admin",
    }

    with patch(
        "django_clerk_users.client.get_clerk_client",
        side_effect=AssertionError("Clerk API should not be called"),
    ):
        result = handle_membership_created(payload)

    organization = Organization.objects.get(clerk_id="org_nested")
    membership = OrganizationMember.objects.get(clerk_membership_id="mem_nested_org")
    assert result is True
    assert organization.name == "Nested Org"
    assert organization.slug == "nested-org"
    assert membership.organization == organization
    assert membership.user == user
    assert membership.role == "org:admin"


def test_handle_membership_updated_changes_role_and_metadata(organization, user):
    """Test membership update webhook updates local fields."""
    membership = OrganizationMember.objects.create(
        clerk_membership_id="mem_update",
        organization=organization,
        user=user,
        role="member",
    )

    result = handle_membership_updated(
        {
            "id": membership.clerk_membership_id,
            "role": "org:admin",
            "public_metadata": {"title": "Director"},
            "private_metadata": {"cost_center": "ops"},
        }
    )

    membership.refresh_from_db()
    assert result is True
    assert membership.role == "org:admin"
    assert membership.public_metadata == {"title": "Director"}
    assert membership.private_metadata == {"cost_center": "ops"}


def test_handle_membership_deleted_removes_membership(organization, user):
    """Test membership deletion webhook deletes the local membership."""
    membership = OrganizationMember.objects.create(
        clerk_membership_id="mem_delete",
        organization=organization,
        user=user,
    )

    result = handle_membership_deleted({"id": membership.clerk_membership_id})

    assert result is True
    assert not OrganizationMember.objects.filter(pk=membership.pk).exists()


def test_invitation_webhook_lifecycle(organization, user):
    """Test invitation created, accepted, and revoked webhook handlers."""
    created = handle_invitation_created(
        {
            "id": "inv_lifecycle",
            "organization_id": organization.clerk_id,
            "email_address": "invitee@example.com",
            "inviter_user_id": user.clerk_id,
            "role": "member",
            "public_metadata": {"source": "test"},
            "private_metadata": {"batch": "one"},
        }
    )

    invitation = OrganizationInvitation.objects.get(clerk_invitation_id="inv_lifecycle")
    assert created is True
    assert invitation.organization == organization
    assert invitation.inviter == user
    assert invitation.status == OrganizationInvitation.Status.PENDING
    assert invitation.public_metadata == {"source": "test"}

    accepted = handle_invitation_accepted({"id": invitation.clerk_invitation_id})
    invitation.refresh_from_db()
    assert accepted is True
    assert invitation.status == OrganizationInvitation.Status.ACCEPTED

    revoked = handle_invitation_revoked({"id": invitation.clerk_invitation_id})
    invitation.refresh_from_db()
    assert revoked is True
    assert invitation.status == OrganizationInvitation.Status.REVOKED


def test_handle_invitation_created_creates_missing_org_from_payload(user):
    """Test invitation.created can create the organization from nested payload."""
    payload = {
        "id": "inv_nested_org",
        "organization_id": "org_inv_nested",
        "organization": {
            "id": "org_inv_nested",
            "name": "Invitation Nested Org",
            "slug": "invitation-nested-org",
        },
        "email_address": "new-member@example.com",
        "inviter_user_id": user.clerk_id,
        "role": "org:member",
    }

    with patch(
        "django_clerk_users.client.get_clerk_client",
        side_effect=AssertionError("Clerk API should not be called"),
    ):
        result = handle_invitation_created(payload)

    organization = Organization.objects.get(clerk_id="org_inv_nested")
    invitation = OrganizationInvitation.objects.get(
        clerk_invitation_id="inv_nested_org"
    )
    assert result is True
    assert organization.name == "Invitation Nested Org"
    assert organization.slug == "invitation-nested-org"
    assert invitation.organization == organization
    assert invitation.inviter == user
    assert invitation.role == "org:member"


def test_process_organization_event_routes_and_acknowledges_unknown():
    """Test organization event router dispatches known events and acks unknown."""
    with patch(
        "django_clerk_users.organizations.webhooks.handle_organization_deleted",
        return_value=True,
    ) as handler:
        assert process_organization_event("organization.deleted", {"id": "org_123"})

    handler.assert_called_once_with({"id": "org_123"})
    assert process_organization_event("organizationLogo.updated", {}) is True


def test_process_organization_event_returns_false_for_handler_exception():
    """Test organization router reports handler exceptions as failures."""
    with patch(
        "django_clerk_users.organizations.webhooks.handle_organization_deleted",
        side_effect=Exception("Handler error"),
    ):
        assert (
            process_organization_event("organization.deleted", {"id": "org_123"})
            is False
        )
