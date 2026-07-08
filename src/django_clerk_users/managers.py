"""
Custom managers for django-clerk-users models.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.models import BaseUserManager

if TYPE_CHECKING:
    from django_clerk_users.models import AbstractClerkUser


class ClerkUserManager(BaseUserManager["AbstractClerkUser"]):
    """
    Custom manager for ClerkUser model.

    Handles user creation with clerk_id as the primary identifier.
    """

    def create_user(
        self,
        email: str | None = None,
        clerk_id: str | None = None,
        password: str | None = None,
        username: str | None = None,
        **extra_fields: Any,
    ) -> AbstractClerkUser:
        """
        Create and save a user with the given identifiers.

        Args:
            email: The user's email address (optional for Clerk users).
            clerk_id: The Clerk user ID (optional for Django admin users).
            password: Optional password (required for Django admin users).
            username: The user's username from Clerk (optional).
            **extra_fields: Additional fields for the user model.

        Returns:
            The created user instance.

        Raises:
            ValueError: If email is not provided for admin users (no clerk_id).
        """
        # Admin users (no clerk_id) require email for Django admin login
        if not clerk_id and not email:
            raise ValueError("The email must be set for admin users")

        if email:
            email = self.normalize_email(email)

        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(
            clerk_id=clerk_id, email=email, username=username, **extra_fields
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        clerk_id: str | None = None,
        **extra_fields: Any,
    ) -> AbstractClerkUser:
        """
        Create and save a superuser with the given email.

        Args:
            email: The user's email address (required).
            password: Password for the superuser (required for Django admin access).
            clerk_id: The Clerk user ID (optional).
            **extra_fields: Additional fields for the user model.

        Returns:
            The created superuser instance.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(
            email=email, clerk_id=clerk_id, password=password, **extra_fields
        )

    def get_by_clerk_id(self, clerk_id: str) -> AbstractClerkUser | None:
        """
        Get a user by their Clerk ID.

        Args:
            clerk_id: The Clerk user ID.

        Returns:
            The user instance or None if not found.
        """
        try:
            return self.get(clerk_id=clerk_id)
        except self.model.DoesNotExist:
            return None

    def get_by_email(self, email: str) -> AbstractClerkUser | None:
        """
        Get a user by their email address.

        Args:
            email: The user's email address.

        Returns:
            The user instance or None if not found.
        """
        try:
            return self.get(email=self.normalize_email(email))
        except self.model.DoesNotExist:
            return None

    def get_by_username(self, username: str) -> AbstractClerkUser | None:
        """
        Get a user by their username.

        Args:
            username: The user's username.

        Returns:
            The user instance or None if not found.
        """
        try:
            return self.get(username=username)
        except self.model.DoesNotExist:
            return None

    def generate_unique_username(self, prefix: str | None = None) -> str:
        """
        Generate a unique username that doesn't exist in the database.

        Uses the pattern: {prefix}_{uuid8} (e.g., "user_abc12345")

        Args:
            prefix: The username prefix. If not provided, uses CLERK_AUTO_GENERATE_USERNAME_PREFIX.

        Returns:
            A unique username string.
        """
        if prefix is None:
            prefix = getattr(settings, "CLERK_AUTO_GENERATE_USERNAME_PREFIX", "user")

        # Try up to 10 times to generate a unique username
        for _ in range(10):
            unique_id = uuid.uuid4().hex[:8]
            username = f"{prefix}_{unique_id}"
            if not self.filter(username=username).exists():
                return username

        # Fallback: use full UUID to guarantee uniqueness
        return f"{prefix}_{uuid.uuid4().hex}"
