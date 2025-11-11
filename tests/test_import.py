"""
Basic tests for django-googler package.
"""

import pytest  # noqa: F401


def test_import_django_googler():
    """Test that django_googler can be imported."""
    import django_clerk_users  # noqa: F401


def test_django_setup():
    """Test that Django can be set up with the package installed."""
    import django  # noqa: F401
    from django.conf import settings

    assert settings.configured
    assert "django_clerk_users" in settings.INSTALLED_APPS
