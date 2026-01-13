"""
Tests for django-clerk-users organizations sub-app.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from django_clerk_users.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_org123",
        email="org@example.com",
        first_name="Org",
        last_name="User",
    )


@pytest.fixture
def another_user(db):
    """Create another test user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_other456",
        email="other@example.com",
    )


@pytest.fixture
def organization(db):
    """Create a test organization."""
    return Organization.objects.create(
        clerk_id="org_test123",
        name="Test Organization",
        slug="test-org",
    )


@pytest.fixture
def membership(db, organization, clerk_user):
    """Create a test membership."""
    return OrganizationMember.objects.create(
        clerk_membership_id="mem_test123",
        organization=organization,
        user=clerk_user,
        role="member",
    )


@pytest.fixture
def invitation(db, organization, clerk_user):
    """Create a test invitation."""
    return OrganizationInvitation.objects.create(
        clerk_invitation_id="inv_test123",
        organization=organization,
        inviter=clerk_user,
        email_address="invited@example.com",
        role="member",
    )


class TestOrganizationModel:
    """Test Organization model."""

    def test_create_organization(self, db):
        """Test creating an organization."""
        org = Organization.objects.create(
            clerk_id="org_create123",
            name="Created Org",
            slug="created-org",
        )

        assert org.clerk_id == "org_create123"
        assert org.name == "Created Org"
        assert org.slug == "created-org"
        assert org.is_active is True

    def test_organization_str(self, organization):
        """Test organization string representation."""
        assert str(organization) == "Test Organization"

    def test_organization_uid_is_uuid(self, organization):
        """Test that uid is a valid UUID."""
        assert isinstance(organization.uid, uuid.UUID)

    def test_organization_public_id(self, organization):
        """Test public_id property."""
        assert organization.public_id == str(organization.uid)

    def test_organization_handle(self, organization):
        """Test handle property (alias for slug)."""
        assert organization.handle == organization.slug

    def test_organization_timestamps(self, organization):
        """Test organization timestamps."""
        assert organization.created_at is not None
        assert organization.updated_at is not None

    def test_organization_metadata_defaults(self, organization):
        """Test metadata fields default to empty dicts."""
        assert organization.public_metadata == {}
        assert organization.private_metadata == {}

    def test_organization_counts_default(self, organization):
        """Test count fields default to 0."""
        assert organization.members_count == 0
        assert organization.pending_invitations_count == 0
        assert organization.max_allowed_memberships == 0

    def test_organization_with_metadata(self, db):
        """Test creating organization with metadata."""
        org = Organization.objects.create(
            clerk_id="org_meta123",
            name="Meta Org",
            slug="meta-org",
            public_metadata={"plan": "pro"},
            private_metadata={"internal_id": "12345"},
        )

        assert org.public_metadata == {"plan": "pro"}
        assert org.private_metadata == {"internal_id": "12345"}

    def test_get_member_count(self, organization, membership):
        """Test get_member_count method."""
        count = organization.get_member_count()
        assert count == 1


class TestOrganizationMemberModel:
    """Test OrganizationMember model."""

    def test_create_membership(self, organization, clerk_user):
        """Test creating a membership."""
        member = OrganizationMember.objects.create(
            clerk_membership_id="mem_new123",
            organization=organization,
            user=clerk_user,
            role="admin",
        )

        assert member.organization == organization
        assert member.user == clerk_user
        assert member.role == "admin"

    def test_membership_str(self, membership):
        """Test membership string representation."""
        result = str(membership)
        assert "org@example.com" in result
        assert "Test Organization" in result
        assert "member" in result

    def test_is_admin_for_admin_role(self, organization, clerk_user):
        """Test is_admin property for admin role."""
        member = OrganizationMember.objects.create(
            clerk_membership_id="mem_admin",
            organization=organization,
            user=clerk_user,
            role="admin",
        )
        assert member.is_admin is True

    def test_is_admin_for_org_admin_role(self, organization, clerk_user):
        """Test is_admin property for org:admin role."""
        member = OrganizationMember.objects.create(
            clerk_membership_id="mem_org_admin",
            organization=organization,
            user=clerk_user,
            role="org:admin",
        )
        assert member.is_admin is True

    def test_is_admin_for_owner_role(self, organization, clerk_user):
        """Test is_admin property for owner role."""
        member = OrganizationMember.objects.create(
            clerk_membership_id="mem_owner",
            organization=organization,
            user=clerk_user,
            role="owner",
        )
        assert member.is_admin is True

    def test_is_admin_for_member_role(self, membership):
        """Test is_admin property for member role."""
        assert membership.is_admin is False

    def test_can_invite_members_admin(self, organization, clerk_user):
        """Test can_invite_members for admin."""
        member = OrganizationMember.objects.create(
            clerk_membership_id="mem_inv_admin",
            organization=organization,
            user=clerk_user,
            role="admin",
        )
        assert member.can_invite_members() is True

    def test_can_invite_members_regular(self, membership):
        """Test can_invite_members for regular member."""
        assert membership.can_invite_members() is False

    def test_membership_unique_constraint(self, organization, clerk_user):
        """Test that user can only have one membership per org."""
        OrganizationMember.objects.create(
            clerk_membership_id="mem_first",
            organization=organization,
            user=clerk_user,
        )

        with pytest.raises(Exception):  # IntegrityError
            OrganizationMember.objects.create(
                clerk_membership_id="mem_second",
                organization=organization,
                user=clerk_user,
            )

    def test_membership_metadata(self, organization, clerk_user):
        """Test membership metadata fields."""
        member = OrganizationMember.objects.create(
            clerk_membership_id="mem_meta",
            organization=organization,
            user=clerk_user,
            public_metadata={"title": "Engineer"},
            private_metadata={"salary": "100k"},
        )

        assert member.public_metadata == {"title": "Engineer"}
        assert member.private_metadata == {"salary": "100k"}


