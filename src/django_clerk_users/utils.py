"""
Core utilities for django-clerk-users.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Callable

from django.conf import settings
from django.db import IntegrityError, transaction

from django_clerk_users.caching import (
    get_cached_user,
    invalidate_clerk_user_cache,
    set_cached_user,
)
from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import (
    ClerkAPIError,
    ClerkUserMergeConflictError,
    ClerkUserNotFoundError,
)
from django_clerk_users.settings import _coerce_bool

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)
CLERK_API_DEFAULT_TIMEOUT_MS = 10_000


class _ClerkIdCreateRace(Exception):
    """Raised when local Clerk user creation may have lost a concurrent race."""


def _auto_generate_username_enabled() -> bool:
    return _coerce_bool(getattr(settings, "CLERK_AUTO_GENERATE_USERNAME", False), False)


def _clerk_timeout_options() -> dict[str, int]:
    raw_timeout = getattr(
        settings, "CLERK_API_TIMEOUT_MS", CLERK_API_DEFAULT_TIMEOUT_MS
    )
    try:
        timeout_ms = int(raw_timeout)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid CLERK_API_TIMEOUT_MS value %r, using default %s",
            raw_timeout,
            CLERK_API_DEFAULT_TIMEOUT_MS,
        )
        timeout_ms = CLERK_API_DEFAULT_TIMEOUT_MS

    if timeout_ms <= 0:
        logger.warning(
            "Non-positive CLERK_API_TIMEOUT_MS value %r, using default %s",
            raw_timeout,
            CLERK_API_DEFAULT_TIMEOUT_MS,
        )
        timeout_ms = CLERK_API_DEFAULT_TIMEOUT_MS

    return {"timeout_ms": timeout_ms}


def _clerk_list_data(response: Any) -> list[Any]:
    """Return list endpoint data for both SDK pagination objects and lists."""
    if response is None:
        return []
    if isinstance(response, Mapping):
        data = response.get("data", response)
    else:
        data = getattr(response, "data", response)
    if data is None:
        return []
    return list(data)


def _default_duplicate_is_disposable(user: AbstractClerkUser) -> bool:
    return not (
        user.is_staff
        or user.is_superuser
        or user.has_usable_password()
        or user.groups.exists()
        or user.user_permissions.exists()
    )


def absorb_clerk_user_duplicate(
    target_user: AbstractClerkUser,
    *,
    email: str | None = None,
    duplicate_user: AbstractClerkUser | None = None,
    safe_to_delete: Callable[[AbstractClerkUser], bool] | None = None,
    delete_duplicate: bool = True,
    replace_existing_clerk_id: bool = True,
) -> bool:
    """
    Move a Clerk identity from a fresh duplicate user onto a target user.

    This is for claim/conversion flows where Clerk creates a new Django user for
    a real email before the app links that Clerk identity to a pre-existing
    account. The helper deliberately does not run during normal authentication;
    call it only when your app has confirmed the target account and duplicate
    policy.

    Args:
        target_user: The existing Django user that should receive the Clerk ID.
        email: Case-insensitive email used to locate the duplicate when
            duplicate_user is not provided.
        duplicate_user: Explicit duplicate user to absorb.
        safe_to_delete: Optional predicate for app-specific data checks. Return
            True only when deleting or clearing the duplicate is safe. Without a
            predicate, only a simple unelevated passwordless user is disposable.
        delete_duplicate: Delete the duplicate row after moving its Clerk ID.
            Set False only if your app has a separate retirement strategy.
        replace_existing_clerk_id: Allow replacing target_user.clerk_id when it
            already has a different Clerk ID.

    Returns:
        True when a duplicate was found and absorbed, otherwise False.

    Raises:
        ValueError: If neither email nor duplicate_user is provided.
        ClerkUserMergeConflictError: If the duplicate is not disposable or the
            target already has a different Clerk ID and replacement is disabled.
    """
    if duplicate_user is None and not email:
        raise ValueError("email or duplicate_user is required")

    from django.contrib.auth import get_user_model

    User = get_user_model()

    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=target_user.pk)

        if duplicate_user is not None:
            if duplicate_user.pk == target.pk:
                return False
            duplicate = (
                User.objects.select_for_update().filter(pk=duplicate_user.pk).first()
            )
        else:
            duplicate = (
                User.objects.select_for_update()
                .filter(email__iexact=email)
                .exclude(pk=target.pk)
                .first()
            )

        if duplicate is None:
            return False

        predicate = safe_to_delete or _default_duplicate_is_disposable
        if not predicate(duplicate):
            identifier = email or duplicate.pk
            raise ClerkUserMergeConflictError(
                f"User {duplicate.pk} already holds {identifier} and is not safe "
                "to absorb automatically."
            )

        old_clerk_id = target.clerk_id
        new_clerk_id = duplicate.clerk_id

        if (
            old_clerk_id
            and new_clerk_id
            and old_clerk_id != new_clerk_id
            and not replace_existing_clerk_id
        ):
            raise ClerkUserMergeConflictError(
                f"Target user {target.pk} already has Clerk ID {old_clerk_id}."
            )

        if delete_duplicate:
            duplicate_pk = duplicate.pk
            duplicate.delete()
            duplicate_deleted = True
        else:
            duplicate_pk = duplicate.pk
            duplicate_deleted = False
            if new_clerk_id:
                duplicate.clerk_id = None
                duplicate.save(update_fields=["clerk_id"])
                if duplicate_user is not None:
                    duplicate_user.clerk_id = None

        if new_clerk_id and target.clerk_id != new_clerk_id:
            target.clerk_id = new_clerk_id
            target.save(update_fields=["clerk_id"])

        target_user.clerk_id = target.clerk_id

    for clerk_id in {old_clerk_id, new_clerk_id}:
        if clerk_id:
            invalidate_clerk_user_cache(clerk_id)

    logger.info(
        "Absorbed Clerk duplicate user %s into user %s (clerk_id=%s, deleted=%s)",
        duplicate_pk,
        target_user.pk,
        new_clerk_id or "-",
        duplicate_deleted,
    )
    return True


def _upsert_local_clerk_user(
    User: Any,
    clerk_user_id: str,
    *,
    primary_email: str | None,
    username: str | None,
    user_data: dict[str, Any],
) -> tuple[AbstractClerkUser, bool]:
    """Create, update, or link the local Django user for a Clerk identity."""
    user = User.objects.select_for_update().filter(clerk_id=clerk_user_id).first()
    created = False

    if user:
        for key, value in user_data.items():
            setattr(user, key, value)
        user.email = primary_email
        user.username = username
        user.save()
        return user, created

    existing_user = None
    if primary_email:
        existing_user = (
            User.objects.select_for_update().filter(email__iexact=primary_email).first()
        )
    if not existing_user and username:
        existing_user = (
            User.objects.select_for_update().filter(username=username).first()
        )

    if existing_user:
        existing_user.clerk_id = clerk_user_id
        existing_user.email = primary_email
        existing_user.username = username
        for key, value in user_data.items():
            setattr(existing_user, key, value)
        existing_user.save()
        identifier = primary_email or username or clerk_user_id
        logger.info("Linked existing user %s to Clerk ID %s", identifier, clerk_user_id)
        return existing_user, created

    try:
        user = User.objects.create(
            clerk_id=clerk_user_id,
            email=primary_email,
            username=username,
            **user_data,
        )
    except IntegrityError as exc:
        raise _ClerkIdCreateRace from exc
    created = True
    return user, created


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
        clerk_user = clerk.users.get(
            user_id=clerk_user_id,
            **_clerk_timeout_options(),
        )

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
            if _auto_generate_username_enabled():
                username = User.objects.generate_unique_username()

        # Note: Both email and username can be null - clerk_id is the only required identifier

        # Prepare user data
        user_data = {
            "first_name": getattr(clerk_user, "first_name", "") or "",
            "last_name": getattr(clerk_user, "last_name", "") or "",
            "image_url": getattr(clerk_user, "image_url", "") or "",
        }

        try:
            with transaction.atomic():
                user, created = _upsert_local_clerk_user(
                    User,
                    clerk_user_id,
                    primary_email=primary_email,
                    username=username,
                    user_data=user_data,
                )
        except _ClerkIdCreateRace:
            user = User.objects.filter(clerk_id=clerk_user_id).first()
            if not user:
                raise
            created = False
            logger.info(
                "Recovered local user sync after Clerk ID race for %s",
                clerk_user_id,
            )

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
        clerk_user = clerk.users.get(
            user_id=clerk_user_id,
            **_clerk_timeout_options(),
        )

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

        clerk.users.update(
            user_id=clerk_user_id,
            **update_data,
            **_clerk_timeout_options(),
        )
        return True

    except Exception as e:
        logger.error(f"Failed to update user metadata: {e}")
        return False


def generate_username_for_user(
    user_id: int | str,
    prefix: str | None = None,
    force: bool = False,
    sync_to_clerk: bool = True,
) -> str | None:
    """
    Generate and set a username for a user who doesn't have one.

    This function is designed to be called from async task queues like
    Celery or django-qstash to generate usernames outside the request loop.

    Args:
        user_id: The Django user ID (pk) or Clerk user ID (clerk_id).
        prefix: Optional username prefix. Uses CLERK_AUTO_GENERATE_USERNAME_PREFIX if not provided.
        force: If True, regenerate username even if user already has one.
        sync_to_clerk: If True (default), sync the username to Clerk.

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

    # Sync to Clerk if enabled and user has a clerk_id
    if sync_to_clerk and user.clerk_id:
        try:
            clerk = get_clerk_client()
            clerk.users.update(
                user_id=user.clerk_id,
                username=username,
                **_clerk_timeout_options(),
            )
            logger.info(f"Synced username '{username}' to Clerk for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to sync username to Clerk for user {user_id}: {e}")

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
