"""
Convenience wrappers for Clerk server-side operations.

These helpers use the official Clerk Backend SDK under the hood, but keep the
calling shape small and Django-friendly for common app workflows: provisioning
passwordless users, minting access links, revoking sessions, and keeping profile
data in sync with Clerk.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings

from django_clerk_users.client import (
    get_clerk_client,
    get_configured_clerk_secret_key,
)
from django_clerk_users.exceptions import ClerkConfigurationError

logger = logging.getLogger(__name__)

CLERK_API_DEFAULT_TIMEOUT_MS = 10_000
DUPLICATE_IDENTIFIER_CODES = {
    "form_identifier_exists",
    "form_identifier_not_unique",
}


def _resolve_clerk_client(clerk_client: Any | None = None) -> Any | None:
    if clerk_client is not None:
        return clerk_client

    if not get_configured_clerk_secret_key():
        return None

    try:
        return get_clerk_client()
    except ClerkConfigurationError:
        return None


def _timeout_options(timeout_ms: int | None) -> dict[str, int]:
    raw_timeout = (
        timeout_ms
        if timeout_ms is not None
        else getattr(settings, "CLERK_API_TIMEOUT_MS", CLERK_API_DEFAULT_TIMEOUT_MS)
    )
    try:
        resolved_timeout = int(raw_timeout)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid CLERK_API_TIMEOUT_MS value %r, using default %s",
            raw_timeout,
            CLERK_API_DEFAULT_TIMEOUT_MS,
        )
        resolved_timeout = CLERK_API_DEFAULT_TIMEOUT_MS

    if resolved_timeout <= 0:
        logger.warning(
            "Non-positive Clerk API timeout %r, using default %s",
            raw_timeout,
            CLERK_API_DEFAULT_TIMEOUT_MS,
        )
        resolved_timeout = CLERK_API_DEFAULT_TIMEOUT_MS

    return {"timeout_ms": resolved_timeout}


def _plain_data(value: Any) -> Any:
    """Convert SDK models to plain Python values without requiring pydantic."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {key: _plain_data(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain_data(item) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=True)

    if hasattr(value, "__dict__"):
        return {
            key: _plain_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }

    return value


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _list_data(response: Any) -> list[Any]:
    data = _get_value(response, "data", response)
    if data is None:
        return []
    return list(data)


def _error_param_names(error: Any) -> set[str]:
    meta = _plain_data(_get_value(error, "meta", {})) or {}
    param_names = meta.get("param_names") or []
    return {str(name) for name in param_names}


def _clerk_errors(exc: Exception) -> list[Any]:
    data = _get_value(exc, "data")
    errors = _get_value(data, "errors", [])
    return list(errors or [])


def _has_duplicate_identifier_error(exc: Exception) -> bool:
    for error in _clerk_errors(exc):
        if _get_value(error, "code") in DUPLICATE_IDENTIFIER_CODES:
            return True
    return False


def _duplicate_error_params(exc: Exception) -> set[str]:
    params: set[str] = set()
    for error in _clerk_errors(exc):
        if _get_value(error, "code") in DUPLICATE_IDENTIFIER_CODES:
            params.update(_error_param_names(error))
    return params


def _log_clerk_error(operation: str, exc: Exception) -> None:
    status_code = _get_value(exc, "status_code")
    if status_code:
        logger.error("Clerk %s failed: status=%s error=%s", operation, status_code, exc)
    else:
        logger.error("Clerk %s failed: %s", operation, exc)


def derive_clerk_username(email: str) -> str:
    """Return a random-suffixed username based on an email local-part."""
    base = re.sub(r"[^a-z0-9_]", "", email.split("@", 1)[0].lower())[:24] or "user"
    return f"{base}_{secrets.token_hex(3)}"


