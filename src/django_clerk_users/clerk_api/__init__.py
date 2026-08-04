"""
Thin Clerk HTTP client core.

First step of decoupling this package from ``clerk-backend-api``. Provides the
three pieces the existing call sites depend on:

- :class:`~django_clerk_users.clerk_api.objects.ClerkObject`, a recursive
  attribute- and mapping-accessible response object.
- :class:`~django_clerk_users.exceptions.ClerkAPIError`, carrying
  ``status_code`` and structured ``data.errors``.
- :class:`~django_clerk_users.clerk_api.transport.ClerkTransport`, an httpx
  transport honouring ``timeout_ms``.

Endpoint resources are not part of this module yet.
"""

from django_clerk_users.clerk_api.objects import (
    ClerkObject,
    clerk_value,
    to_plain_data,
)
from django_clerk_users.clerk_api.transport import (
    CLERK_API_BASE_URL,
    CLERK_API_DEFAULT_TIMEOUT_MS,
    ClerkTransport,
)

__all__ = [
    "CLERK_API_BASE_URL",
    "CLERK_API_DEFAULT_TIMEOUT_MS",
    "ClerkObject",
    "ClerkTransport",
    "clerk_value",
    "to_plain_data",
]
