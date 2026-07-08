"""
Tests for organization resolution middleware.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from django_clerk_users.organizations.middleware import ClerkOrganizationMiddleware
from django_clerk_users.organizations.models import Organization, OrganizationMember


@pytest.fixture
def request_factory():
    """Create a request factory."""
    return RequestFactory()


@pytest.fixture
def user(db):
    """Create a Clerk-linked user."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_org_middleware",
        email="org-middleware@example.com",
    )


@pytest.fixture
def organization(db):
    """Create an active organization."""
    return Organization.objects.create(
        clerk_id="org_middleware",
        name="Middleware Org",
        slug="middleware-org",
    )


@pytest.fixture
def middleware():
    """Create middleware instance."""
    return ClerkOrganizationMiddleware(lambda request: HttpResponse("OK"))


def test_no_organization_id_leaves_request_without_organization(
    middleware,
    request_factory,
    user,
):
    """Test requests without org context stay unscoped."""
    request = request_factory.get("/")
    request.user = user

    middleware.process_request(request)

    assert request.organization is None


def test_header_organization_sets_context_for_member(
    middleware,
    request_factory,
    user,
    organization,
):
    """Test X-Organization-Id can select an org the user belongs to."""
    OrganizationMember.objects.create(
        clerk_membership_id="mem_header",
        organization=organization,
        user=user,
    )
    request = request_factory.get(
        "/",
        HTTP_X_ORGANIZATION_ID=organization.clerk_id,
    )
    request.user = user

    middleware.process_request(request)

    assert request.organization == organization
    assert request.org == organization.clerk_id


def test_jwt_org_takes_precedence_over_header(
    middleware,
    request_factory,
    user,
    organization,
):
    """Test request.org from Clerk auth takes precedence over headers."""
    header_org = Organization.objects.create(
        clerk_id="org_header",
        name="Header Org",
        slug="header-org",
    )
    OrganizationMember.objects.create(
        clerk_membership_id="mem_jwt",
        organization=organization,
        user=user,
    )
    OrganizationMember.objects.create(
        clerk_membership_id="mem_header",
        organization=header_org,
        user=user,
    )
    request = request_factory.get(
        "/",
        HTTP_X_ORGANIZATION_ID=header_org.clerk_id,
    )
    request.user = user
    request.org = organization.clerk_id

    middleware.process_request(request)

    assert request.organization == organization
    assert request.org == organization.clerk_id


def test_non_member_cannot_select_organization(
    middleware,
    request_factory,
    user,
    organization,
):
    """Test org context is not set when the user is not a member."""
    request = request_factory.get(
        "/",
        HTTP_X_ORGANIZATION_ID=organization.clerk_id,
    )
    request.user = user

    middleware.process_request(request)

    assert request.organization is None


def test_anonymous_user_cannot_select_organization(
    middleware,
    request_factory,
    organization,
):
    """Test anonymous users cannot select org context."""
    request = request_factory.get(
        "/",
        HTTP_X_ORGANIZATION_ID=organization.clerk_id,
    )
    request.user = AnonymousUser()

    middleware.process_request(request)

    assert request.organization is None


def test_inactive_organization_is_not_resolved(
    middleware,
    request_factory,
    user,
):
    """Test inactive organizations are ignored by the cache helper."""
    inactive = Organization.objects.create(
        clerk_id="org_inactive",
        name="Inactive Org",
        slug="inactive-org",
        is_active=False,
    )
    OrganizationMember.objects.create(
        clerk_membership_id="mem_inactive",
        organization=inactive,
        user=user,
    )
    request = request_factory.get(
        "/",
        HTTP_X_ORGANIZATION_ID=inactive.clerk_id,
    )
    request.user = user

    middleware.process_request(request)

    assert request.organization is None


def test_get_organization_delegates_to_cache_helper(middleware, organization):
    """Test _get_organization uses the shared cache lookup path."""
    with patch(
        "django_clerk_users.organizations.middleware.get_cached_organization",
        return_value=organization,
    ) as get_cached_organization:
        result = middleware._get_organization(organization.clerk_id)

    assert result == organization
    get_cached_organization.assert_called_once_with(organization.clerk_id)


def test_call_processes_request_and_returns_response(
    middleware,
    request_factory,
    user,
    organization,
):
    """Test middleware __call__ resolves org context before response."""
    OrganizationMember.objects.create(
        clerk_membership_id="mem_call",
        organization=organization,
        user=user,
    )
    request = request_factory.get(
        "/",
        HTTP_X_ORGANIZATION_ID=organization.clerk_id,
    )
    request.user = user

    response = middleware(request)

    assert response.status_code == 200
    assert response.content == b"OK"
    assert request.organization == organization