def create_clerk_user(
    email: str,
    *,
    password: str | None = None,
    first_name: str = "",
    last_name: str = "",
    username: str | None = None,
    auto_username: bool = False,
    public_metadata: dict[str, Any] | None = None,
    private_metadata: dict[str, Any] | None = None,
    unsafe_metadata: dict[str, Any] | None = None,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    """
    Create a Clerk user directly from Django.

    When ``password`` is omitted, the user is created passwordless with
    ``skip_password_requirement=True`` so the app can sign them in via a one-time
    sign-in token. If Clerk is not configured, returns ``{"no_key": True}``.
    If the email already exists, returns ``{"already_exists": True, "email": ...}``.
    """
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping Clerk user creation")
        return {"no_key": True}

    create_kwargs: dict[str, Any] = {
        "email_address": [email],
        "first_name": first_name,
        "last_name": last_name,
    }
    if password:
        create_kwargs["password"] = password
        create_kwargs["skip_password_checks"] = True
    else:
        create_kwargs["skip_password_requirement"] = True
    if public_metadata is not None:
        create_kwargs["public_metadata"] = public_metadata
    if private_metadata is not None:
        create_kwargs["private_metadata"] = private_metadata
    if unsafe_metadata is not None:
        create_kwargs["unsafe_metadata"] = unsafe_metadata

    should_derive_username = auto_username and not username
    attempts = 5 if should_derive_username else 1
    for _attempt in range(attempts):
        attempt_kwargs = {**create_kwargs, **_timeout_options(timeout_ms)}
        if should_derive_username:
            attempt_kwargs["username"] = derive_clerk_username(email)
        elif username:
            attempt_kwargs["username"] = username

        try:
            return _plain_data(client.users.create(**attempt_kwargs))
        except Exception as exc:
            if _has_duplicate_identifier_error(exc):
                params = _duplicate_error_params(exc)
                if (
                    should_derive_username
                    and "username" in params
                    and "email_address" not in params
                ):
                    continue
                if "email_address" in params or not params:
                    logger.info("Clerk user already exists: %s", email)
                    return {"already_exists": True, "email": email}

            _log_clerk_error("user creation", exc)
            return None

    logger.error("Clerk user creation exhausted username retries for %s", email)
    return None


def get_clerk_user_by_email(
    email: str,
    *,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    """Look up the first Clerk user matching an email address."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        return None

    try:
        response = client.users.list(
            request={"email_address": [email], "limit": 1},
            **_timeout_options(timeout_ms),
        )
    except Exception as exc:
        _log_clerk_error(f"user lookup for {email}", exc)
        return None

    users = _list_data(response)
    if not users:
        return None
    return _plain_data(users[0])


def get_clerk_user(
    clerk_user_id: str,
    *,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    """Fetch a Clerk user by ID and return plain dict data."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        return None

    try:
        return _plain_data(
            client.users.get(user_id=clerk_user_id, **_timeout_options(timeout_ms))
        )
    except Exception as exc:
        _log_clerk_error(f"user fetch for {clerk_user_id}", exc)
        return None


def update_clerk_user(
    clerk_user_id: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    public_metadata: dict[str, Any] | None = None,
    private_metadata: dict[str, Any] | None = None,
    unsafe_metadata: dict[str, Any] | None = None,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """Patch common Clerk user fields."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping Clerk user update")
        return False

    update_kwargs: dict[str, Any] = {}
    if first_name is not None:
        update_kwargs["first_name"] = first_name
    if last_name is not None:
        update_kwargs["last_name"] = last_name
    if public_metadata is not None:
        update_kwargs["public_metadata"] = public_metadata
    if private_metadata is not None:
        update_kwargs["private_metadata"] = private_metadata
    if unsafe_metadata is not None:
        update_kwargs["unsafe_metadata"] = unsafe_metadata
    if not update_kwargs:
        return True

    try:
        client.users.update(
            user_id=clerk_user_id,
            **update_kwargs,
            **_timeout_options(timeout_ms),
        )
        return True
    except Exception as exc:
        _log_clerk_error(f"user update for {clerk_user_id}", exc)
        return False


def update_clerk_user_public_metadata(
    clerk_user_id: str,
    updates: Mapping[str, Any],
    *,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """Merge keys into a Clerk user's public metadata without clobbering it."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping metadata update")
        return False

    try:
        user = client.users.get(user_id=clerk_user_id, **_timeout_options(timeout_ms))
        current = _plain_data(user).get("public_metadata") or {}
        client.users.update(
            user_id=clerk_user_id,
            public_metadata={**current, **dict(updates)},
            **_timeout_options(timeout_ms),
        )
        return True
    except Exception as exc:
        _log_clerk_error(f"public metadata update for {clerk_user_id}", exc)
        return False


def set_clerk_user_email(
    clerk_user_id: str,
    email: str,
    *,
    verified: bool = True,
    prune_existing: bool = True,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """
    Create a verified primary email in Clerk and optionally remove old emails.

    Use this before changing the local Django email so Clerk login and Django
    profile state cannot drift apart.
    """
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping Clerk email update")
        return False

    try:
        created = client.email_addresses.create(
            request={
                "user_id": clerk_user_id,
                "email_address": email,
                "verified": verified,
                "primary": True,
            },
            **_timeout_options(timeout_ms),
        )
        new_email_id = _get_value(_plain_data(created), "id")

        if prune_existing and new_email_id:
            user = client.users.get(
                user_id=clerk_user_id,
                **_timeout_options(timeout_ms),
            )
            for email_address in _plain_data(user).get("email_addresses") or []:
                email_id = _get_value(email_address, "id")
                if email_id and email_id != new_email_id:
                    try:
                        client.email_addresses.delete(
                            email_address_id=email_id,
                            **_timeout_options(timeout_ms),
                        )
                    except Exception as exc:
                        _log_clerk_error(f"email delete for {email_id}", exc)
        return True
    except Exception as exc:
        _log_clerk_error(f"email update for {clerk_user_id}", exc)
        return False


def create_clerk_sign_in_token(
    clerk_user_id: str,
    *,
    expires_in_seconds: int = 7200,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> str | None:
    """Mint a one-time Clerk sign-in token for a user."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping sign-in token")
        return None

    try:
        response = client.sign_in_tokens.create(
            request={
                "user_id": clerk_user_id,
                "expires_in_seconds": int(expires_in_seconds),
            },
            **_timeout_options(timeout_ms),
        )
        return _get_value(_plain_data(response), "token")
    except Exception as exc:
        _log_clerk_error(f"sign-in token creation for {clerk_user_id}", exc)
        return None


def build_clerk_sign_in_url(
    sign_in_url: str,
    token: str,
    *,
    ticket_param: str = "__clerk_ticket",
) -> str:
    """Append a Clerk sign-in token to an app sign-in URL."""
    if not sign_in_url or not token:
        return ""

    parts = urlsplit(sign_in_url)
    query = [
        item
        for item in parse_qsl(parts.query, keep_blank_values=True)
        if item[0] != ticket_param
    ]
    query.append((ticket_param, token))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def create_clerk_sign_in_link(
    clerk_user_id: str,
    sign_in_url: str,
    *,
    expires_in_seconds: int = 7200,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> str:
    """Create a one-time sign-in link for a Clerk user."""
    token = create_clerk_sign_in_token(
        clerk_user_id,
        expires_in_seconds=expires_in_seconds,
        clerk_client=clerk_client,
        timeout_ms=timeout_ms,
    )
    if not token:
        return ""
    return build_clerk_sign_in_url(sign_in_url, token)


def provision_clerk_user_access_link(
    email: str,
    sign_in_url: str,
    *,
    first_name: str = "",
    last_name: str = "",
    public_metadata: dict[str, Any] | None = None,
    expires_in_seconds: int = 7200,
    auto_username: bool = False,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    """
    Create or resolve a Clerk user, then mint a one-time sign-in link.

    Returns a stable dict shape for invite/activation flows:
    ``clerk_user_id``, ``access_link``, ``sign_in_token``, ``created``,
    ``already_exists``, and ``no_key``.
    """
    user = create_clerk_user(
        email,
        first_name=first_name,
        last_name=last_name,
        public_metadata=public_metadata,
        auto_username=auto_username,
        clerk_client=clerk_client,
        timeout_ms=timeout_ms,
    )
    if isinstance(user, Mapping) and user.get("no_key"):
        return {
            "clerk_user_id": None,
            "access_link": "",
            "sign_in_token": "",
            "created": False,
            "already_exists": False,
            "no_key": True,
        }
    if not user:
        return {
            "clerk_user_id": None,
            "access_link": "",
            "sign_in_token": "",
            "created": False,
            "already_exists": False,
            "no_key": False,
        }

    already_exists = bool(user.get("already_exists"))
    clerk_user_id = user.get("id")
    if already_exists and not clerk_user_id:
        existing_user = get_clerk_user_by_email(
            email,
            clerk_client=clerk_client,
            timeout_ms=timeout_ms,
        )
        clerk_user_id = (existing_user or {}).get("id")

    if not clerk_user_id:
        return {
            "clerk_user_id": None,
            "access_link": "",
            "sign_in_token": "",
            "created": False,
            "already_exists": already_exists,
            "no_key": False,
        }

    token = create_clerk_sign_in_token(
        clerk_user_id,
        expires_in_seconds=expires_in_seconds,
        clerk_client=clerk_client,
        timeout_ms=timeout_ms,
    )
    access_link = build_clerk_sign_in_url(sign_in_url, token or "")

    return {
        "clerk_user_id": clerk_user_id,
        "access_link": access_link,
        "sign_in_token": token or "",
        "created": not already_exists,
        "already_exists": already_exists,
        "no_key": False,
    }


def revoke_clerk_user_sessions(
    clerk_user_id: str,
    *,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> int | None:
    """Revoke all active Clerk sessions for a user."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping session revoke")
        return None

    try:
        response = client.sessions.list(
            user_id=clerk_user_id,
            status="active",
            **_timeout_options(timeout_ms),
        )
        revoked = 0
        for session in _list_data(response):
            session_id = _get_value(session, "id")
            if not session_id:
                continue
            client.sessions.revoke(
                session_id=session_id,
                **_timeout_options(timeout_ms),
            )
            revoked += 1
        return revoked
    except Exception as exc:
        _log_clerk_error(f"session revoke for {clerk_user_id}", exc)
        return None


def send_clerk_invitation(
    email: str,
    *,
    public_metadata: dict[str, Any] | None = None,
    redirect_url: str | None = None,
    notify: bool = True,
    ignore_existing: bool = True,
    expires_in_days: int | None = None,
    template_slug: str | None = None,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    """Send a Clerk invitation email."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping Clerk invitation")
        return None

    request: dict[str, Any] = {
        "email_address": email,
        "notify": notify,
        "ignore_existing": ignore_existing,
    }
    if public_metadata is not None:
        request["public_metadata"] = public_metadata
    if redirect_url is not None:
        request["redirect_url"] = redirect_url
    if expires_in_days is not None:
        request["expires_in_days"] = int(expires_in_days)
    if template_slug is not None:
        request["template_slug"] = template_slug

    try:
        return _plain_data(
            client.invitations.create(
                request=request,
                **_timeout_options(timeout_ms),
            )
        )
    except Exception as exc:
        _log_clerk_error(f"invitation for {email}", exc)
        return None


def revoke_clerk_invitation(
    invitation_id: str,
    *,
    clerk_client: Any | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """Revoke a pending Clerk invitation."""
    client = _resolve_clerk_client(clerk_client)
    if client is None:
        logger.warning("CLERK_SECRET_KEY not configured, skipping invitation revoke")
        return False

    try:
        client.invitations.revoke(
            invitation_id=invitation_id,
            **_timeout_options(timeout_ms),
        )
        return True
    except Exception as exc:
        _log_clerk_error(f"invitation revoke for {invitation_id}", exc)
        return False
