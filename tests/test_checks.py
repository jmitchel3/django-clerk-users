"""
Tests for django-clerk-users system checks.
"""

import pytest
from django.test import override_settings
from django.urls import clear_url_caches, path

from django_clerk_users.checks import check_django_clerk_users
from django_clerk_users.webhooks.views import clerk_webhook_view

urlpatterns = [
    path("webhooks/clerk/", clerk_webhook_view, name="clerk_webhook"),
]


@pytest.fixture(autouse=True)
def clear_url_resolver_cache():
    clear_url_caches()
    yield
    clear_url_caches()


def _check_ids():
    return {message.id for message in check_django_clerk_users(None)}


@override_settings(
    MIDDLEWARE=[
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django_clerk_users.middleware.ClerkAuthMiddleware",
    ],
    AUTHENTICATION_BACKENDS=[],
    CLERK_SECRET_KEY="sk_test_mock_secret_key",
    CLERK_FRONTEND_HOSTS=["https://app.example.com"],
    ROOT_URLCONF="",
)
def test_secret_key_warning_when_clerk_auth_middleware_uses_placeholder():
    assert "django_clerk_users.W001" in _check_ids()


@override_settings(
    MIDDLEWARE=[],
    AUTHENTICATION_BACKENDS=[],
    CLERK_SECRET_KEY="sk_test_mock_secret_key",
    CLERK_FRONTEND_HOSTS=[],
    REST_FRAMEWORK={},
    ROOT_URLCONF="",
)
def test_secret_key_warning_not_emitted_when_clerk_authentication_disabled():
    assert "django_clerk_users.W001" not in _check_ids()


@override_settings(
    MIDDLEWARE=[],
    AUTHENTICATION_BACKENDS=[],
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "django_clerk_users.authentication.ClerkAuthentication"
        ]
    },
    CLERK_SECRET_KEY="sk_test_mock_secret_key",
    CLERK_FRONTEND_HOSTS=["https://app.example.com"],
    ROOT_URLCONF="",
)
def test_secret_key_warning_when_drf_clerk_authentication_uses_placeholder():
    assert "django_clerk_users.W001" in _check_ids()


@override_settings(
    MIDDLEWARE=[],
    AUTHENTICATION_BACKENDS=[],
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": ["django.contrib.auth.backends.ModelBackend"]
    },
    CLERK_SECRET_KEY="sk_test_mock_secret_key",
    CLERK_FRONTEND_HOSTS=[],
    ROOT_URLCONF="",
)
def test_secret_key_warning_not_emitted_for_non_clerk_drf_authentication():
    assert "django_clerk_users.W001" not in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django_clerk_users.middleware.ClerkAuthMiddleware",
    ],
    AUTHENTICATION_BACKENDS=[],
    CLERK_FRONTEND_HOSTS=[],
    ROOT_URLCONF="",
)
def test_auth_parties_warning_when_clerk_auth_enabled_without_frontend_hosts():
    assert "django_clerk_users.W003" in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django_clerk_users.middleware.ClerkAuthMiddleware",
    ],
    AUTHENTICATION_BACKENDS=[],
    CLERK_FRONTEND_HOSTS="https://app.example.com, https://admin.example.com",
    ROOT_URLCONF="",
)
def test_auth_parties_warning_not_emitted_for_comma_separated_frontend_hosts():
    assert "django_clerk_users.W003" not in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django_clerk_users.middleware.ClerkAuthMiddleware",
    ],
    AUTHENTICATION_BACKENDS=[],
    CLERK_FRONTEND_HOSTS=[b"\xff"],
    ROOT_URLCONF="",
)
def test_auth_parties_warning_handles_invalid_byte_frontend_hosts():
    assert "django_clerk_users.W003" in _check_ids()


@override_settings(
    ROOT_URLCONF=__name__,
    CLERK_WEBHOOK_SIGNING_KEY="whsec_test_mock_signing_key",
)
def test_webhook_signing_key_warning_when_default_view_uses_placeholder():
    assert "django_clerk_users.W002" in _check_ids()


@override_settings(
    ROOT_URLCONF=__name__,
    CLERK_WEBHOOK_SIGNING_KEY=b" whsec_valid_signing_key ",
)
def test_webhook_signing_key_warning_not_emitted_for_real_bytes_secret():
    assert "django_clerk_users.W002" not in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django_clerk_users.middleware.ClerkAuthMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
    ],
)
def test_clerk_auth_middleware_order_error_when_before_auth_middleware():
    assert "django_clerk_users.E001" in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django_clerk_users.middleware.ClerkAuthMiddleware",
    ],
)
def test_clerk_auth_middleware_order_error_when_auth_middleware_missing():
    assert "django_clerk_users.E001" in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django_clerk_users.middleware.ClerkAuthMiddleware",
        "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
    ],
)
def test_middleware_order_errors_not_emitted_when_configured_correctly():
    check_ids = _check_ids()

    assert "django_clerk_users.E001" not in check_ids
    assert "django_clerk_users.E002" not in check_ids


@override_settings(
    MIDDLEWARE=[
        "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
        "django_clerk_users.middleware.ClerkAuthMiddleware",
    ],
)
def test_organization_middleware_order_error_when_before_clerk_auth_middleware():
    assert "django_clerk_users.E002" in _check_ids()


@override_settings(
    MIDDLEWARE=[
        "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
    ],
)
def test_organization_middleware_order_error_when_clerk_auth_middleware_missing():
    assert "django_clerk_users.E002" in _check_ids()
