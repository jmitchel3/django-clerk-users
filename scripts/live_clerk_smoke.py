"""
Run read-only live Clerk validation for release readiness.

This script intentionally performs no writes against Clerk. It verifies that the
package can configure Django, authenticate to the Clerk Backend API, perform a
small read-only user-list call, and verify a Clerk/Svix webhook signature using
the configured signing secret.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from svix.webhooks import Webhook

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CLERK_SECRET_KEY_PLACEHOLDERS = {
    "abc123",
    "sk_test_mock_secret_key",
    "sk_live_replace_me",
}
CLERK_WEBHOOK_SIGNING_KEY_PLACEHOLDERS = {
    "whsec_test_mock_signing_key",
    "whsec_replace_me",
}


def _remove_source_tree_from_path() -> None:
    resolved_src = SRC_ROOT.resolve()
    sys.path[:] = [
        path for path in sys.path if not path or Path(path).resolve() != resolved_src
    ]


def _project_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["version"]


def _verify_installed_distribution() -> None:
    expected_version = _project_version()
    installed_version = importlib.metadata.version("django-clerk-users")
    if installed_version != expected_version:
        raise AssertionError(
            f"Installed django-clerk-users version {installed_version} does not "
            f"match project version {expected_version}."
        )

    import django_clerk_users

    package_file = Path(django_clerk_users.__file__).resolve()
    try:
        package_file.relative_to(SRC_ROOT.resolve())
    except ValueError:
        return

    raise AssertionError(
        "Live Clerk smoke check imported django_clerk_users from the checkout "
        f"source tree instead of the installed distribution: {package_file}"
    )


def _split_hosts(raw_hosts: str) -> list[str]:
    return [host.strip() for host in raw_hosts.split(",") if host.strip()]


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _normalized_secret(secret: str | None) -> str:
    if not secret:
        return ""
    return secret.strip()


def _is_real_secret(secret: str | None, *, prefix: str, placeholders: set[str]) -> bool:
    secret = _normalized_secret(secret)
    return bool(secret) and secret.startswith(prefix) and secret not in placeholders


def _env_secret(name: str) -> str:
    return _normalized_secret(os.environ.get(name))


def _missing_reasons() -> list[str]:
    reasons = []
    if not _is_real_secret(
        os.environ.get("CLERK_SECRET_KEY"),
        prefix="sk_",
        placeholders=CLERK_SECRET_KEY_PLACEHOLDERS,
    ):
        reasons.append("CLERK_SECRET_KEY must be a real Clerk secret key")

    if not _is_real_secret(
        os.environ.get("CLERK_WEBHOOK_SIGNING_KEY"),
        prefix="whsec_",
        placeholders=CLERK_WEBHOOK_SIGNING_KEY_PLACEHOLDERS,
    ):
        reasons.append("CLERK_WEBHOOK_SIGNING_KEY must be a real Svix signing secret")

    return reasons


def _live_credentials_are_unset() -> bool:
    return not _env_secret("CLERK_SECRET_KEY") and not _env_secret(
        "CLERK_WEBHOOK_SIGNING_KEY"
    )


def _django_settings_kwargs() -> dict[str, Any]:
    return {
        "SECRET_KEY": "live-clerk-smoke",
        "DEBUG": False,
        "INSTALLED_APPS": [
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.messages",
            "django.contrib.sessions",
            "django_clerk_users",
            "django_clerk_users.organizations",
        ],
        "MIDDLEWARE": [
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django_clerk_users.middleware.ClerkAuthMiddleware",
            "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
        ],
        "TEMPLATES": [
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                    ],
                },
            }
        ],
        "DATABASES": {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        "AUTH_USER_MODEL": "django_clerk_users.ClerkUser",
        "AUTHENTICATION_BACKENDS": ["django_clerk_users.authentication.ClerkBackend"],
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
        "USE_TZ": True,
        "CLERK_SECRET_KEY": _env_secret("CLERK_SECRET_KEY"),
        "CLERK_WEBHOOK_SIGNING_KEY": _env_secret("CLERK_WEBHOOK_SIGNING_KEY"),
        "CLERK_FRONTEND_HOSTS": _split_hosts(
            os.environ.get("CLERK_FRONTEND_HOSTS", "http://localhost:3000")
        ),
        "CLERK_API_TIMEOUT_MS": _env_int("CLERK_API_TIMEOUT_MS", 10000),
    }


def _configure_django() -> None:
    from django.conf import settings

    if settings.configured:
        return

    settings.configure(**_django_settings_kwargs())


def _list_users(timeout_ms: int) -> int:
    from django_clerk_users.client import get_clerk_client

    get_clerk_client.cache_clear()
    clerk = get_clerk_client()
    response = clerk.users.list(
        request={"limit": 1, "offset": 0}, timeout_ms=timeout_ms
    )
    users = response.data if hasattr(response, "data") else response
    return len(list(users or []))


def _optional_lookup(email: str, timeout_ms: int) -> dict[str, Any] | None:
    from django_clerk_users.server_api import get_clerk_user_by_email

    return get_clerk_user_by_email(email, timeout_ms=timeout_ms)


def _verify_signed_webhook() -> None:
    from django.test import RequestFactory

    from django_clerk_users.webhooks.security import verify_clerk_webhook

    payload = {
        "id": "evt_live_smoke",
        "type": "user.updated",
        "data": {"id": "user_live_smoke"},
    }
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = datetime.now(timezone.utc)
    message_id = "msg_live_smoke"

    webhook = Webhook(_env_secret("CLERK_WEBHOOK_SIGNING_KEY"))
    signature = webhook.sign(message_id, timestamp, body)

    request = RequestFactory().post(
        "/webhooks/clerk/",
        data=body,
        content_type="application/json",
        HTTP_SVIX_ID=message_id,
        HTTP_SVIX_TIMESTAMP=str(int(timestamp.timestamp())),
        HTTP_SVIX_SIGNATURE=signature,
    )

    verified = verify_clerk_webhook(request)
    if verified != payload:
        raise AssertionError(
            f"Webhook verifier returned unexpected payload: {verified}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-missing-env",
        action="store_true",
        help="Exit successfully when live Clerk credentials are not configured.",
    )
    args = parser.parse_args()

    missing_reasons = _missing_reasons()
    if missing_reasons:
        message = "Live Clerk smoke check not configured:\n  - " + "\n  - ".join(
            missing_reasons
        )
        if args.allow_missing_env and _live_credentials_are_unset():
            print(message)
            return 0
        raise SystemExit(message)

    _remove_source_tree_from_path()
    _verify_installed_distribution()

    timeout_ms = _env_int("CLERK_API_TIMEOUT_MS", 10000)

    _configure_django()

    import django
    from django.core.management import call_command

    django.setup()
    call_command("check", verbosity=0)

    user_count = _list_users(timeout_ms)
    print(f"Clerk API users.list succeeded; received {user_count} user(s).")

    lookup_email = os.environ.get("CLERK_LIVE_SMOKE_LOOKUP_EMAIL")
    if lookup_email:
        lookup_result = _optional_lookup(lookup_email, timeout_ms)
        if not lookup_result:
            raise AssertionError(
                "CLERK_LIVE_SMOKE_LOOKUP_EMAIL was set, but no Clerk user was found: "
                f"{lookup_email}"
            )
        print(f"Clerk email lookup succeeded for {lookup_email}.")

    _verify_signed_webhook()
    print("Webhook signature verification succeeded.")
    print("Live Clerk smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
