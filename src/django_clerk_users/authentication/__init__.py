"""
Authentication backends and utilities for django-clerk-users.
"""

from django_clerk_users.authentication.backends import ClerkBackend
from django_clerk_users.authentication.utils import (
    get_clerk_payload_from_request,
    get_or_create_user_from_payload,
)

__all__ = [
    "ClerkBackend",
    "get_clerk_payload_from_request",
    "get_or_create_user_from_payload",
]

# Conditionally export DRF authentication if available
try:
    from django_clerk_users.authentication.drf import ClerkAuthentication

    __all__.append("ClerkAuthentication")
except ImportError:
    # DRF is not installed
    pass
