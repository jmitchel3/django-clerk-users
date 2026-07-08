"""
Smoke-test the installed wheel without importing from the checkout's src tree.
"""

from __future__ import annotations

import importlib.metadata
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _remove_source_tree_from_path() -> None:
    resolved_src = SRC_ROOT.resolve()
    sys.path[:] = [
        path for path in sys.path if not path or Path(path).resolve() != resolved_src
    ]


def _project_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["version"]


def _verify_installed_distribution() -> str:
    expected_version = _project_version()
    installed_version = importlib.metadata.version("django-clerk-users")
    if installed_version != expected_version:
        raise AssertionError(
            f"Installed version {installed_version} != project version "
            f"{expected_version}"
        )

    import django_clerk_users

    package_file = Path(django_clerk_users.__file__).resolve()
    try:
        package_file.relative_to(SRC_ROOT.resolve())
    except ValueError:
        return installed_version

    raise AssertionError(
        "Installed wheel smoke test imported django_clerk_users from the "
        f"checkout source tree instead of the installed distribution: {package_file}"
    )


def _configure_django() -> None:
    from django.conf import settings

    if settings.configured:
        return

    settings.configure(
        SECRET_KEY="wheel-smoke-test",
        DEBUG=False,
        INSTALLED_APPS=[
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.messages",
            "django.contrib.sessions",
            "django_clerk_users",
            "django_clerk_users.organizations",
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django_clerk_users.middleware.ClerkAuthMiddleware",
            "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
        ],
        TEMPLATES=[
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
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        AUTH_USER_MODEL="django_clerk_users.ClerkUser",
        AUTHENTICATION_BACKENDS=["django_clerk_users.authentication.ClerkBackend"],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        CLERK_SECRET_KEY="abc123",
        CLERK_WEBHOOK_SIGNING_KEY="whsec_test_mock_signing_key",
        CLERK_FRONTEND_HOSTS=["http://localhost:3000"],
        SILENCED_SYSTEM_CHECKS=["django_clerk_users.W001"],
    )


def main() -> int:
    _remove_source_tree_from_path()
    installed_version = _verify_installed_distribution()

    _configure_django()

    import django
    from django.contrib.admin import AdminSite
    from django.core.management import call_command

    django.setup()
    call_command("check", verbosity=0)

    from django_clerk_users.admin import register_clerk_user_admin
    from django_clerk_users.models import ClerkUser
    from django_clerk_users.organizations.admin import register_organization_admins
    from django_clerk_users.organizations.models import Organization
    from django_clerk_users.server_api import create_clerk_user
    from django_clerk_users.webhooks.views import clerk_webhook_view

    site = AdminSite(name="wheel-smoke-test")
    assert register_clerk_user_admin(site) is True
    assert site.is_registered(ClerkUser)
    assert Organization._meta.app_label == "clerk_organizations"
    assert len(register_organization_admins(AdminSite(name="wheel-org-test"))) == 3
    assert create_clerk_user("missing-key@example.com", clerk_client=None) is not None
    assert callable(clerk_webhook_view)

    print(
        f"Installed wheel smoke test passed for django-clerk-users {installed_version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
