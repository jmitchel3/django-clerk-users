"""
Django authentication backend for Clerk.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

if TYPE_CHECKING:
    from django.http import HttpRequest

    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


class ClerkBackend(ModelBackend):
    """
    Django authentication backend for Clerk.

    This backend extends Django's ModelBackend to add Clerk ID authentication
    while preserving standard username/password authentication. This allows:

    - Superusers to log into Django admin with email/password
    - Clerk users to authenticate via JWT tokens (clerk_id)
    - All standard Django permission checks to work as expected

    To use this backend, add it to AUTHENTICATION_BACKENDS in settings:

        AUTHENTICATION_BACKENDS = [
            'django_clerk_users.authentication.ClerkBackend',
        ]

    This is the only backend you need - it handles both Clerk authentication
    and standard Django authentication (for admin access, etc.).
    """

    def authenticate(
        self,
        request: "HttpRequest | None" = None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> "AbstractClerkUser | None":
        """
        Authenticate a user by Clerk ID or username/password.

        If a clerk_id is provided in kwargs, authenticates via Clerk ID lookup.
        Otherwise, falls back to Django's standard username/password
        authentication (inherited from ModelBackend).

        Args:
            request: The current HTTP request (optional).
            username: The username (email) for standard auth (optional).
            password: The password for standard auth (optional).
            **kwargs: Additional keyword arguments. If 'clerk_id' is present,
                      Clerk authentication is used instead of password auth.

        Returns:
            The authenticated user or None if authentication fails.
        """
        # If clerk_id is provided, authenticate via Clerk
        clerk_id = kwargs.pop("clerk_id", None)
        if clerk_id:
            User = get_user_model()

            try:
                user = User.objects.get(clerk_id=clerk_id)
                if user.is_active:
                    return user
                logger.debug(f"User {clerk_id} is inactive")
                return None
            except User.DoesNotExist:
                logger.debug(f"No user found with clerk_id: {clerk_id}")
                return None

        # Otherwise, fall back to standard Django authentication
        # This enables superuser login via Django admin
        return super().authenticate(request, username, password, **kwargs)
