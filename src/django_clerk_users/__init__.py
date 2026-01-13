"""
django-clerk-users: Integrate Clerk authentication with Django.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-clerk-users")
except PackageNotFoundError:
    __version__ = "unknown"

# Re-export default app config
default_app_config = "django_clerk_users.apps.DjangoClerkUsersConfig"


def __getattr__(name: str):
    """Lazy import to avoid loading Django models before apps are ready."""
    # Models
    if name == "AbstractClerkUser":
        from django_clerk_users.models import AbstractClerkUser

        return AbstractClerkUser
    if name == "ClerkUser":
        from django_clerk_users.models import ClerkUser

        return ClerkUser
    if name == "ClerkUserManager":
        from django_clerk_users.models import ClerkUserManager

        return ClerkUserManager

    # Client
    if name == "get_clerk_client":
        from django_clerk_users.client import get_clerk_client

        return get_clerk_client

    # Exceptions
    if name in (
        "ClerkError",
        "ClerkConfigurationError",
        "ClerkAuthenticationError",
        "ClerkTokenError",
        "ClerkWebhookError",
        "ClerkAPIError",
        "ClerkUserNotFoundError",
        "ClerkOrganizationNotFoundError",
    ):
        from django_clerk_users import exceptions

        return getattr(exceptions, name)

    # Testing utilities
    if name in (
        "ClerkTestClient",
        "ClerkTestMixin",
        "TestUserData",
        "make_test_email",
        "make_test_phone",
        "TEST_OTP_CODE",
    ):
        from django_clerk_users import testing

        return getattr(testing, name)

    raise AttributeError(f"Module 'django_clerk_users' has no attribute '{name}'")


__all__ = [
    "__version__",
    # Models
    "AbstractClerkUser",
    "ClerkUser",
    "ClerkUserManager",
    # Client
    "get_clerk_client",
    # Exceptions
    "ClerkError",
    "ClerkConfigurationError",
    "ClerkAuthenticationError",
    "ClerkTokenError",
    "ClerkWebhookError",
    "ClerkAPIError",
    "ClerkUserNotFoundError",
    "ClerkOrganizationNotFoundError",
    # Testing utilities
    "ClerkTestClient",
    "ClerkTestMixin",
    "TestUserData",
    "make_test_email",
    "make_test_phone",
    "TEST_OTP_CODE",
]
