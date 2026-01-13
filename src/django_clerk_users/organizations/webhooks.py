"""
Webhook handlers for organization events.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from django_clerk_users.caching import invalidate_organization_cache
from django_clerk_users.webhooks.handlers import parse_clerk_timestamp
from django_clerk_users.webhooks.signals import (
    clerk_invitation_accepted,
    clerk_invitation_created,
    clerk_invitation_revoked,
    clerk_membership_created,
    clerk_membership_deleted,
    clerk_membership_updated,
    clerk_organization_created,
    clerk_organization_deleted,
    clerk_organization_updated,
)

logger = logging.getLogger(__name__)


def update_or_create_organization(org_id: str) -> tuple:
    """
    Update or create an Organization from Clerk data.

    Args:
        org_id: The Clerk organization ID.

    Returns:
        A tuple of (organization, created).
    """
    from django_clerk_users.client import get_clerk_client
    from django_clerk_users.organizations.models import Organization

    clerk = get_clerk_client()
    clerk_org = clerk.organizations.get(organization_id=org_id)

    if not clerk_org:
        logger.error(f"Organization not found in Clerk: {org_id}")
        return None, False

    org_data = {
        "name": getattr(clerk_org, "name", ""),
        "slug": getattr(clerk_org, "slug", ""),
        "image_url": getattr(clerk_org, "image_url", "") or "",
        "public_metadata": getattr(clerk_org, "public_metadata", {}) or {},
        "private_metadata": getattr(clerk_org, "private_metadata", {}) or {},
        "members_count": getattr(clerk_org, "members_count", 0) or 0,
        "pending_invitations_count": getattr(clerk_org, "pending_invitations_count", 0) or 0,
        "max_allowed_memberships": getattr(clerk_org, "max_allowed_memberships", 0) or 0,
    }

    created_at = parse_clerk_timestamp(getattr(clerk_org, "created_at", None))
    if created_at:
        org_data["created_at"] = created_at

    organization, created = Organization.objects.update_or_create(
        clerk_id=org_id,
        defaults=org_data,
    )

    return organization, created


@transaction.atomic
def handle_organization_created(data: dict[str, Any]) -> bool:
    """Handle organization.created webhook event."""
    from django_clerk_users.organizations.models import Organization

    org_id = data.get("id")
    if not org_id:
        logger.error("organization.created webhook missing organization ID")
        return False

    try:
        organization, created = update_or_create_organization(org_id)
        if organization:
            clerk_organization_created.send(
                sender=Organization,
                organization=organization,
                clerk_data=data,
            )
            logger.info(f"Organization created: {organization.name}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to handle organization.created: {e}")
        return False


@transaction.atomic
def handle_organization_updated(data: dict[str, Any]) -> bool:
    """Handle organization.updated webhook event."""
    from django_clerk_users.organizations.models import Organization

    org_id = data.get("id")
    if not org_id:
        logger.error("organization.updated webhook missing organization ID")
        return False

    try:
        invalidate_organization_cache(org_id)
        organization, created = update_or_create_organization(org_id)
        if organization:
            clerk_organization_updated.send(
                sender=Organization,
                organization=organization,
                clerk_data=data,
            )
            logger.info(f"Organization updated: {organization.name}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to handle organization.updated: {e}")
        return False


@transaction.atomic
def handle_organization_deleted(data: dict[str, Any]) -> bool:
    """Handle organization.deleted webhook event."""
    from django_clerk_users.organizations.models import Organization

    org_id = data.get("id")
    if not org_id:
        logger.error("organization.deleted webhook missing organization ID")
        return False

    try:
        invalidate_organization_cache(org_id)
        organization = Organization.objects.filter(clerk_id=org_id).first()
        if organization:
            organization.is_active = False
            organization.save(update_fields=["is_active", "updated_at"])
            clerk_organization_deleted.send(
                sender=Organization,
                organization=organization,
                clerk_data=data,
            )
            logger.info(f"Organization deleted: {organization.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to handle organization.deleted: {e}")
        return False


@transaction.atomic
def handle_membership_created(data: dict[str, Any]) -> bool:
    """Handle organizationMembership.created webhook event."""
    from django.contrib.auth import get_user_model

    from django_clerk_users.organizations.models import Organization, OrganizationMember

    User = get_user_model()

    membership_id = data.get("id")
    org_data = data.get("organization", {})
    user_data = data.get("public_user_data", {})

    org_id = org_data.get("id")
    user_id = user_data.get("user_id")

    if not all([membership_id, org_id, user_id]):
        logger.error("organizationMembership.created webhook missing required fields")
        return False

    try:
        organization = Organization.objects.filter(clerk_id=org_id).first()
        if not organization:
            organization, _ = update_or_create_organization(org_id)

        user = User.objects.filter(clerk_id=user_id).first()
        if not user:
            from django_clerk_users.utils import update_or_create_clerk_user
            user, _ = update_or_create_clerk_user(user_id)

        membership, created = OrganizationMember.objects.update_or_create(
            clerk_membership_id=membership_id,
            defaults={
                "organization": organization,
                "user": user,
                "role": data.get("role", "member"),
                "public_metadata": data.get("public_metadata", {}),
                "private_metadata": data.get("private_metadata", {}),
            },
        )

        joined_at = parse_clerk_timestamp(data.get("created_at"))
        if joined_at:
            membership.joined_at = joined_at
            membership.save(update_fields=["joined_at"])

        clerk_membership_created.send(
            sender=OrganizationMember,
            membership=membership,
            clerk_data=data,
        )
        logger.info(f"Membership created: {user.email} in {organization.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to handle organizationMembership.created: {e}")
        return False


@transaction.atomic
def handle_membership_updated(data: dict[str, Any]) -> bool:
    """Handle organizationMembership.updated webhook event."""
    from django_clerk_users.organizations.models import OrganizationMember

    membership_id = data.get("id")
    if not membership_id:
        logger.error("organizationMembership.updated webhook missing membership ID")
        return False

    try:
        membership = OrganizationMember.objects.filter(
            clerk_membership_id=membership_id
        ).first()
        if membership:
            membership.role = data.get("role", membership.role)
            membership.public_metadata = data.get("public_metadata", membership.public_metadata)
            membership.private_metadata = data.get("private_metadata", membership.private_metadata)
            membership.save()

            clerk_membership_updated.send(
                sender=OrganizationMember,
                membership=membership,
                clerk_data=data,
            )
            logger.info(f"Membership updated: {membership}")
        return True

    except Exception as e:
        logger.error(f"Failed to handle organizationMembership.updated: {e}")
        return False


@transaction.atomic
def handle_membership_deleted(data: dict[str, Any]) -> bool:
    """Handle organizationMembership.deleted webhook event."""
    from django_clerk_users.organizations.models import OrganizationMember

    membership_id = data.get("id")
    if not membership_id:
        logger.error("organizationMembership.deleted webhook missing membership ID")
        return False

    try:
        membership = OrganizationMember.objects.filter(
            clerk_membership_id=membership_id
        ).first()
        if membership:
            clerk_membership_deleted.send(
                sender=OrganizationMember,
                membership=membership,
                clerk_data=data,
            )
            membership.delete()
            logger.info(f"Membership deleted: {membership_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to handle organizationMembership.deleted: {e}")
        return False


@transaction.atomic
def handle_invitation_created(data: dict[str, Any]) -> bool:
    """Handle organizationInvitation.created webhook event."""
    from django.contrib.auth import get_user_model

    from django_clerk_users.organizations.models import Organization, OrganizationInvitation

    User = get_user_model()

    invitation_id = data.get("id")
    org_id = data.get("organization_id")
    email = data.get("email_address")

    if not all([invitation_id, org_id, email]):
        logger.error("organizationInvitation.created webhook missing required fields")
        return False

    try:
        organization = Organization.objects.filter(clerk_id=org_id).first()
        if not organization:
            organization, _ = update_or_create_organization(org_id)

        inviter = None
        inviter_id = data.get("inviter_user_id")
        if inviter_id:
            inviter = User.objects.filter(clerk_id=inviter_id).first()

        invitation, created = OrganizationInvitation.objects.update_or_create(
            clerk_invitation_id=invitation_id,
            defaults={
                "organization": organization,
                "inviter": inviter,
                "email_address": email,
                "role": data.get("role", "member"),
                "status": OrganizationInvitation.Status.PENDING,
                "public_metadata": data.get("public_metadata", {}),
                "private_metadata": data.get("private_metadata", {}),
            },
        )

        clerk_invitation_created.send(
            sender=OrganizationInvitation,
            invitation=invitation,
            clerk_data=data,
        )
        logger.info(f"Invitation created: {email} to {organization.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to handle organizationInvitation.created: {e}")
        return False


@transaction.atomic
def handle_invitation_accepted(data: dict[str, Any]) -> bool:
    """Handle organizationInvitation.accepted webhook event."""
    from django_clerk_users.organizations.models import OrganizationInvitation

    invitation_id = data.get("id")
    if not invitation_id:
        logger.error("organizationInvitation.accepted webhook missing invitation ID")
        return False

    try:
        invitation = OrganizationInvitation.objects.filter(
            clerk_invitation_id=invitation_id
        ).first()
        if invitation:
            invitation.status = OrganizationInvitation.Status.ACCEPTED
            invitation.save(update_fields=["status", "updated_at"])

            clerk_invitation_accepted.send(
                sender=OrganizationInvitation,
                invitation=invitation,
                clerk_data=data,
            )
            logger.info(f"Invitation accepted: {invitation.email_address}")
        return True

    except Exception as e:
        logger.error(f"Failed to handle organizationInvitation.accepted: {e}")
        return False


@transaction.atomic
def handle_invitation_revoked(data: dict[str, Any]) -> bool:
    """Handle organizationInvitation.revoked webhook event."""
    from django_clerk_users.organizations.models import OrganizationInvitation

    invitation_id = data.get("id")
    if not invitation_id:
        logger.error("organizationInvitation.revoked webhook missing invitation ID")
        return False

    try:
        invitation = OrganizationInvitation.objects.filter(
            clerk_invitation_id=invitation_id
        ).first()
        if invitation:
            invitation.status = OrganizationInvitation.Status.REVOKED
            invitation.save(update_fields=["status", "updated_at"])

            clerk_invitation_revoked.send(
                sender=OrganizationInvitation,
                invitation=invitation,
                clerk_data=data,
            )
            logger.info(f"Invitation revoked: {invitation.email_address}")
        return True

    except Exception as e:
        logger.error(f"Failed to handle organizationInvitation.revoked: {e}")
        return False


def process_organization_event(event_type: str, data: dict[str, Any]) -> bool:
    """
    Process an organization-related webhook event.

    Args:
        event_type: The Clerk event type.
        data: The event data.

    Returns:
        True if handled successfully, False otherwise.
    """
    handlers = {
        "organization.created": handle_organization_created,
        "organization.updated": handle_organization_updated,
        "organization.deleted": handle_organization_deleted,
        "organizationMembership.created": handle_membership_created,
        "organizationMembership.updated": handle_membership_updated,
        "organizationMembership.deleted": handle_membership_deleted,
        "organizationInvitation.created": handle_invitation_created,
        "organizationInvitation.accepted": handle_invitation_accepted,
        "organizationInvitation.revoked": handle_invitation_revoked,
    }

    handler = handlers.get(event_type)
    if handler:
        return handler(data)

    logger.debug(f"Unhandled organization event type: {event_type}")
    return True
