"""
Organization models for django-clerk-users.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser


class Organization(models.Model):
    """
    Represents a Clerk organization.

    Organizations are synced from Clerk and stored locally for
    efficient querying and relationships.
    """

    # Public identifier (use in URLs and APIs)
    uid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="Public unique identifier for the organization.",
    )

    # Clerk-specific fields
    clerk_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique identifier from Clerk.",
    )

    # Organization fields
    name = models.CharField(
        max_length=255,
        help_text="Organization name.",
    )
    slug = models.SlugField(
        max_length=255,
        db_index=True,
        help_text="URL-friendly organization identifier.",
    )
    image_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL to organization logo from Clerk.",
    )

    # Metadata
    public_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Public metadata from Clerk.",
    )
    private_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Private metadata from Clerk.",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the organization is active.",
    )

    # Stats (synced from Clerk)
    members_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of members in the organization.",
    )
    pending_invitations_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of pending invitations.",
    )
    max_allowed_memberships = models.PositiveIntegerField(
        default=0,
        help_text="Maximum allowed memberships (0 = unlimited).",
    )

    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the organization was created in Clerk.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the organization was last updated.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["clerk_id"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self) -> str:
        return self.name

    @property
    def public_id(self) -> str:
        """Return the public UUID as a string for API responses."""
        return str(self.uid)

    @property
    def handle(self) -> str:
        """Return the organization slug (alias for compatibility)."""
        return self.slug

    def get_member_count(self) -> int:
        """Get current member count from cached members."""
        return self.cached_members.count()

    def sync_from_clerk(self) -> tuple[bool, str]:
        """
        Sync organization data from Clerk.

        Returns:
            Tuple of (success, message)
        """
        try:
            from django_clerk_users.organizations.webhooks import (
                update_or_create_organization,
            )

            org, created = update_or_create_organization(self.clerk_id)
            action = "created" if created else "updated"
            return True, f"Organization {action} successfully"
        except Exception as e:
            return False, str(e)


class OrganizationMember(models.Model):
    """
    Represents a membership in a Clerk organization.

    This is a cache of Clerk's organization memberships for efficient
    local queries.
    """

    # Clerk-specific fields
    clerk_membership_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique membership identifier from Clerk.",
    )

    # Relationships
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="cached_members",
        help_text="The organization.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
        help_text="The user.",
    )

    # Role
    role = models.CharField(
        max_length=100,
        default="member",
        help_text="User's role in the organization (e.g., 'admin', 'member').",
    )

    # Metadata
    public_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Public metadata from Clerk.",
    )
    private_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Private metadata from Clerk.",
    )

    # Timestamps
    joined_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the user joined the organization.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the membership was last updated.",
    )

    class Meta:
        ordering = ["-joined_at"]
        unique_together = [("organization", "user")]
        indexes = [
            models.Index(fields=["clerk_membership_id"]),
            models.Index(fields=["role"]),
        ]
        verbose_name = "Organization Member"
        verbose_name_plural = "Organization Members"

    def __str__(self) -> str:
        return f"{self.user.email} in {self.organization.name} ({self.role})"

    @property
    def is_admin(self) -> bool:
        """Check if this member has admin role."""
        return self.role.lower() in ("admin", "org:admin", "owner")

    def can_invite_members(self) -> bool:
        """Check if this member can invite others to the organization."""
        return self.is_admin


class OrganizationInvitation(models.Model):
    """
    Represents a pending invitation to a Clerk organization.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"

    # Clerk-specific fields
    clerk_invitation_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique invitation identifier from Clerk.",
    )

    # Relationships
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invitations",
        help_text="The organization.",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations",
        help_text="The user who sent the invitation.",
    )

    # Invitation details
    email_address = models.EmailField(
        help_text="Email address of the invitee.",
    )
    role = models.CharField(
        max_length=100,
        default="member",
        help_text="Role the user will have upon accepting.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Invitation status.",
    )

    # Metadata
    public_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Public metadata from Clerk.",
    )
    private_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Private metadata from Clerk.",
    )

    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the invitation was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the invitation was last updated.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["clerk_invitation_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["email_address"]),
        ]
        verbose_name = "Organization Invitation"
        verbose_name_plural = "Organization Invitations"

    def __str__(self) -> str:
        return f"Invitation to {self.email_address} for {self.organization.name}"
