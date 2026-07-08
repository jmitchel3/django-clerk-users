"""
User models for django-clerk-users.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from django_clerk_users.managers import ClerkUserManager

logger = logging.getLogger(__name__)


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
        unique=True,
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
    username = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="User's username from Clerk (optional).",
    )
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="User's email address. May be null for username-only Clerk users.",
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
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return self.email or self.username or self.clerk_id or str(self.uid)

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
        """Return the user's short name (Django compatibility)."""
        if self.first_name:
            return self.first_name
        if self.username:
            return self.username
        if self.email:
            return self.email.split("@")[0]
        return str(self.uid)[:8]

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

    def set_password(
        self, raw_password: str | None, sync_to_clerk: bool = True
    ) -> None:
        """
        Set the user's password, optionally syncing to Clerk.

        Args:
            raw_password: The raw password to set.
            sync_to_clerk: If True (default), sync the password to Clerk.
                          Only applies if the user has a clerk_id.

        Example:
            # Sync password to both Django and Clerk (default)
            user.set_password("new_password")
            user.save()

            # Only set Django password (skip Clerk sync)
            user.set_password("new_password", sync_to_clerk=False)
            user.save()
        """
        # Set password in Django
        super().set_password(raw_password)

        # Sync to Clerk if enabled and user has a clerk_id
        from django_clerk_users.settings import _bool_setting

        password_sync_disabled = _bool_setting("CLERK_DISABLE_PASSWORD_SYNC", False)
        password_sync_enabled = not password_sync_disabled and _bool_setting(
            "CLERK_SYNC_PASSWORDS", not password_sync_disabled
        )
        if sync_to_clerk and password_sync_enabled and self.clerk_id and raw_password:
            try:
                from django_clerk_users.client import get_clerk_client
                from django_clerk_users.utils import _clerk_timeout_options

                clerk = get_clerk_client()
                clerk.users.update(
                    user_id=self.clerk_id,
                    password=raw_password,
                    **_clerk_timeout_options(),
                )
                logger.info(f"Synced password to Clerk for user {self.clerk_id}")
            except Exception as e:
                logger.error(
                    f"Failed to sync password to Clerk for user {self.clerk_id}: {e}"
                )


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
