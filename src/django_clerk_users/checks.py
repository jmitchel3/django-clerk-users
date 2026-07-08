"""
Django system checks for django-clerk-users configuration.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.urls import URLPattern, URLResolver, get_resolver

from django_clerk_users.client import get_configured_clerk_secret_key
from django_clerk_users.webhooks.security import _get_webhook_signing_key

AUTHENTICATION_MIDDLEWARE = "django.contrib.auth.middleware.AuthenticationMiddleware"
CLERK_AUTH_MIDDLEWARE = "django_clerk_users.middleware.ClerkAuthMiddleware"
CLERK_BACKEND = "django_clerk_users.authentication.ClerkBackend"
CLERK_DRF_AUTHENTICATION_CLASSES = {
    "django_clerk_users.authentication.ClerkAuthentication",
    "django_clerk_users.authentication.ClerkSessionAuthentication",
    "django_clerk_users.authentication.drf.ClerkAuthentication",
    "django_clerk_users.authentication.drf.ClerkSessionAuthentication",
}
CLERK_ORGANIZATION_MIDDLEWARE = (
    "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware"
)


@register(Tags.security)
def check_django_clerk_users(app_configs: Any, **kwargs: Any) -> list[Warning | Error]:
    """Validate high-impact django-clerk-users production settings."""
    return [
        *_check_secret_key(),
        *_check_auth_parties(),
        *_check_webhook_signing_key(),
        *_check_middleware_order(),
    ]


def _check_secret_key() -> list[Warning]:
    if not _clerk_authentication_enabled():
        return []

    if get_configured_clerk_secret_key():
        return []

    return [
        Warning(
            "CLERK_SECRET_KEY is missing or set to a documented placeholder while "
            "Clerk authentication is enabled.",
            hint=(
                "Set CLERK_SECRET_KEY to a real Clerk secret key, or remove "
                "django_clerk_users authentication middleware/backend/DRF classes "
                "from this environment."
            ),
            id="django_clerk_users.W001",
        )
    ]


def _check_webhook_signing_key() -> list[Warning]:
    if _get_webhook_signing_key(None, "CLERK_WEBHOOK_SIGNING_KEY"):
        return []

    if not _urlconf_uses_default_clerk_webhook_view():
        return []

    return [
        Warning(
            "CLERK_WEBHOOK_SIGNING_KEY is missing or set to a documented placeholder "
            "while the default Clerk webhook view is in the URLconf.",
            hint=(
                "Set CLERK_WEBHOOK_SIGNING_KEY to the Svix signing secret for your "
                "Clerk webhook endpoint."
            ),
            id="django_clerk_users.W002",
        )
    ]


def _check_auth_parties() -> list[Warning]:
    if not _clerk_authentication_enabled():
        return []

    if _configured_auth_parties():
        return []

    return [
        Warning(
            "CLERK_FRONTEND_HOSTS/CLERK_AUTH_PARTIES is empty while Clerk "
            "authentication is enabled.",
            hint=(
                "Set CLERK_FRONTEND_HOSTS or CLERK_AUTH_PARTIES to the allowed "
                "frontend origin(s) that can issue Clerk session tokens."
            ),
            id="django_clerk_users.W003",
        )
    ]


def _check_middleware_order() -> list[Error]:
    errors: list[Error] = []
    auth_index = _middleware_index(AUTHENTICATION_MIDDLEWARE)
    clerk_index = _middleware_index(CLERK_AUTH_MIDDLEWARE)
    organization_index = _middleware_index(CLERK_ORGANIZATION_MIDDLEWARE)

    if clerk_index is not None:
        if auth_index is None:
            errors.append(
                Error(
                    "ClerkAuthMiddleware requires Django's AuthenticationMiddleware.",
                    hint=(
                        "Add django.contrib.auth.middleware.AuthenticationMiddleware "
                        "before django_clerk_users.middleware.ClerkAuthMiddleware."
                    ),
                    id="django_clerk_users.E001",
                )
            )
        elif clerk_index <= auth_index:
            errors.append(
                Error(
                    "ClerkAuthMiddleware must be listed after Django's "
                    "AuthenticationMiddleware.",
                    hint=(
                        "Move django_clerk_users.middleware.ClerkAuthMiddleware below "
                        "django.contrib.auth.middleware.AuthenticationMiddleware in "
                        "MIDDLEWARE."
                    ),
                    id="django_clerk_users.E001",
                )
            )

    if organization_index is not None:
        if clerk_index is None:
            errors.append(
                Error(
                    "ClerkOrganizationMiddleware requires ClerkAuthMiddleware.",
                    hint=(
                        "Add django_clerk_users.middleware.ClerkAuthMiddleware before "
                        "django_clerk_users.organizations.middleware."
                        "ClerkOrganizationMiddleware."
                    ),
                    id="django_clerk_users.E002",
                )
            )
        elif organization_index <= clerk_index:
            errors.append(
                Error(
                    "ClerkOrganizationMiddleware must be listed after "
                    "ClerkAuthMiddleware.",
                    hint=(
                        "Move django_clerk_users.organizations.middleware."
                        "ClerkOrganizationMiddleware below "
                        "django_clerk_users.middleware.ClerkAuthMiddleware in "
                        "MIDDLEWARE."
                    ),
                    id="django_clerk_users.E002",
                )
            )

    return errors


def _clerk_authentication_enabled() -> bool:
    has_auth_middleware = _middleware_index(CLERK_AUTH_MIDDLEWARE) is not None
    has_clerk_backend = CLERK_BACKEND in getattr(
        settings, "AUTHENTICATION_BACKENDS", []
    )
    has_drf_auth = _drf_clerk_authentication_enabled()
    return has_auth_middleware or has_clerk_backend or has_drf_auth


def _drf_clerk_authentication_enabled() -> bool:
    rest_framework_settings = getattr(settings, "REST_FRAMEWORK", {})
    if not isinstance(rest_framework_settings, Mapping):
        return False

    auth_classes = rest_framework_settings.get("DEFAULT_AUTHENTICATION_CLASSES", [])
    return any(
        path in CLERK_DRF_AUTHENTICATION_CLASSES
        for path in _configured_class_paths(auth_classes)
    )


def _configured_class_paths(values: Any) -> Iterable[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return

    for value in values:
        if isinstance(value, str):
            yield value
            continue

        module = getattr(value, "__module__", "")
        name = getattr(value, "__name__", "")
        if module and name:
            yield f"{module}.{name}"


def _middleware_index(middleware_path: str) -> int | None:
    try:
        return list(getattr(settings, "MIDDLEWARE", [])).index(middleware_path)
    except ValueError:
        return None


def _configured_auth_parties() -> list[str]:
    raw_value = getattr(settings, "CLERK_AUTH_PARTIES", None)
    if raw_value is None:
        raw_value = getattr(settings, "CLERK_FRONTEND_HOSTS", [])
    return _string_list(raw_value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return []
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, Iterable):
        raw_values = value
    else:
        return []

    values = []
    for item in raw_values:
        if item is None:
            continue
        if isinstance(item, bytes):
            try:
                item = item.decode("utf-8")
            except UnicodeDecodeError:
                continue
        item = str(item).strip()
        if item:
            values.append(item)
    return values


def _urlconf_uses_default_clerk_webhook_view() -> bool:
    try:
        from django_clerk_users.webhooks.views import clerk_webhook_view

        resolver = get_resolver()
        url_patterns = resolver.url_patterns
    except Exception:
        return False

    return any(
        _pattern_uses_view(pattern, clerk_webhook_view)
        for pattern in _iter_url_patterns(url_patterns)
    )


def _iter_url_patterns(patterns: Iterable[Any]) -> Iterable[URLPattern]:
    for pattern in patterns:
        if isinstance(pattern, URLPattern):
            yield pattern
        elif isinstance(pattern, URLResolver):
            try:
                yield from _iter_url_patterns(pattern.url_patterns)
            except Exception:
                continue


def _pattern_uses_view(pattern: URLPattern, view_func: Any) -> bool:
    try:
        callback = pattern.callback
    except Exception:
        return False

    return _same_view(callback, view_func)


def _same_view(callback: Any, view_func: Any) -> bool:
    seen: set[int] = set()
    current = callback
    while current is not None:
        if current is view_func:
            return True

        current_id = id(current)
        if current_id in seen:
            return False
        seen.add(current_id)

        current = getattr(current, "__wrapped__", None)
    return False
