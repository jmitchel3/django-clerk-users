"""
Clerk SDK client singleton.
"""

from functools import lru_cache

from clerk_backend_api import Clerk
from django.conf import settings

from django_clerk_users.exceptions import ClerkConfigurationError


@lru_cache(maxsize=1)
def get_clerk_client() -> Clerk:
    """
    Get the Clerk SDK client instance.

    Returns a cached singleton instance of the Clerk client.

    Raises:
        ClerkConfigurationError: If CLERK_SECRET_KEY is not set.
    """
    # Read directly from Django settings to get the most current value
    clerk_secret_key = getattr(settings, "CLERK_SECRET_KEY", None)
    if not clerk_secret_key:
        raise ClerkConfigurationError(
            "CLERK_SECRET_KEY is not set. Please configure it in your Django settings."
        )
    return Clerk(bearer_auth=clerk_secret_key)


def get_clerk_sdk() -> Clerk:
    """Alias for get_clerk_client() for compatibility."""
    return get_clerk_client()
