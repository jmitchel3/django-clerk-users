"""
Django admin configuration for organization models.
"""

from django.contrib import admin

from django_clerk_users.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "clerk_id",
        "members_count",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "slug", "clerk_id"]
    readonly_fields = [
        "uid",
        "clerk_id",
        "created_at",
        "updated_at",
        "members_count",
        "pending_invitations_count",
    ]
    ordering = ["-created_at"]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "organization",
        "role",
        "joined_at",
    ]
    list_filter = ["role", "joined_at"]
    search_fields = [
        "user__email",
        "organization__name",
        "clerk_membership_id",
    ]
    readonly_fields = [
        "clerk_membership_id",
        "joined_at",
        "updated_at",
    ]
    raw_id_fields = ["user", "organization"]
    ordering = ["-joined_at"]


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = [
        "email_address",
        "organization",
        "role",
        "status",
        "created_at",
    ]
    list_filter = ["status", "role", "created_at"]
    search_fields = [
        "email_address",
        "organization__name",
        "clerk_invitation_id",
    ]
    readonly_fields = [
        "clerk_invitation_id",
        "created_at",
        "updated_at",
    ]
    raw_id_fields = ["organization", "inviter"]
    ordering = ["-created_at"]
