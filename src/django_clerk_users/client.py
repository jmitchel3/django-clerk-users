"""
Clerk SDK client singleton.
"""

from functools import lru_cache

from clerk_backend_api import Clerk

from django_clerk_users.exceptions import ClerkConfigurationError
from django_clerk_users.settings import CLERK_SECRET_KEY


@lru_cache(maxsize=1)
def get_clerk_client() -> Clerk:
    """
    Get the Clerk SDK client instance.

    Returns a cached singleton instance of the Clerk client.

    Raises:
        ClerkConfigurationError: If CLERK_SECRET_KEY is not set.
    """
    if not CLERK_SECRET_KEY:
        raise ClerkConfigurationError(
            "CLERK_SECRET_KEY is not set. Please configure it in your Django settings."
        )
    return Clerk(bearer_auth=CLERK_SECRET_KEY)


def get_clerk_sdk() -> Clerk:
    """Alias for get_clerk_client() for compatibility."""
    return get_clerk_client()
