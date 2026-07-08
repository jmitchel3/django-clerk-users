"""
Authentication utilities for JWT token validation and user retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from clerk_backend_api.security.types import AuthenticateRequestOptions
from django.conf import settings
from django.core.cache import cache

from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import (
    ClerkAuthenticationError,
    ClerkConfigurationError,
    ClerkTokenError,
)

if TYPE_CHECKING:
    from django.http import HttpRequest

    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)

DEFAULT_CLERK_CACHE_TIMEOUT = 300


def _get_int_setting(setting_name: str, default: int) -> int:
    raw_value = getattr(settings, setting_name, default)
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s value %r, using default %s",
            setting_name,
            raw_value,
            default,
        )
        return default


def _coerce_string_list(value: Any, setting_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Invalid %s bytes value, using an empty list", setting_name)
            return []
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, list | tuple | set):
        raw_values = value
    else:
        logger.warning("Invalid %s value %r, using an empty list", setting_name, value)
        return []

    values = []
    for item in raw_values:
        if item is None:
            continue
        if isinstance(item, bytes):
            try:
                item = item.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Invalid %s bytes item, skipping it", setting_name)
                continue
        item = str(item).strip()
        if item:
            values.append(item)
    return values


def _get_auth_parties() -> list[str]:
    raw_auth_parties = getattr(
        settings,
        "CLERK_AUTH_PARTIES",
        getattr(settings, "CLERK_FRONTEND_HOSTS", []),
    )
    return _coerce_string_list(raw_auth_parties, "CLERK_AUTH_PARTIES")


def _get_cache_timeout() -> int:
    return _get_int_setting("CLERK_CACHE_TIMEOUT", DEFAULT_CLERK_CACHE_TIMEOUT)


def _payload_cache_timeout(payload: dict[str, Any], *, now: int | None = None) -> int:
    """
    Return a cache timeout that cannot outlive the token's safe lifetime.

    Clerk session tokens include an ``exp`` claim. Cache payloads only until one
    minute before that expiry; tokens already within that final minute are not
    cached at all.
    """
    configured_timeout = _get_cache_timeout()
    if configured_timeout <= 0:
        return 0

    exp = payload.get("exp")
    if exp is None:
        return configured_timeout

    try:
        expires_at = int(exp)
    except (TypeError, ValueError):
        return configured_timeout

    current_time = int(time.time()) if now is None else now
    seconds_until_expiry = expires_at - current_time
    if seconds_until_expiry <= 60:
        return 0

    return min(seconds_until_expiry - 60, configured_timeout)


def get_bearer_token(request: HttpRequest) -> str | None:
    """
    Extract the Bearer token from the Authorization header.

    Args:
        request: The Django HTTP request.

    Returns:
        The bearer token string or None if not present.
    """
    auth_header = request.headers.get("Authorization", "")
    if isinstance(auth_header, bytes):
        auth_header = auth_header.decode("latin1")

    parts = auth_header.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def get_clerk_payload_from_request(request: HttpRequest) -> dict[str, Any] | None:
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
        auth_parties = _get_auth_parties()
        if auth_parties:
            auth_options = AuthenticateRequestOptions(authorized_parties=auth_parties)

        # Validate the token using Clerk SDK
        request_state = clerk.authenticate_request(request, options=auth_options)

        if not request_state.is_signed_in:
            reason = getattr(request_state, "message", None) or "not signed in"
            logger.debug("Clerk token validation failed: %s", reason)
            raise ClerkTokenError(f"Token validation failed: {reason}")

        payload = request_state.payload
        if not payload:
            logger.debug("Clerk token validation failed: no payload")
            raise ClerkTokenError("Token validation failed: no payload")

        # Calculate cache timeout based on token expiration
        # This ensures we never use an expired token from cache
        cache_timeout = _payload_cache_timeout(payload)
        if cache_timeout > 0:
            cache.set(cache_key, payload, timeout=cache_timeout)
            logger.debug("Cached Clerk payload for %s seconds", cache_timeout)

        return payload

    except ClerkTokenError:
        raise
    except Exception as e:
        logger.warning(f"Clerk token validation error: {e}")
        raise ClerkTokenError(f"Token validation failed: {e}") from e


def get_or_create_user_from_payload(
    payload: dict[str, Any],
) -> tuple[AbstractClerkUser, bool]:
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


def get_user_from_clerk_id(clerk_id: str) -> AbstractClerkUser | None:
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
