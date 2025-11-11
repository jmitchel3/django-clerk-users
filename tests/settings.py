"""
Django settings for testing django-clerk-users.
"""

SECRET_KEY = "test-secret-key-for-django-clerk-users"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_clerk_users",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True
