"""
Django authentication backend for Clerk.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

if TYPE_CHECKING:
    from django.http import HttpRequest

    from django_clerk_users.models import AbstractClerkUser

logger = logging.getLogger(__name__)


class ClerkBackend(BaseBackend):
    """
    Django authentication backend for Clerk.

    This backend authenticates users by their Clerk ID rather than
    username/password. It's designed to work with Clerk's JWT-based
    authentication.

    To use this backend, add it to AUTHENTICATION_BACKENDS in settings:

        AUTHENTICATION_BACKENDS = [
            'django_clerk_users.authentication.ClerkBackend',
        ]
    """

    def authenticate(
        self,
        request: "HttpRequest | None" = None,
        clerk_id: str | None = None,
        **kwargs: Any,
    ) -> "AbstractClerkUser | None":
        """
        Authenticate a user by their Clerk ID.

        Args:
            request: The current HTTP request (optional).
            clerk_id: The Clerk user ID to authenticate.
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            The authenticated user or None if authentication fails.
        """
        if not clerk_id:
            return None

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

    def get_user(self, user_id: int) -> "AbstractClerkUser | None":
        """
        Get a user by their Django primary key.

        This method is called by Django's authentication middleware
        to restore the user from the session.

        Args:
            user_id: The user's primary key.

        Returns:
            The user instance or None if not found.
        """
        User = get_user_model()

        try:
            user = User.objects.get(pk=user_id)
            if user.is_active:
                return user
            return None
        except User.DoesNotExist:
            return None
