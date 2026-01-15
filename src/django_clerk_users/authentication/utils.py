"""
Authentication utilities for JWT token validation and user retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from clerk_backend_api.security.types import AuthenticateRequestOptions
from django.core.cache import cache

from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import (
    ClerkAuthenticationError,
    ClerkConfigurationError,
    ClerkTokenError,
)
from django_clerk_users.settings import CLERK_AUTH_PARTIES, CLERK_CACHE_TIMEOUT

if TYPE_CHECKING:
    from django.http import HttpRequest

    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


def get_bearer_token(request: "HttpRequest") -> str | None:
    """
    Extract the Bearer token from the Authorization header.

    Args:
        request: The Django HTTP request.

    Returns:
        The bearer token string or None if not present.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix
    return None


def get_clerk_payload_from_request(request: "HttpRequest") -> dict[str, Any] | None:
    """
    Validate a Clerk JWT token and return the payload.

    This function extracts the JWT from the Authorization header,
    validates it using the Clerk SDK, and returns the decoded payload.
    Results are cached to avoid repeated validation.

    Args:
        request: The Django HTTP request.

    Returns:
        The decoded JWT payload dict or None if validation fails.

    Raises:
        ClerkTokenError: If the token is invalid or expired.
    """
    token = get_bearer_token(request)
    if not token:
        return None

    # Create a cache key based on the token hash (never store raw tokens)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache_key = f"clerk:payload:{token_hash}"

    # Check cache first
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        return cached_payload

    try:
        clerk = get_clerk_client()
    except ClerkConfigurationError:
        # Clerk is not configured, skip authentication silently
        return None

    try:
        # Build auth options with authorized parties
        auth_options = None
        if CLERK_AUTH_PARTIES:
            auth_options = AuthenticateRequestOptions(
                authorized_parties=CLERK_AUTH_PARTIES
            )

        # Validate the token using Clerk SDK
        request_state = clerk.authenticate_request(request, options=auth_options)

        if not request_state.is_signed_in:
            logger.debug("Clerk token validation failed: not signed in")
            return None

        payload = request_state.payload
        if not payload:
            logger.debug("Clerk token validation failed: no payload")
            return None

        # Calculate cache timeout based on token expiration
        # This ensures we never use an expired token from cache
        exp = payload.get("exp")
        if exp:
            current_time = int(time.time())
            # Cache until 1 minute before expiration, with a minimum of 60s
            # and maximum of CLERK_CACHE_TIMEOUT (default 5 minutes)
            time_until_exp = exp - current_time
            cache_timeout = max(60, min(time_until_exp - 60, CLERK_CACHE_TIMEOUT))
        else:
            # Default to cache timeout if no exp claim
            cache_timeout = CLERK_CACHE_TIMEOUT

        cache.set(cache_key, payload, timeout=cache_timeout)
        logger.debug(f"Cached Clerk payload for {cache_timeout} seconds")

        return payload

    except Exception as e:
        logger.warning(f"Clerk token validation error: {e}")
        raise ClerkTokenError(f"Token validation failed: {e}") from e


def get_or_create_user_from_payload(
    payload: dict[str, Any],
) -> tuple["AbstractClerkUser", bool]:
    """
    Get or create a Django user from a Clerk JWT payload.

    Args:
        payload: The decoded Clerk JWT payload.

    Returns:
        A tuple of (user, created) where created is True if the user was newly created.

    Raises:
        ClerkAuthenticationError: If the payload is invalid or user creation fails.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise ClerkAuthenticationError("Invalid payload: missing 'sub' claim")

    # Try to get existing user first
    user = User.objects.filter(clerk_id=clerk_user_id).first()
    if user:
        return user, False

    # User doesn't exist - we need to create them
    # Fetch full user data from Clerk API
    try:
        from django_clerk_users.utils import update_or_create_clerk_user

        user, created = update_or_create_clerk_user(clerk_user_id)
        return user, created
    except Exception as e:
        logger.error(f"Failed to create user from Clerk: {e}")
        raise ClerkAuthenticationError(f"Failed to create user: {e}") from e


def get_user_from_clerk_id(clerk_id: str) -> "AbstractClerkUser | None":
    """
    Get a Django user by their Clerk ID.

    Args:
        clerk_id: The Clerk user ID.

    Returns:
        The user instance or None if not found.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.filter(clerk_id=clerk_id).first()
