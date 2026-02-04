"""
Pytest configuration for django-clerk-users tests.

This file loads BEFORE Django settings, allowing .env to override test defaults.
"""

import os
from pathlib import Path

# Load .env file from examples directory if it exists
# This MUST happen before Django settings are loaded
_env_file = Path(__file__).parent.parent / "examples" / "django_react_example" / "backend" / ".env"

if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except ImportError:
        # python-dotenv not installed, skip loading
        pass


def pytest_configure(config):
    """
    Called after command line options have been parsed and before test collection.
    Re-load .env to ensure it's loaded before Django settings.
    """
    if _env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_env_file, override=True)
        except ImportError:
            pass

    # Clear the Clerk client cache so it picks up the new settings
    try:
        from django_clerk_users.client import get_clerk_client
        get_clerk_client.cache_clear()
    except ImportError:
        pass


import pytest


@pytest.fixture(autouse=True, scope="session")
def clear_clerk_client_cache():
    """Clear the Clerk client cache at the start of the test session."""
    try:
        from django_clerk_users.client import get_clerk_client
        get_clerk_client.cache_clear()
    except ImportError:
        pass
    yield
    # Clear again at the end
    try:
        from django_clerk_users.client import get_clerk_client
        get_clerk_client.cache_clear()
    except ImportError:
        pass
