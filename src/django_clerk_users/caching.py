"""
Caching utilities for django-clerk-users.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.cache import cache

from django_clerk_users.settings import CLERK_CACHE_TIMEOUT, CLERK_ORG_CACHE_TIMEOUT

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


# Cache key prefixes
USER_CACHE_PREFIX = "clerk:user:"
ORG_CACHE_PREFIX = "clerk:org:"


def get_user_cache_key(clerk_id: str) -> str:
    """Get the cache key for a user."""
    return f"{USER_CACHE_PREFIX}{clerk_id}"


def get_org_cache_key(clerk_id: str) -> str:
    """Get the cache key for an organization."""
    return f"{ORG_CACHE_PREFIX}{clerk_id}"


def get_cached_user(clerk_id: str) -> "AbstractClerkUser | None | bool":
    """
    Get a cached user by Clerk ID.

    Args:
        clerk_id: The Clerk user ID.

    Returns:
        The cached user, None if not in cache, or False if user was not found
        (to distinguish between "not cached" and "cached as not found").
    """
    cache_key = get_user_cache_key(clerk_id)
    return cache.get(cache_key)


def set_cached_user(clerk_id: str, user: "AbstractClerkUser | None") -> None:
    """
    Cache a user by Clerk ID.

    Args:
        clerk_id: The Clerk user ID.
        user: The user to cache, or None to cache "not found".
    """
    cache_key = get_user_cache_key(clerk_id)
    # Cache False for "not found" to distinguish from "not cached"
    value = user if user is not None else False
    cache.set(cache_key, value, timeout=CLERK_CACHE_TIMEOUT)


def invalidate_clerk_user_cache(clerk_id: str) -> None:
    """
    Invalidate the cache for a user.

    Args:
        clerk_id: The Clerk user ID.
    """
    cache_key = get_user_cache_key(clerk_id)
    cache.delete(cache_key)
    logger.debug(f"Invalidated user cache: {clerk_id}")


def get_cached_organization(clerk_id: str):
    """
    Get a cached organization by Clerk ID.

    Args:
        clerk_id: The Clerk organization ID.

    Returns:
        The cached organization, None if not in cache, or False if org was not found.
    """
    cache_key = get_org_cache_key(clerk_id)
    return cache.get(cache_key)


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
    cache.set(cache_key, value, timeout=CLERK_ORG_CACHE_TIMEOUT)


def invalidate_organization_cache(clerk_id: str) -> None:
    """
    Invalidate the cache for an organization.

    Args:
        clerk_id: The Clerk organization ID.
    """
    cache_key = get_org_cache_key(clerk_id)
    cache.delete(cache_key)
    logger.debug(f"Invalidated organization cache: {clerk_id}")
