"""
httpx transport for the thin Clerk HTTP client.

This is the wire layer only: it signs requests with the secret key, applies
timeouts, decodes JSON into :class:`~django_clerk_users.clerk_api.objects.ClerkObject`
trees, and turns non-2xx responses into
:class:`~django_clerk_users.exceptions.ClerkAPIError`. Endpoint-specific
resources live above it.
"""

from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from django_clerk_users.clerk_api.objects import clerk_value
from django_clerk_users.exceptions import ClerkAPIError

__all__ = ["ClerkTransport", "CLERK_API_BASE_URL", "CLERK_API_DEFAULT_TIMEOUT_MS"]

CLERK_API_BASE_URL = "https://api.clerk.com/v1"
CLERK_API_DEFAULT_TIMEOUT_MS = 10_000


def _resolve_timeout_ms(timeout_ms: int | None) -> int:
    """Resolve a timeout in milliseconds, falling back to the Django setting.

    Mirrors ``server_api._timeout_options`` so both paths treat an unparseable
    ``CLERK_API_TIMEOUT_MS`` the same way: warn-free fallback to the default
    rather than raising at request time.
    """
    raw = (
        timeout_ms
        if timeout_ms is not None
        else getattr(settings, "CLERK_API_TIMEOUT_MS", CLERK_API_DEFAULT_TIMEOUT_MS)
    )
    try:
        return int(raw)
    except (TypeError, ValueError):
        return CLERK_API_DEFAULT_TIMEOUT_MS


class ClerkTransport:
    """Minimal authenticated JSON transport for the Clerk Backend API."""

    def __init__(
        self,
        secret_key: str,
        *,
        base_url: str = CLERK_API_BASE_URL,
        timeout_ms: int | None = None,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        # ``transport`` exists so tests can inject httpx.MockTransport without
        # patching module internals; ``client`` allows sharing a pooled client.
        self._transport = transport
        self._client = client

    def _build_client(self, timeout_ms: int) -> tuple[httpx.Client, bool]:
        if self._client is not None:
            return self._client, False
        client = httpx.Client(
            transport=self._transport,
            timeout=timeout_ms / 1000,
        )
        return client, True

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        timeout_ms: int | None = None,
    ) -> Any:
        """Perform a request and return the decoded body.

        Returns a ``ClerkObject`` for JSON objects, a list for JSON arrays, and
        ``None`` for empty bodies (Clerk returns 204 for some deletes).
        """
        resolved_timeout = _resolve_timeout_ms(
            timeout_ms if timeout_ms is not None else self.timeout_ms
        )
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "User-Agent": "django-clerk-users",
        }

        client, owned = self._build_client(resolved_timeout)
        try:
            response = client.request(
                method,
                url,
                params=_clean_params(params),
                json=json,
                headers=headers,
                timeout=resolved_timeout / 1000,
            )
        except httpx.TimeoutException as exc:
            raise ClerkAPIError(
                f"Clerk request timed out after {resolved_timeout}ms: {method} {url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ClerkAPIError(f"Clerk request failed: {method} {url}: {exc}") from exc
        finally:
            if owned:
                client.close()

        return self._handle_response(response, method=method, url=url)

    def _handle_response(self, response: httpx.Response, *, method: str, url: str):
        body = _decode_json(response)

        if response.is_success:
            return clerk_value(body)

        raise ClerkAPIError(
            _error_message(response, body, method=method, url=url),
            status_code=response.status_code,
            data=body,
            response=response,
        )

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop ``None`` values so they are not serialized as the string "None"."""
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _decode_json(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        # Error pages and gateway responses are not always JSON. Keep the text
        # so it reaches the exception message instead of masking the failure.
        return response.text or None


def _error_message(
    response: httpx.Response, body: Any, *, method: str, url: str
) -> str:
    detail = ""
    if isinstance(body, dict):
        errors = body.get("errors") or []
        messages = [
            str(item.get("long_message") or item.get("message"))
            for item in errors
            if isinstance(item, dict)
            and (item.get("long_message") or item.get("message"))
        ]
        detail = "; ".join(messages)
    elif isinstance(body, str):
        detail = body.strip()

    base = f"Clerk API error {response.status_code} for {method} {url}"
    return f"{base}: {detail}" if detail else base
