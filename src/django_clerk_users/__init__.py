"""
django-clerk-users: Integrate Clerk authentication with Django.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-clerk-users")
except PackageNotFoundError:
    __version__ = "unknown"

# Re-export default app config


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

    # Server-side Clerk API helpers
    if name in (
        "build_clerk_sign_in_url",
        "create_clerk_sign_in_link",
        "create_clerk_sign_in_token",
        "create_clerk_user",
        "derive_clerk_username",
        "get_clerk_user_by_email",
        "provision_clerk_user_access_link",
        "revoke_clerk_invitation",
        "revoke_clerk_user_sessions",
        "send_clerk_invitation",
        "set_clerk_user_email",
        "update_clerk_user",
        "update_clerk_user_public_metadata",
    ):
        from django_clerk_users import server_api

        return getattr(server_api, name)

    # Authentication
    if name in (
        "ClerkBackend",
        "ClerkAuthentication",
        "ClerkSessionAuthentication",
        "CsrfExemptSessionAuthentication",
    ):
        from django_clerk_users import authentication

        return getattr(authentication, name)

    # Exceptions
    if name in (
        "ClerkError",
        "ClerkConfigurationError",
        "ClerkAuthenticationError",
        "ClerkTokenError",
        "ClerkWebhookError",
        "ClerkAPIError",
        "ClerkUserNotFoundError",
        "ClerkUserMergeConflictError",
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
        "make_test_username",
        "TEST_OTP_CODE",
    ):
        from django_clerk_users import testing

        return getattr(testing, name)

    # Username generation utilities (for Celery/django-qstash)
    if name in (
        "absorb_clerk_user_duplicate",
        "generate_username_for_user",
        "generate_usernames_for_users_without",
    ):
        from django_clerk_users import utils

        return getattr(utils, name)

    raise AttributeError(f"Module 'django_clerk_users' has no attribute '{name}'")


__all__ = [
    "__version__",
    # Models
    "AbstractClerkUser",
    "ClerkUser",
    "ClerkUserManager",
    # Client
    "get_clerk_client",
    # Server-side Clerk API helpers
    "build_clerk_sign_in_url",
    "create_clerk_sign_in_link",
    "create_clerk_sign_in_token",
    "create_clerk_user",
    "derive_clerk_username",
    "get_clerk_user_by_email",
    "provision_clerk_user_access_link",
    "revoke_clerk_invitation",
    "revoke_clerk_user_sessions",
    "send_clerk_invitation",
    "set_clerk_user_email",
    "update_clerk_user",
    "update_clerk_user_public_metadata",
    # Authentication
    "ClerkBackend",
    "ClerkAuthentication",
    "ClerkSessionAuthentication",
    "CsrfExemptSessionAuthentication",
    # Exceptions
    "ClerkError",
    "ClerkConfigurationError",
    "ClerkAuthenticationError",
    "ClerkTokenError",
    "ClerkWebhookError",
    "ClerkAPIError",
    "ClerkUserNotFoundError",
    "ClerkUserMergeConflictError",
    "ClerkOrganizationNotFoundError",
    # Testing utilities
    "ClerkTestClient",
    "ClerkTestMixin",
    "TestUserData",
    "make_test_email",
    "make_test_phone",
    "make_test_username",
    "TEST_OTP_CODE",
    # Username generation utilities
    "absorb_clerk_user_duplicate",
    "generate_username_for_user",
    "generate_usernames_for_users_without",
]
