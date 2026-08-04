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


def test_configured_secret_key_satisfies_authentication_check(monkeypatch):
    from django_clerk_users import checks

    monkeypatch.setattr(checks, "_clerk_authentication_enabled", lambda: True)
    monkeypatch.setattr(
        checks, "get_configured_clerk_secret_key", lambda: "sk_test_real"
    )

    assert checks._check_secret_key() == []


@override_settings(REST_FRAMEWORK=[])
def test_non_mapping_drf_settings_disable_clerk_authentication():
    from django_clerk_users import checks

    assert checks._drf_clerk_authentication_enabled() is False


def test_configured_class_paths_normalize_strings_classes_and_invalid_values():
    from django_clerk_users import checks

    class AuthenticationClass:
        pass

    assert list(checks._configured_class_paths("package.Authentication")) == [
        "package.Authentication"
    ]
    assert list(checks._configured_class_paths(123)) == []
    assert list(checks._configured_class_paths([AuthenticationClass, object()])) == [
        f"{AuthenticationClass.__module__}.{AuthenticationClass.__name__}"
    ]


@override_settings(CLERK_AUTH_PARTIES="https://app.example.com")
def test_configured_auth_parties_take_precedence_over_frontend_hosts():
    from django_clerk_users import checks

    assert checks._configured_auth_parties() == ["https://app.example.com"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        (b" first, second ", ["first", "second"]),
        (b"\xff", []),
        (object(), []),
        ([None, b"\xff", " valid "], ["valid"]),
        (["", "valid"], ["valid"]),
    ],
)
def test_string_list_handles_configuration_edge_cases(value, expected):
    from django_clerk_users import checks

    assert checks._string_list(value) == expected


def test_webhook_urlconf_lookup_failure_is_safe(monkeypatch):
    from django_clerk_users import checks

    def broken_resolver():
        raise RuntimeError("URLconf unavailable")

    monkeypatch.setattr(checks, "get_resolver", broken_resolver)

    assert checks._urlconf_uses_default_clerk_webhook_view() is False


def test_url_pattern_iterator_descends_and_skips_broken_resolvers(monkeypatch):
    from django_clerk_users import checks

    class FakePattern:
        pass

    class FakeResolver:
        def __init__(self, patterns=None, *, broken=False):
            self.patterns = patterns
            self.broken = broken

        @property
        def url_patterns(self):
            if self.broken:
                raise RuntimeError("lazy URLconf failed")
            return self.patterns

    monkeypatch.setattr(checks, "URLPattern", FakePattern)
    monkeypatch.setattr(checks, "URLResolver", FakeResolver)
    leaf = FakePattern()

    assert list(
        checks._iter_url_patterns(
            [object(), FakeResolver([leaf]), FakeResolver(broken=True)]
        )
    ) == [leaf]
    assert list(checks._iter_url_patterns([])) == []


def test_pattern_callback_lookup_failure_is_safe(monkeypatch):
    from django_clerk_users import checks

    class BrokenPattern:
        @property
        def callback(self):
            raise RuntimeError("callback unavailable")

    assert checks._pattern_uses_view(BrokenPattern(), object()) is False


def test_same_view_follows_wrappers_and_detects_cycles():
    from django_clerk_users import checks

    def view():
        pass

    def wrapper():
        pass

    wrapper.__wrapped__ = view
    loop = type("Loop", (), {})()
    loop.__wrapped__ = loop

    assert checks._same_view(view, view) is True
    assert checks._same_view(wrapper, view) is True
    assert checks._same_view(loop, view) is False
    assert checks._same_view(None, view) is False
