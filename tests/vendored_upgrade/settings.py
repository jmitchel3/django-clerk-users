"""
Settings for the vendored-migration upgrade scenario (PostgreSQL only).

Environment:
    DJANGO_CLERK_USERS_POSTGRES_URL  postgres://user:pass@host:port/dbname
    LEGACY_CLERK_MIGRATIONS          unset (packaged), "local", or "drift"
"""

import os
from urllib.parse import urlparse

_url = urlparse(os.environ["DJANGO_CLERK_USERS_POSTGRES_URL"])

SECRET_KEY = "vendored-upgrade-scenario"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_clerk_users",
    "tests.vendored_upgrade.legacy_app",
]
AUTH_USER_MODEL = "django_clerk_users.ClerkUser"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _url.path.lstrip("/"),
        "USER": _url.username or "",
        "PASSWORD": _url.password or "",
        "HOST": _url.hostname or "",
        "PORT": str(_url.port or ""),
    }
}
CLERK_SECRET_KEY = "sk_test_vendored_upgrade"
CLERK_WEBHOOK_SIGNING_KEY = "whsec_dmVuZG9yZWQtdXBncmFkZS1zY2VuYXJpbw=="
CLERK_FRONTEND_HOSTS = ["http://localhost:3000"]

_legacy = os.environ.get("LEGACY_CLERK_MIGRATIONS")
if _legacy == "local":
    MIGRATION_MODULES = {
        "django_clerk_users": "tests.vendored_upgrade.clerk_migrations"
    }
elif _legacy == "drift":
    MIGRATION_MODULES = {
        "django_clerk_users": "tests.vendored_upgrade.clerk_migrations_drift"
    }