class TestOrganizationInvitationModel:
    """Test OrganizationInvitation model."""

    def test_create_invitation(self, organization, clerk_user):
        """Test creating an invitation."""
        inv = OrganizationInvitation.objects.create(
            clerk_invitation_id="inv_new123",
            organization=organization,
            inviter=clerk_user,
            email_address="newuser@example.com",
            role="member",
        )

        assert inv.organization == organization
        assert inv.inviter == clerk_user
        assert inv.email_address == "newuser@example.com"
        assert inv.status == OrganizationInvitation.Status.PENDING

    def test_invitation_str(self, invitation):
        """Test invitation string representation."""
        result = str(invitation)
        assert "invited@example.com" in result
        assert "Test Organization" in result

    def test_invitation_status_choices(self):
        """Test invitation status choices."""
        assert OrganizationInvitation.Status.PENDING == "pending"
        assert OrganizationInvitation.Status.ACCEPTED == "accepted"
        assert OrganizationInvitation.Status.REVOKED == "revoked"

    def test_invitation_without_inviter(self, organization):
        """Test invitation can have null inviter."""
        inv = OrganizationInvitation.objects.create(
            clerk_invitation_id="inv_no_inviter",
            organization=organization,
            email_address="noinviter@example.com",
        )

        assert inv.inviter is None

    def test_invitation_timestamps(self, invitation):
        """Test invitation timestamps."""
        assert invitation.created_at is not None
        assert invitation.updated_at is not None

    def test_invitation_metadata(self, organization):
        """Test invitation metadata fields."""
        inv = OrganizationInvitation.objects.create(
            clerk_invitation_id="inv_meta",
            organization=organization,
            email_address="meta@example.com",
            public_metadata={"source": "email"},
            private_metadata={"campaign_id": "abc123"},
        )

        assert inv.public_metadata == {"source": "email"}
        assert inv.private_metadata == {"campaign_id": "abc123"}


class TestOrganizationRelationships:
    """Test relationships between organization models."""

    def test_organization_members_relationship(self, organization, membership):
        """Test organization -> members relationship."""
        members = organization.cached_members.all()
        assert membership in members

    def test_organization_invitations_relationship(self, organization, invitation):
        """Test organization -> invitations relationship."""
        invitations = organization.invitations.all()
        assert invitation in invitations

    def test_user_memberships_relationship(self, clerk_user, membership):
        """Test user -> memberships relationship."""
        memberships = clerk_user.organization_memberships.all()
        assert membership in memberships

    def test_user_sent_invitations_relationship(self, clerk_user, invitation):
        """Test user -> sent_invitations relationship."""
        invitations = clerk_user.sent_invitations.all()
        assert invitation in invitations

    def test_cascade_delete_organization(self, organization, membership, invitation):
        """Test that deleting organization cascades to members and invitations."""
        org_id = organization.id
        organization.delete()

        assert not OrganizationMember.objects.filter(organization_id=org_id).exists()
        assert not OrganizationInvitation.objects.filter(organization_id=org_id).exists()

    def test_cascade_delete_user_memberships(self, clerk_user, membership):
        """Test that deleting user cascades to memberships."""
        user_id = clerk_user.id
        clerk_user.delete()

        assert not OrganizationMember.objects.filter(user_id=user_id).exists()

    def test_set_null_inviter_on_delete(self, clerk_user, invitation):
        """Test that deleting inviter sets invitation.inviter to null."""
        inv_id = invitation.id
        clerk_user.delete()

        invitation.refresh_from_db()
        assert invitation.inviter is None
