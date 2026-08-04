"""
Clerk API client singleton.

Which implementation is returned depends on ``CLERK_CLIENT_BACKEND``; see
:func:`get_clerk_client`.
"""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from django_clerk_users.exceptions import ClerkConfigurationError

CLERK_NO_KEY_SENTINELS = {
    "abc123",
    "sk_test_mock_secret_key",
    "sk_live_replace_me",
}


def _normalize_secret_key(secret_key) -> str | None:
    if secret_key is None:
        return None
    if isinstance(secret_key, bytes):
        try:
            secret_key = secret_key.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(secret_key, str):
        return None

    secret_key = secret_key.strip()
    if (
        not secret_key
        or not secret_key.startswith("sk_")
        or secret_key in CLERK_NO_KEY_SENTINELS
    ):
        return None
    return secret_key


def get_configured_clerk_secret_key() -> str | None:
    secret_key = getattr(settings, "CLERK_SECRET_KEY", None)
    return _normalize_secret_key(secret_key)


def _get_configured_secret_key() -> str | None:
    return get_configured_clerk_secret_key()


CLERK_CLIENT_BACKEND_THIN = "thin"
CLERK_CLIENT_BACKEND_SDK = "sdk"
CLERK_CLIENT_BACKENDS = (CLERK_CLIENT_BACKEND_THIN, CLERK_CLIENT_BACKEND_SDK)
DEFAULT_CLERK_CLIENT_BACKEND = CLERK_CLIENT_BACKEND_THIN


def get_clerk_client_backend() -> str:
    """Return the configured client backend, defaulting to the thin client.

    Selection is by explicit setting only, never by what happens to be
    importable. ``get_clerk_client`` is public API, and switching
    implementations based on installed packages would make response models,
    error types, retries, and available methods depend on the environment. It
    would also silently reinstate the ``cryptography`` ceiling for anyone who
    picked up ``clerk-backend-api`` as a transitive dependency.
    """
    backend = getattr(settings, "CLERK_CLIENT_BACKEND", DEFAULT_CLERK_CLIENT_BACKEND)
    if isinstance(backend, bytes):
        backend = backend.decode("utf-8", "replace")
    backend = str(backend or DEFAULT_CLERK_CLIENT_BACKEND).strip().lower()

    if backend not in CLERK_CLIENT_BACKENDS:
        raise ClerkConfigurationError(
            f"CLERK_CLIENT_BACKEND must be one of "
            f"{', '.join(sorted(CLERK_CLIENT_BACKENDS))}; got {backend!r}."
        )
    return backend


def _require_secret_key() -> str:
    # Read directly from Django settings to get the most current value.
    clerk_secret_key = _get_configured_secret_key()
    if not clerk_secret_key:
        raise ClerkConfigurationError(
            "CLERK_SECRET_KEY is not set to a real Clerk secret key. "
            "Please configure it in your Django settings."
        )
    return clerk_secret_key


@lru_cache(maxsize=1)
def get_clerk_client():
    """
    Get the Clerk API client instance.

    Returns a cached singleton. Which implementation you get is determined by
    ``CLERK_CLIENT_BACKEND``:

    - ``"thin"`` (default): this package's own REST client. No
      ``clerk-backend-api`` install required, and no ``cryptography`` ceiling.
    - ``"sdk"``: the official ``clerk-backend-api`` client. Requires
      ``pip install django-clerk-users[sdk]``, and reintroduces that SDK's
      ``cryptography<49`` pin.

    Raises:
        ClerkConfigurationError: If CLERK_SECRET_KEY is not set, the backend
            name is unrecognized, or the SDK backend is selected without
            ``clerk-backend-api`` installed.
    """
    backend = get_clerk_client_backend()
    clerk_secret_key = _require_secret_key()

    if backend == CLERK_CLIENT_BACKEND_SDK:
        try:
            from clerk_backend_api import Clerk as ClerkSDK
        except ImportError as exc:
            raise ClerkConfigurationError(
                'CLERK_CLIENT_BACKEND is "sdk" but clerk-backend-api is not '
                "installed. Install it with: "
                "pip install django-clerk-users[sdk], or remove the setting to "
                "use the built-in thin client."
            ) from exc
        return ClerkSDK(bearer_auth=clerk_secret_key)

    from django_clerk_users.clerk_api import ClerkClient

    return ClerkClient(clerk_secret_key)


def get_clerk_sdk():
    """Alias for get_clerk_client() for compatibility."""
    return get_clerk_client()
