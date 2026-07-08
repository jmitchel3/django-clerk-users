"""
Django admin configuration for ClerkUser model.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from django_clerk_users.models import ClerkUser


class ClerkUserAdmin(UserAdmin):
    list_display = [
        "email",
        "username",
        "first_name",
        "last_name",
        "clerk_id",
        "is_staff",
        "is_active",
    ]
    list_filter = ["is_staff", "is_active", "created_at"]
    search_fields = ["email", "username", "first_name", "last_name", "clerk_id"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
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
        "username",
        "created_at",
        "updated_at",
        "last_login",
        "last_logout",
    ]


def _model_is_swapped(model) -> bool:
    return bool(getattr(model._meta, "swapped", None))


def register_clerk_user_admin(site: admin.AdminSite = admin.site) -> bool:
    """
    Register the default ClerkUser admin when the model is active.

    If projects use a custom AUTH_USER_MODEL based on AbstractClerkUser, Django
    marks this concrete model as swapped. Registering a swapped model creates a
    broken admin entry, so custom-user projects should register their own model.
    """
    if _model_is_swapped(ClerkUser) or site.is_registered(ClerkUser):
        return False

    site.register(ClerkUser, ClerkUserAdmin)
    return True


register_clerk_user_admin()
