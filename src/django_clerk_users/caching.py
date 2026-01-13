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


def get_cached_user(clerk_id: str, query_db: bool = True) -> "AbstractClerkUser | None":
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
    cached_user = cache.get(cache_key)

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
        cache.set(cache_key, user, timeout=CLERK_CACHE_TIMEOUT)
        return user
    except User.DoesNotExist:
        # Cache the "not found" result to prevent repeated DB queries
        cache.set(cache_key, False, timeout=CLERK_CACHE_TIMEOUT)
        return None


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
    cached_org = cache.get(cache_key)

    if cached_org is not None:
        # Cache hit - could be an Organization instance or False (cached "not found")
        return cached_org if cached_org is not False else None

    if not query_db:
        return None

    # Cache miss - query database
    try:
        from django_clerk_users.organizations.models import Organization

        org = Organization.objects.get(clerk_id=clerk_id, is_active=True)
        # Cache the organization instance
        cache.set(cache_key, org, timeout=CLERK_ORG_CACHE_TIMEOUT)
        return org
    except Exception:
        # Cache the "not found" result to prevent repeated DB queries
        cache.set(cache_key, False, timeout=CLERK_ORG_CACHE_TIMEOUT)
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
