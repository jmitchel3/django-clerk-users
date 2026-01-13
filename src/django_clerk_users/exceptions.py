"""
Custom exceptions for django-clerk-users.
"""


class ClerkError(Exception):
    """Base exception for all Clerk-related errors."""

    pass


class ClerkConfigurationError(ClerkError):
    """Raised when Clerk is not properly configured."""

    pass


class ClerkAuthenticationError(ClerkError):
    """Raised when authentication fails."""

    pass


class ClerkTokenError(ClerkAuthenticationError):
    """Raised when JWT token validation fails."""

    pass


class ClerkWebhookError(ClerkError):
    """Raised when webhook verification fails."""

    pass


class ClerkAPIError(ClerkError):
    """Raised when Clerk API returns an error."""

    pass


class ClerkUserNotFoundError(ClerkError):
    """Raised when a Clerk user cannot be found."""

    pass


class ClerkOrganizationNotFoundError(ClerkError):
    """Raised when a Clerk organization cannot be found."""

    pass
