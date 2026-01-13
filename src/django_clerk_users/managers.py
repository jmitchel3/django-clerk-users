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
        email: str,
        clerk_id: str | None = None,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "AbstractClerkUser":
        """
        Create and save a user with the given email and optional clerk_id.

        Args:
            email: The user's email address (required).
            clerk_id: The Clerk user ID (optional for Django admin users).
            password: Optional password (required for Django admin users).
            **extra_fields: Additional fields for the user model.

        Returns:
            The created user instance.

        Raises:
            ValueError: If email is not provided.
        """
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
        email: str,
        password: str | None = None,
        clerk_id: str | None = None,
        **extra_fields: Any,
    ) -> "AbstractClerkUser":
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
