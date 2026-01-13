"""
Core utilities for django-clerk-users.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django_clerk_users.caching import (
    get_cached_user,
    invalidate_clerk_user_cache,
    set_cached_user,
)
from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import ClerkAPIError, ClerkUserNotFoundError

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


def update_or_create_clerk_user(
    clerk_user_id: str,
) -> tuple["AbstractClerkUser", bool]:
    """
    Update or create a Django user from Clerk data.

    Fetches user data from the Clerk API and creates or updates
    the corresponding Django user. If a user with the same email
    already exists (e.g., a superuser created via createsuperuser),
    it will be linked to the Clerk ID rather than creating a duplicate.

    Args:
        clerk_user_id: The Clerk user ID.

    Returns:
        A tuple of (user, created) where created is True if the user was
        newly created.

    Raises:
        ClerkUserNotFoundError: If the user is not found in Clerk.
        ClerkAPIError: If the Clerk API returns an error.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        # Fetch user from Clerk API
        clerk = get_clerk_client()
        clerk_user = clerk.users.get(user_id=clerk_user_id)

        if not clerk_user:
            raise ClerkUserNotFoundError(f"User not found in Clerk: {clerk_user_id}")

        # Extract email from email_addresses array
        primary_email = None
        email_addresses = getattr(clerk_user, "email_addresses", []) or []
        for email_obj in email_addresses:
            email_id = getattr(clerk_user, "primary_email_address_id", None)
            if email_id and getattr(email_obj, "id", None) == email_id:
                primary_email = getattr(email_obj, "email_address", None)
                break
        if not primary_email and email_addresses:
            # Fallback to first email
            primary_email = getattr(email_addresses[0], "email_address", None)

        if not primary_email:
            raise ClerkAPIError(f"User {clerk_user_id} has no email address")

        # Prepare user data
        user_data = {
            "first_name": getattr(clerk_user, "first_name", "") or "",
            "last_name": getattr(clerk_user, "last_name", "") or "",
            "image_url": getattr(clerk_user, "image_url", "") or "",
        }

        # First, try to find by clerk_id
        user = User.objects.filter(clerk_id=clerk_user_id).first()
        created = False

        if user:
            # Update existing Clerk-linked user
            for key, value in user_data.items():
                setattr(user, key, value)
            user.email = primary_email
            user.save()
        else:
            # No user with this clerk_id - check if email already exists
            user = User.objects.filter(email__iexact=primary_email).first()

            if user:
                # Link existing Django user to Clerk
                user.clerk_id = clerk_user_id
                for key, value in user_data.items():
                    setattr(user, key, value)
                user.save()
                logger.info(
                    f"Linked existing user {user.email} to Clerk ID {clerk_user_id}"
                )
            else:
                # Create new user
                user = User.objects.create(
                    clerk_id=clerk_user_id,
                    email=primary_email,
                    **user_data,
                )
                created = True

        # Update cache
        set_cached_user(clerk_user_id, user)

        return user, created

    except ClerkUserNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch/create user from Clerk: {e}")
        raise ClerkAPIError(f"Failed to fetch user from Clerk: {e}") from e


def get_clerk_user(clerk_user_id: str) -> "AbstractClerkUser | None":
    """
    Get a Django user by their Clerk ID.

    Checks the cache first, then the database.

    Args:
        clerk_user_id: The Clerk user ID.

    Returns:
        The user instance or None if not found.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Check cache first
    cached = get_cached_user(clerk_user_id)
    if cached is not None:
        if cached is False:
            return None  # Cached as "not found"
        return cached

    # Query database
    user = User.objects.filter(clerk_id=clerk_user_id).first()

    # Update cache
    set_cached_user(clerk_user_id, user)

    return user


def sync_user_from_clerk(clerk_user_id: str) -> "AbstractClerkUser | None":
    """
    Force sync a user from Clerk, ignoring cache.

    Args:
        clerk_user_id: The Clerk user ID.

    Returns:
        The synced user or None if sync failed.
    """
    # Invalidate cache
    invalidate_clerk_user_cache(clerk_user_id)

    try:
        user, _ = update_or_create_clerk_user(clerk_user_id)
        return user
    except Exception as e:
        logger.error(f"Failed to sync user: {e}")
        return None


def get_user_metadata(clerk_user_id: str) -> dict[str, Any]:
    """
    Get user metadata from Clerk.

    Args:
        clerk_user_id: The Clerk user ID.

    Returns:
        A dict containing public and private metadata.
    """
    try:
        clerk = get_clerk_client()
        clerk_user = clerk.users.get(user_id=clerk_user_id)

        if not clerk_user:
            return {"public": {}, "private": {}}

        return {
            "public": getattr(clerk_user, "public_metadata", {}) or {},
            "private": getattr(clerk_user, "private_metadata", {}) or {},
        }

    except Exception as e:
        logger.error(f"Failed to get user metadata: {e}")
        return {"public": {}, "private": {}}


def update_user_metadata(
    clerk_user_id: str,
    public_metadata: dict[str, Any] | None = None,
    private_metadata: dict[str, Any] | None = None,
) -> bool:
    """
    Update user metadata in Clerk.

    Args:
        clerk_user_id: The Clerk user ID.
        public_metadata: Public metadata to merge (optional).
        private_metadata: Private metadata to merge (optional).

    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        clerk = get_clerk_client()

        update_data = {}
        if public_metadata is not None:
            update_data["public_metadata"] = public_metadata
        if private_metadata is not None:
            update_data["private_metadata"] = private_metadata

        if not update_data:
            return True

        clerk.users.update(user_id=clerk_user_id, **update_data)
        return True

    except Exception as e:
        logger.error(f"Failed to update user metadata: {e}")
        return False
