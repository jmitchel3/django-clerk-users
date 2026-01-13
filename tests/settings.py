"""
Django settings for testing django-clerk-users.
"""

SECRET_KEY = "test-secret-key-for-django-clerk-users"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django_clerk_users",
    "django_clerk_users.organizations",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django_clerk_users.middleware.ClerkAuthMiddleware",
    "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
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

# Clerk settings (mock values for testing)
CLERK_SECRET_KEY = "sk_test_mock_secret_key"
CLERK_WEBHOOK_SIGNING_KEY = "whsec_test_mock_signing_key"
CLERK_FRONTEND_HOSTS = ["http://localhost:3000"]

USE_TZ = True
