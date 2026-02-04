"""
Django admin configuration for ClerkUser model.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from django_clerk_users.models import ClerkUser


@admin.register(ClerkUser)
class ClerkUserAdmin(UserAdmin):
    list_display = [
        "email",
        "first_name",
        "last_name",
        "clerk_id",
        "is_staff",
        "is_active",
    ]
    list_filter = ["is_staff", "is_active", "created_at"]
    search_fields = ["email", "first_name", "last_name", "clerk_id"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "image_url")}),
        ("Clerk", {"fields": ("clerk_id", "uid")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at", "last_login", "last_logout")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    readonly_fields = [
        "uid",
        "clerk_id",
        "created_at",
        "updated_at",
        "last_login",
        "last_logout",
    ]
