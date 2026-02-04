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
) -> tuple[AbstractClerkUser, bool]:
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

        # Extract username (optional in Clerk)
        username = getattr(clerk_user, "username", None)

        # Auto-generate username if enabled and user doesn't have one
        if username is None:
            from django_clerk_users.settings import CLERK_AUTO_GENERATE_USERNAME

            if CLERK_AUTO_GENERATE_USERNAME:
                username = User.objects.generate_unique_username()

        # Note: Both email and username can be null - clerk_id is the only required identifier

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
            user.username = username
            user.save()
        else:
            # No user with this clerk_id - try to find by email or username
            existing_user = None

            # Try email first (if present)
            if primary_email:
                existing_user = User.objects.filter(email__iexact=primary_email).first()

            # Try username if no match by email (and username is present)
            if not existing_user and username:
                existing_user = User.objects.filter(username=username).first()

            if existing_user:
                # Link existing Django user to Clerk
                existing_user.clerk_id = clerk_user_id
                existing_user.email = primary_email
                existing_user.username = username
                for key, value in user_data.items():
                    setattr(existing_user, key, value)
                existing_user.save()
                user = existing_user
                identifier = primary_email or username or clerk_user_id
                logger.info(
                    f"Linked existing user {identifier} to Clerk ID {clerk_user_id}"
                )
            else:
                # Create new user
                user = User.objects.create(
                    clerk_id=clerk_user_id,
                    email=primary_email,
                    username=username,
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


def get_clerk_user(clerk_user_id: str) -> AbstractClerkUser | None:
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


def sync_user_from_clerk(clerk_user_id: str) -> AbstractClerkUser | None:
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


def generate_username_for_user(
    user_id: int | str,
    prefix: str | None = None,
    force: bool = False,
) -> str | None:
    """
    Generate and set a username for a user who doesn't have one.

    This function is designed to be called from async task queues like
    Celery or django-qstash to generate usernames outside the request loop.

    Args:
        user_id: The Django user ID (pk) or Clerk user ID (clerk_id).
        prefix: Optional username prefix. Uses CLERK_AUTO_GENERATE_USERNAME_PREFIX if not provided.
        force: If True, regenerate username even if user already has one.

    Returns:
        The generated username, or None if user not found or already has username (and force=False).

    Example usage with Celery:
        @celery_app.task
        def generate_username_task(user_id: int):
            from django_clerk_users.utils import generate_username_for_user
            return generate_username_for_user(user_id)

    Example usage with django-qstash:
        @stash.task()
        def generate_username_task(user_id: int):
            from django_clerk_users.utils import generate_username_for_user
            return generate_username_for_user(user_id)
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Find user by pk or clerk_id
    user = None
    if isinstance(user_id, int):
        user = User.objects.filter(pk=user_id).first()
    else:
        # Try as clerk_id first, then as pk string
        user = User.objects.filter(clerk_id=user_id).first()
        if not user:
            try:
                user = User.objects.filter(pk=int(user_id)).first()
            except (ValueError, TypeError):
                pass

    if not user:
        logger.warning(f"User not found for username generation: {user_id}")
        return None

    if user.username and not force:
        logger.debug(f"User {user_id} already has username: {user.username}")
        return user.username

    # Generate and save username
    username = User.objects.generate_unique_username(prefix=prefix)
    user.username = username
    user.save(update_fields=["username"])

    logger.info(f"Generated username '{username}' for user {user_id}")
    return username


def generate_usernames_for_users_without(
    prefix: str | None = None,
    batch_size: int = 100,
) -> int:
    """
    Generate usernames for all users who don't have one.

    This function is designed to be called from async task queues like
    Celery or django-qstash to backfill usernames for existing users.

    Args:
        prefix: Optional username prefix. Uses CLERK_AUTO_GENERATE_USERNAME_PREFIX if not provided.
        batch_size: Number of users to process per batch (default: 100).

    Returns:
        The number of users updated.

    Example usage with Celery:
        @celery_app.task
        def backfill_usernames_task():
            from django_clerk_users.utils import generate_usernames_for_users_without
            return generate_usernames_for_users_without()

    Example usage with django-qstash:
        @stash.task()
        def backfill_usernames_task():
            from django_clerk_users.utils import generate_usernames_for_users_without
            return generate_usernames_for_users_without()
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    updated_count = 0
    users_without_username = User.objects.filter(username__isnull=True).iterator(
        chunk_size=batch_size
    )

    for user in users_without_username:
        username = User.objects.generate_unique_username(prefix=prefix)
        user.username = username
        user.save(update_fields=["username"])
        updated_count += 1

    if updated_count > 0:
        logger.info(f"Generated usernames for {updated_count} users")

    return updated_count
