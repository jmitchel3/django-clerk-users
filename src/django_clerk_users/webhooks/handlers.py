"""
Webhook event handlers for Clerk.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from django.core.cache import cache
from django.db import transaction

from django_clerk_users.settings import CLERK_WEBHOOK_DEDUP_TIMEOUT
from django_clerk_users.webhooks.signals import (
    clerk_session_created,
    clerk_session_ended,
    clerk_user_created,
    clerk_user_deleted,
    clerk_user_updated,
)

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


def parse_clerk_timestamp(timestamp: int | str | datetime | None) -> datetime | None:
    """
    Parse a Clerk timestamp into a datetime object.

    Clerk can send timestamps in various formats:
    - Unix milliseconds (integer): 1704067200000
    - ISO string: "2025-01-15T10:30:00Z"
    - datetime object: already parsed

    Args:
        timestamp: The timestamp to parse.

    Returns:
        A timezone-aware datetime object or None.
    """
    if timestamp is None:
        return None

    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp

    if isinstance(timestamp, int):
        # Unix milliseconds
        return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

    if isinstance(timestamp, str):
        # ISO format string
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            logger.warning(f"Failed to parse timestamp: {timestamp}")
            return None

    return None


def is_duplicate_webhook(event_type: str, instance_id: str) -> bool:
    """
    Check if this webhook has already been processed.

    Uses cache to prevent duplicate processing within a short window.

    Args:
        event_type: The Clerk event type.
        instance_id: The webhook instance ID.

    Returns:
        True if this is a duplicate, False otherwise.
    """
    cache_key = f"webhook:{event_type}:{instance_id}"
    if cache.get(cache_key):
        return True
    cache.set(cache_key, True, timeout=CLERK_WEBHOOK_DEDUP_TIMEOUT)
    return False


@transaction.atomic
def handle_user_created(data: dict[str, Any]) -> "AbstractClerkUser | None":
    """
    Handle user.created webhook event.

    Args:
        data: The webhook event data.

    Returns:
        The created user or None if creation failed.
    """
    from django_clerk_users.utils import update_or_create_clerk_user

    clerk_user_id = data.get("id")
    if not clerk_user_id:
        logger.error("user.created webhook missing user ID")
        return None

    try:
        user, created = update_or_create_clerk_user(clerk_user_id)

        # Emit signal
        clerk_user_created.send(
            sender=user.__class__,
            user=user,
            clerk_data=data,
        )

        logger.info(f"User created via webhook: {user.email}")
        return user

    except Exception as e:
        logger.error(f"Failed to handle user.created: {e}")
        return None


@transaction.atomic
def handle_user_updated(data: dict[str, Any]) -> "AbstractClerkUser | None":
    """
    Handle user.updated webhook event.

    Args:
        data: The webhook event data.

    Returns:
        The updated user or None if update failed.
    """
    from django_clerk_users.caching import invalidate_clerk_user_cache
    from django_clerk_users.utils import update_or_create_clerk_user

    clerk_user_id = data.get("id")
    if not clerk_user_id:
        logger.error("user.updated webhook missing user ID")
        return None

    try:
        # Invalidate cache before update
        invalidate_clerk_user_cache(clerk_user_id)

        user, created = update_or_create_clerk_user(clerk_user_id)

        # Emit signal
        clerk_user_updated.send(
            sender=user.__class__,
            user=user,
            clerk_data=data,
        )

        logger.info(f"User updated via webhook: {user.email}")
        return user

    except Exception as e:
        logger.error(f"Failed to handle user.updated: {e}")
        return None


@transaction.atomic
def handle_user_deleted(data: dict[str, Any]) -> "AbstractClerkUser | None":
    """
    Handle user.deleted webhook event.

    Performs a soft delete by setting is_active=False.

    Args:
        data: The webhook event data.

    Returns:
        The deleted user or None if deletion failed.
    """
    from django.contrib.auth import get_user_model

    from django_clerk_users.caching import invalidate_clerk_user_cache

    User = get_user_model()

    clerk_user_id = data.get("id")
    if not clerk_user_id:
        logger.error("user.deleted webhook missing user ID")
        return None

    try:
        # Invalidate cache
        invalidate_clerk_user_cache(clerk_user_id)

        user = User.objects.filter(clerk_id=clerk_user_id).first()
        if not user:
            logger.warning(f"User not found for deletion: {clerk_user_id}")
            return None

        # Soft delete
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        # Emit signal
        clerk_user_deleted.send(
            sender=user.__class__,
            user=user,
            clerk_data=data,
        )

        logger.info(f"User deleted via webhook: {user.email}")
        return user

    except Exception as e:
        logger.error(f"Failed to handle user.deleted: {e}")
        return None


@transaction.atomic
def handle_session_created(data: dict[str, Any]) -> None:
    """
    Handle session.created webhook event.

    Updates the user's last_login timestamp.

    Args:
        data: The webhook event data.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    user_id = data.get("user_id")
    if not user_id:
        logger.error("session.created webhook missing user_id")
        return

    try:
        user = User.objects.filter(clerk_id=user_id).first()
        if not user:
            logger.debug(f"User not found for session.created: {user_id}")
            return

        # Update last_login
        user.last_login = parse_clerk_timestamp(data.get("created_at"))
        user.save(update_fields=["last_login", "updated_at"])

        # Emit signal
        clerk_session_created.send(
            sender=user.__class__,
            user=user,
            clerk_data=data,
        )

    except Exception as e:
        logger.error(f"Failed to handle session.created: {e}")


@transaction.atomic
def handle_session_ended(data: dict[str, Any]) -> None:
    """
    Handle session.ended/removed/revoked webhook events.

    Updates the user's last_logout timestamp.

    Args:
        data: The webhook event data.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    user_id = data.get("user_id")
    if not user_id:
        logger.error("session.ended webhook missing user_id")
        return

    try:
        user = User.objects.filter(clerk_id=user_id).first()
        if not user:
            logger.debug(f"User not found for session.ended: {user_id}")
            return

        # Update last_logout
        user.last_logout = parse_clerk_timestamp(
            data.get("abandoned_at") or data.get("updated_at")
        )
        user.save(update_fields=["last_logout", "updated_at"])

        # Emit signal
        clerk_session_ended.send(
            sender=user.__class__,
            user=user,
            clerk_data=data,
        )

    except Exception as e:
        logger.error(f"Failed to handle session.ended: {e}")


def process_webhook_event(event_type: str, data: dict[str, Any]) -> bool:
    """
    Process a Clerk webhook event.

    This is the main entry point for webhook event handling.
    It routes events to the appropriate handler.

    Args:
        event_type: The Clerk event type (e.g., "user.created").
        data: The event data from the webhook payload.

    Returns:
        True if the event was handled successfully, False otherwise.
    """
    handlers = {
        "user.created": handle_user_created,
        "user.updated": handle_user_updated,
        "user.deleted": handle_user_deleted,
        "session.created": handle_session_created,
        "session.ended": handle_session_ended,
        "session.removed": handle_session_ended,
        "session.revoked": handle_session_ended,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(data)
            return True
        except Exception as e:
            logger.error(f"Error handling {event_type}: {e}")
            return False

    # Check if organizations app handles this event
    if event_type.startswith(("organization", "organizationMembership", "organizationInvitation")):
        try:
            from django_clerk_users.organizations.webhooks import (
                process_organization_event,
            )

            return process_organization_event(event_type, data)
        except ImportError:
            logger.debug(f"Organizations app not installed, skipping {event_type}")
            return True

    logger.debug(f"Unhandled webhook event type: {event_type}")
    return True
