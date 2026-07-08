"""
Django settings for testing django-clerk-users.
"""

import os
from pathlib import Path

# Loading ignored demo credentials is opt-in so regular unit tests stay
# deterministic and do not accidentally call live Clerk APIs.
_env_file = (
    Path(__file__).parent.parent
    / "examples"
    / "django_react_example"
    / "backend"
    / ".env"
)
if os.environ.get("DJANGO_CLERK_USERS_LOAD_EXAMPLE_ENV") == "1" and _env_file.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file, override=True)
    except ImportError:
        pass

SECRET_KEY = "test-secret-key-for-django-clerk-users"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django_clerk_users",
    "django_clerk_users.organizations",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django_clerk_users.middleware.ClerkAuthMiddleware",
    "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
]

TEMPLATES = [
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
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Use the ClerkUser model for testing
AUTH_USER_MODEL = "django_clerk_users.ClerkUser"

AUTHENTICATION_BACKENDS = [
    "django_clerk_users.authentication.ClerkBackend",
]

# Clerk settings (use env vars if available, otherwise mock values for unit tests)
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "sk_test_mock_secret_key")
CLERK_WEBHOOK_SIGNING_KEY = os.environ.get(
    "CLERK_WEBHOOK_SIGNING_KEY", "whsec_test_mock_signing_key"
)
CLERK_FRONTEND_HOSTS = ["http://localhost:3000"]

USE_TZ = True
