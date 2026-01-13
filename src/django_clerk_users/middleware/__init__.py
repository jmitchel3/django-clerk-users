"""
Middleware for django-clerk-users.
"""

from django_clerk_users.middleware.auth import ClerkAuthMiddleware

__all__ = [
    "ClerkAuthMiddleware",
]
