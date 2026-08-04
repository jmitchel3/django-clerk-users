"""
Custom exceptions for django-clerk-users.
"""

from collections.abc import Mapping


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
    """Raised when Clerk API returns an error.

    Carries the HTTP ``status_code`` and the parsed error body so callers can
    branch on Clerk's structured error codes without depending on SDK types::

        for error in exc.data.errors:
            error.code                  # e.g. "form_identifier_exists"
            error.meta.param_names      # e.g. ["email_address"]

    ``data`` is always present and mapping-like, so ``exc.data.errors`` is a
    list even when the response body was empty or unparseable. Constructing
    with only a message stays supported for callers that wrap other failures.
    """

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        data=None,
        response=None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.data = _coerce_error_data(data)

    @property
    def errors(self) -> list:
        """Shortcut for ``self.data.errors``, always a list."""
        return list(self.data.get("errors") or [])


def _coerce_error_data(data):
    """Normalize an error body into a mapping that always exposes ``errors``."""
    from django_clerk_users.clerk_api.objects import ClerkObject

    if data is None:
        return ClerkObject({"errors": []})
    if isinstance(data, ClerkObject):
        if "errors" in data:
            return data
        return ClerkObject({**data.to_dict(), "errors": []})
    if isinstance(data, Mapping):
        payload = dict(data)
        payload.setdefault("errors", [])
        return ClerkObject(payload)
    # A non-mapping body (an HTML error page, a bare string) still needs to
    # satisfy ``.errors`` so duplicate detection can iterate it safely.
    return ClerkObject({"errors": [], "raw": data})


class ClerkUserNotFoundError(ClerkError):
    """Raised when a Clerk user cannot be found."""

    pass


class ClerkUserMergeConflictError(ClerkError):
    """Raised when a Clerk identity cannot be safely moved between users."""

    pass


class ClerkOrganizationNotFoundError(ClerkError):
    """Raised when a Clerk organization cannot be found."""

    pass
