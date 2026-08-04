"""
Clerk SDK client singleton.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from django.conf import settings

from django_clerk_users.exceptions import ClerkConfigurationError

if TYPE_CHECKING:
    from clerk_backend_api import Clerk

CLERK_NO_KEY_SENTINELS = {
    "abc123",
    "sk_test_mock_secret_key",
    "sk_live_replace_me",
}


def _normalize_secret_key(secret_key) -> str | None:
    if secret_key is None:
        return None
    if isinstance(secret_key, bytes):
        try:
            secret_key = secret_key.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(secret_key, str):
        return None

    secret_key = secret_key.strip()
    if (
        not secret_key
        or not secret_key.startswith("sk_")
        or secret_key in CLERK_NO_KEY_SENTINELS
    ):
        return None
    return secret_key


def get_configured_clerk_secret_key() -> str | None:
    secret_key = getattr(settings, "CLERK_SECRET_KEY", None)
    return _normalize_secret_key(secret_key)


def _get_configured_secret_key() -> str | None:
    return get_configured_clerk_secret_key()


@lru_cache(maxsize=1)
def get_clerk_client() -> Clerk:
    """
    Get the Clerk SDK client instance.

    Returns a cached singleton instance of the Clerk client.

    The SDK is imported here rather than at module scope so that importing this
    package does not require ``clerk-backend-api``. Session token verification
    no longer goes through the SDK, so auth-only deployments never reach this
    function.

    Raises:
        ClerkConfigurationError: If CLERK_SECRET_KEY is not set or the SDK is
            not installed.
    """
    try:
        from clerk_backend_api import Clerk as ClerkSDK
    except ImportError as exc:
        raise ClerkConfigurationError(
            "clerk-backend-api is required for Clerk server API calls. "
            "Install it with: pip install django-clerk-users[server]"
        ) from exc

    # Read directly from Django settings to get the most current value.
    clerk_secret_key = _get_configured_secret_key()
    if not clerk_secret_key:
        raise ClerkConfigurationError(
            "CLERK_SECRET_KEY is not set to a real Clerk secret key. "
            "Please configure it in your Django settings."
        )
    return ClerkSDK(bearer_auth=clerk_secret_key)


def get_clerk_sdk() -> Clerk:
    """Alias for get_clerk_client() for compatibility."""
    return get_clerk_client()
