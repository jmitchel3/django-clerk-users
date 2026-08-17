"""
Caching utilities for django-clerk-users.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


# Cache key prefixes
USER_CACHE_PREFIX = "clerk:user:"
ORG_CACHE_PREFIX = "clerk:org:"
DEFAULT_CLERK_CACHE_TIMEOUT = 300
DEFAULT_CLERK_ORG_CACHE_TIMEOUT = 900


def _log_cache_failure(message: str, key: str, exc: Exception) -> None:
    """
    Report a cache backend failure without flooding the logs.

    A cache outage hits every request, so the traceback is attached only when
    DEBUG logging is on. The warning line still names the key and the cause,
    which is enough to tell a cache outage apart from an auth misconfiguration.
    """
    logger.warning(
        message,
        key,
        exc,
        exc_info=logger.isEnabledFor(logging.DEBUG),
    )


def safe_cache_get(key: str, default=None):
    """
    Read from the cache, treating a backend failure as a cache miss.

    Every cache in this package sits in front of an authoritative source
    (Clerk or the database), so a forced miss only costs a re-verification or
    a re-query. It can never make the caller accept something it would
    otherwise reject, which is why failing open is safe here.
    """
    try:
        return cache.get(key, default)
    except Exception as exc:
        _log_cache_failure(
            "Clerk cache read failed for %s (%s); treating as a cache miss", key, exc
        )
        return default


def safe_cache_set(key: str, value, timeout: int | None = None) -> bool:
    """
    Write to the cache, ignoring a backend failure.

    Returns True when the value was stored. Failing to cache must never deny a
    request that already succeeded, so callers continue uncached instead of
    raising.
    """
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except Exception as exc:
        _log_cache_failure(
            "Clerk cache write failed for %s (%s); continuing uncached", key, exc
        )
        return False


def safe_cache_delete(key: str) -> bool:
    """
    Delete a cache key, ignoring a backend failure.

    Returns True when the key was removed. This is the one fail-open case that
    is not free: a swallowed failure means the stale entry is served until it
    expires on its own, so it logs at error rather than warning.
    """
    try:
        cache.delete(key)
        return True
    except Exception as exc:
        logger.error(
            "Clerk cache invalidation failed for %s (%s); "
            "stale data may be served until the entry expires",
            key,
            exc,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        return False


def safe_cache_add(key: str, value, timeout: int | None = None, default=True) -> bool:
    """
    Add a cache key if absent, returning ``default`` on a backend failure.

    ``cache.add`` returns True when the key was absent and has now been set.
    Callers use that to claim work exactly once, so ``default`` is what the
    caller wants a cache outage to mean; it defaults to True so the work runs
    rather than being silently dropped.
    """
    try:
        return bool(cache.add(key, value, timeout=timeout))
    except Exception as exc:
        _log_cache_failure(
            "Clerk cache add failed for %s (%s); assuming the key was absent", key, exc
        )
        return default


def _get_timeout(setting_name: str, default: int) -> int:
    raw_timeout = getattr(settings, setting_name, default)
    try:
        return int(raw_timeout)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s value %r, using default %s",
            setting_name,
            raw_timeout,
            default,
        )
        return default


def _get_user_cache_timeout() -> int:
    return _get_timeout("CLERK_CACHE_TIMEOUT", DEFAULT_CLERK_CACHE_TIMEOUT)


def _get_org_cache_timeout() -> int:
    return _get_timeout("CLERK_ORG_CACHE_TIMEOUT", DEFAULT_CLERK_ORG_CACHE_TIMEOUT)


def get_user_cache_key(clerk_id: str) -> str:
    """Get the cache key for a user."""
    return f"{USER_CACHE_PREFIX}{clerk_id}"


def get_org_cache_key(clerk_id: str) -> str:
    """Get the cache key for an organization."""
    return f"{ORG_CACHE_PREFIX}{clerk_id}"


def get_cached_user(clerk_id: str, query_db: bool = True) -> AbstractClerkUser | None:
    """
    Get a user from cache or database.

    Args:
        clerk_id: The Clerk user ID.
        query_db: If True, query database on cache miss and cache the result.

    Returns:
        The user instance, or None if not found.
    """
    from django.contrib.auth import get_user_model

    if not clerk_id:
        return None

    cache_key = get_user_cache_key(clerk_id)
    cached_user = safe_cache_get(cache_key)

    if cached_user is not None:
        # Cache hit - could be a User instance or False (cached "not found")
        return cached_user if cached_user is not False else None

    if not query_db:
        return None

    # Cache miss - query database
    User = get_user_model()
    try:
        user = User.objects.get(clerk_id=clerk_id, is_active=True)
        # Cache the user instance
        safe_cache_set(cache_key, user, timeout=_get_user_cache_timeout())
        return user
    except User.DoesNotExist:
        # Cache the "not found" result to prevent repeated DB queries
        safe_cache_set(cache_key, False, timeout=_get_user_cache_timeout())
        return None


def set_cached_user(clerk_id: str, user: AbstractClerkUser | None) -> None:
    """
    Cache a user by Clerk ID.

    Args:
        clerk_id: The Clerk user ID.
        user: The user to cache, or None to cache "not found".
    """
    cache_key = get_user_cache_key(clerk_id)
    # Cache False for "not found" to distinguish from "not cached"
    value = user if user is not None else False
    safe_cache_set(cache_key, value, timeout=_get_user_cache_timeout())


def invalidate_clerk_user_cache(clerk_id: str) -> None:
    """
    Invalidate the cache for a user.

    Args:
        clerk_id: The Clerk user ID.
    """
    cache_key = get_user_cache_key(clerk_id)
    safe_cache_delete(cache_key)
    logger.debug(f"Invalidated user cache: {clerk_id}")


def get_cached_organization(clerk_id: str, query_db: bool = True):
    """
    Get an organization from cache or database.

    Args:
        clerk_id: The Clerk organization ID.
        query_db: If True, query database on cache miss and cache the result.

    Returns:
        The organization instance, or None if not found.
    """
    if not clerk_id:
        return None

    cache_key = get_org_cache_key(clerk_id)
    cached_org = safe_cache_get(cache_key)

    if cached_org is not None:
        # Cache hit - could be an Organization instance or False (cached "not found")
        return cached_org if cached_org is not False else None

    if not query_db:
        return None

    # Cache miss - query database
    from django_clerk_users.organizations.models import Organization

    try:
        org = Organization.objects.get(clerk_id=clerk_id, is_active=True)
        # Cache the organization instance
        safe_cache_set(cache_key, org, timeout=_get_org_cache_timeout())
        return org
    except Organization.DoesNotExist:
        # Cache the "not found" result to prevent repeated DB queries
        safe_cache_set(cache_key, False, timeout=_get_org_cache_timeout())
        return None


def set_cached_organization(clerk_id: str, organization) -> None:
    """
    Cache an organization by Clerk ID.

    Args:
        clerk_id: The Clerk organization ID.
        organization: The organization to cache, or None to cache "not found".
    """
    cache_key = get_org_cache_key(clerk_id)
    # Cache False for "not found" to distinguish from "not cached"
    value = organization if organization is not None else False
    safe_cache_set(cache_key, value, timeout=_get_org_cache_timeout())


def invalidate_organization_cache(clerk_id: str) -> None:
    """
    Invalidate the cache for an organization.

    Args:
        clerk_id: The Clerk organization ID.
    """
    cache_key = get_org_cache_key(clerk_id)
    safe_cache_delete(cache_key)
    logger.debug(f"Invalidated organization cache: {clerk_id}")
