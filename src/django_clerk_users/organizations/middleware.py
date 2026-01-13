"""
Organization middleware for django-clerk-users.

This middleware resolves Clerk organization IDs to Organization model instances.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from django_clerk_users.caching import (
    get_cached_organization,
    set_cached_organization,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from django_clerk_users.organizations.models import Organization

logger = logging.getLogger(__name__)


class ClerkOrganizationMiddleware:
    """
    Middleware that resolves organization context.

    This middleware runs after ClerkAuthMiddleware and resolves the
    organization ID (from request.org) to an Organization model instance.

    After processing, the middleware sets:
    - request.organization: The Organization model instance (or None)

    The organization ID can come from:
    1. request.org (set by ClerkAuthMiddleware from JWT payload)
    2. X-Organization-Id header (for explicit org switching)
    """

    def __init__(self, get_response: Callable[["HttpRequest"], "HttpResponse"]):
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        # Process organization before the view
        self.process_request(request)

        # Call the next middleware/view
        response = self.get_response(request)

        return response

    def process_request(self, request: "HttpRequest") -> None:
        """
        Resolve the organization context.

        Sets request.organization to the Organization model instance
        if an organization ID is present.
        """
        request.organization = None  # type: ignore

        # Get organization ID from request
        # Priority: request.org (from JWT) > X-Organization-Id header
        org_id = getattr(request, "org", None)
        if not org_id:
            org_id = request.headers.get("X-Organization-Id")

        if not org_id:
            return

        # Resolve to Organization model
        organization = self._get_organization(org_id)
        if organization:
            if not self._is_member(request, organization):
                logger.debug("User is not a member of org %s", org_id)
                return
            request.organization = organization  # type: ignore
            # Update request.org in case it came from header
            request.org = org_id  # type: ignore

    def _is_member(self, request: "HttpRequest", organization: "Organization") -> bool:
        """
        Check whether the current user belongs to the organization.

        Args:
            request: The current HTTP request.
            organization: The organization to check.

        Returns:
            True if the user is authenticated and a member.
        """
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        from django_clerk_users.organizations.models import OrganizationMember

        return OrganizationMember.objects.filter(
            organization=organization,
            user=request.user,
        ).exists()

    def _get_organization(self, clerk_id: str) -> "Organization | None":
        """
        Get an Organization by Clerk ID, using cache.

        Args:
            clerk_id: The Clerk organization ID.

        Returns:
            The Organization instance or None if not found.
        """
        from django_clerk_users.organizations.models import Organization

        # Check cache first
        cached = get_cached_organization(clerk_id)
        if cached is not None:
            if cached is False:
                return None  # Cached as "not found"
            return cached

        # Query database
        try:
            organization = Organization.objects.get(
                clerk_id=clerk_id,
                is_active=True,
            )
            set_cached_organization(clerk_id, organization)
            return organization
        except Organization.DoesNotExist:
            set_cached_organization(clerk_id, None)
            return None
