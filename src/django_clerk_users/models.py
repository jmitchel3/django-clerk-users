"""
User models for django-clerk-users.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from django_clerk_users.managers import ClerkUserManager


class AbstractClerkUser(AbstractBaseUser, PermissionsMixin):
    """
    Abstract base class for Clerk-authenticated users.

    Extend this class to create a custom user model with additional fields
    while maintaining Clerk integration.

    Example:
        class CustomUser(AbstractClerkUser):
            company = models.CharField(max_length=255, blank=True)
            phone = models.CharField(max_length=20, blank=True)

            class Meta(AbstractClerkUser.Meta):
                swappable = "AUTH_USER_MODEL"
    """

    # Public identifier (use this in URLs and APIs instead of pk)
    uid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="Public unique identifier for the user.",
    )

    # Clerk-specific fields
    clerk_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text="Unique identifier from Clerk. Can be null for Django admin users.",
    )

    # Password field for Django admin compatibility
    # Inherited from AbstractBaseUser, but we make it explicit that it's optional
    # for Clerk users (who authenticate via JWT) but required for admin users

    # Standard user fields
    email = models.EmailField(
        unique=True,
        db_index=True,
        help_text="User's email address.",
    )
    first_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="User's first name.",
    )
    last_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="User's last name.",
    )
    image_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL to user's profile image from Clerk.",
    )

    # Status fields
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the user account is active.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Whether the user can access the admin site.",
    )

    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the user was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the user was last updated.",
    )
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last login timestamp (managed by Clerk).",
    )
    last_logout = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last logout timestamp (managed by Clerk).",
    )

    objects = ClerkUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # Changed to empty - clerk_id is optional for admin users

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["clerk_id"]),
            models.Index(fields=["email"]),
            models.Index(fields=["uid"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def public_id(self) -> str:
        """Return the public UUID as a string for API responses."""
        return str(self.uid)

    @property
    def full_name(self) -> str:
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        """Return the user's full name (Django compatibility)."""
        return self.full_name

    def get_short_name(self) -> str:
        """Return the user's first name (Django compatibility)."""
        return self.first_name or self.email.split("@")[0]

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        """
        Return True if the user has the specified permission.

        For Clerk users, permissions are typically managed through
        Clerk's organization roles or custom metadata.
        Superusers have all permissions.
        """
        if self.is_superuser:
            return True
        return super().has_perm(perm, obj)

    def has_module_perms(self, app_label: str) -> bool:
        """
        Return True if the user has any permissions in the given app.

        Superusers have all permissions.
        """
        if self.is_superuser:
            return True
        return super().has_module_perms(app_label)


class ClerkUser(AbstractClerkUser):
    """
    Concrete user model for Clerk authentication.

    Use this model directly by setting AUTH_USER_MODEL = "django_clerk_users.ClerkUser"
    in your Django settings, or extend AbstractClerkUser for custom fields.
    """

    class Meta(AbstractClerkUser.Meta):
        swappable = "AUTH_USER_MODEL"
        verbose_name = "Clerk User"
        verbose_name_plural = "Clerk Users"
