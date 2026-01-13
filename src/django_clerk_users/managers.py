"""
Custom managers for django-clerk-users models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
        clerk_id: str,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "AbstractClerkUser":
        """
        Create and save a user with the given clerk_id and email.

        Args:
            clerk_id: The Clerk user ID.
            email: The user's email address.
            password: Optional password (not used for Clerk auth, but required
                     for Django admin compatibility).
            **extra_fields: Additional fields for the user model.

        Returns:
            The created user instance.

        Raises:
            ValueError: If clerk_id or email is not provided.
        """
        if not clerk_id:
            raise ValueError("The clerk_id must be set")
        if not email:
            raise ValueError("The email must be set")

        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(clerk_id=clerk_id, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        clerk_id: str,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "AbstractClerkUser":
        """
        Create and save a superuser with the given clerk_id and email.

        Args:
            clerk_id: The Clerk user ID.
            email: The user's email address.
            password: Optional password.
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

        return self.create_user(clerk_id, email, password, **extra_fields)

    def get_by_clerk_id(self, clerk_id: str) -> "AbstractClerkUser | None":
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

    def get_by_email(self, email: str) -> "AbstractClerkUser | None":
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
