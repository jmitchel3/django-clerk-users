"""
REST resources for every Clerk endpoint this package consumes.

These are drop-in replacements for the ``clerk-backend-api`` resource objects,
so ``ClerkClient`` can be handed to any existing call site in place of the SDK
client without editing the call.

That constraint drives the odd-looking signatures. The SDK's own argument
styles are inconsistent, and this package's call sites depend on them:

- ``users.list`` takes a ``request={...}`` dict, but ``organizations.list``
  takes flat ``limit``/``offset`` kwargs.
- ``users.create`` takes flat kwargs, but ``sessions.create`` and
  ``invitations.create`` take ``request={...}``.
- ``users.update`` mixes a positional-ish ``user_id`` kwarg with flat body
  kwargs.

Normalizing those would be the tidier API, and also a breaking change at every
call site. The inconsistency is preserved deliberately; each resource method
documents which style it accepts.

Every method accepts ``timeout_ms`` and forwards it to the transport.
"""

from __future__ import annotations

from typing import Any

from django_clerk_users.clerk_api.transport import ClerkTransport

__all__ = [
    "ClerkClient",
    "EmailAddressesResource",
    "InvitationsResource",
    "OrganizationMembershipsResource",
    "OrganizationsResource",
    "SessionsResource",
    "SignInTokensResource",
    "TestingTokensResource",
    "UsersResource",
]

DEFAULT_PAGE_SIZE = 100


class _Resource:
    def __init__(self, transport: ClerkTransport) -> None:
        self._transport = transport


def _body(request: dict[str, Any] | None, extra: dict[str, Any]) -> dict[str, Any]:
    """Merge a ``request={...}`` dict with flat kwargs.

    Call sites use one style or the other, never both, but accepting both keeps
    every resource method usable either way.
    """
    payload = dict(request or {})
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def _paging_params(
    limit: int | None, offset: int | None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = dict(extra or {})
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    return params


class UsersResource(_Resource):
    """``/users``."""

    def get(self, *, user_id: str, timeout_ms: int | None = None) -> Any:
        return self._transport.get(f"/users/{user_id}", timeout_ms=timeout_ms)

    def list(
        self,
        *,
        request: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Note the ``request={...}`` style, unlike ``organizations.list``.

        Clerk returns a bare JSON array here rather than a ``{"data": [...]}``
        envelope, which ``server_api._list_data`` already handles.
        """
        params = _body(request, kwargs)
        return self._transport.get("/users", params=params, timeout_ms=timeout_ms)

    def create(self, *, timeout_ms: int | None = None, **kwargs: Any) -> Any:
        """Flat kwargs, unlike ``sessions.create`` and ``invitations.create``."""
        return self._transport.post(
            "/users", json=_body(None, kwargs), timeout_ms=timeout_ms
        )

    def update(
        self, *, user_id: str, timeout_ms: int | None = None, **kwargs: Any
    ) -> Any:
        return self._transport.patch(
            f"/users/{user_id}", json=_body(None, kwargs), timeout_ms=timeout_ms
        )

    def delete(self, *, user_id: str, timeout_ms: int | None = None) -> Any:
        return self._transport.delete(f"/users/{user_id}", timeout_ms=timeout_ms)


class OrganizationsResource(_Resource):
    """``/organizations``."""

    def get(self, *, organization_id: str, timeout_ms: int | None = None) -> Any:
        return self._transport.get(
            f"/organizations/{organization_id}", timeout_ms=timeout_ms
        )

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Note the flat ``limit``/``offset`` style, unlike ``users.list``."""
        return self._transport.get(
            "/organizations",
            params=_paging_params(limit, offset, kwargs),
            timeout_ms=timeout_ms,
        )


class OrganizationMembershipsResource(_Resource):
    """``/organizations/{id}/memberships``."""

    def list(
        self,
        *,
        organization_id: str,
        limit: int | None = None,
        offset: int | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._transport.get(
            f"/organizations/{organization_id}/memberships",
            params=_paging_params(limit, offset, kwargs),
            timeout_ms=timeout_ms,
        )


class EmailAddressesResource(_Resource):
    """``/email_addresses``."""

    def create(
        self,
        *,
        request: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._transport.post(
            "/email_addresses", json=_body(request, kwargs), timeout_ms=timeout_ms
        )

    def delete(self, *, email_address_id: str, timeout_ms: int | None = None) -> Any:
        return self._transport.delete(
            f"/email_addresses/{email_address_id}", timeout_ms=timeout_ms
        )


class SignInTokensResource(_Resource):
    """``/sign_in_tokens``."""

    def create(
        self,
        *,
        request: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._transport.post(
            "/sign_in_tokens", json=_body(request, kwargs), timeout_ms=timeout_ms
        )


class SessionsResource(_Resource):
    """``/sessions``."""

    def create(
        self,
        *,
        request: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._transport.post(
            "/sessions", json=_body(request, kwargs), timeout_ms=timeout_ms
        )

    def create_token(
        self,
        *,
        session_id: str,
        expires_in_seconds: int | None = None,
        timeout_ms: int | None = None,
    ) -> Any:
        payload: dict[str, Any] = {}
        if expires_in_seconds is not None:
            payload["expires_in_seconds"] = int(expires_in_seconds)
        return self._transport.post(
            f"/sessions/{session_id}/tokens",
            json=payload or None,
            timeout_ms=timeout_ms,
        )

    def list(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Flat kwargs. ``limit``/``offset`` matter here: session revocation
        pages through this endpoint rather than trusting the default page."""
        params = _paging_params(limit, offset, kwargs)
        if user_id is not None:
            params["user_id"] = user_id
        if status is not None:
            params["status"] = status
        return self._transport.get("/sessions", params=params, timeout_ms=timeout_ms)

    def revoke(self, *, session_id: str, timeout_ms: int | None = None) -> Any:
        return self._transport.post(
            f"/sessions/{session_id}/revoke", timeout_ms=timeout_ms
        )


class InvitationsResource(_Resource):
    """``/invitations``."""

    def create(
        self,
        *,
        request: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._transport.post(
            "/invitations", json=_body(request, kwargs), timeout_ms=timeout_ms
        )

    def revoke(self, *, invitation_id: str, timeout_ms: int | None = None) -> Any:
        return self._transport.post(
            f"/invitations/{invitation_id}/revoke", timeout_ms=timeout_ms
        )


class TestingTokensResource(_Resource):
    """``/testing_tokens``."""

    def create(self, *, timeout_ms: int | None = None) -> Any:
        return self._transport.post("/testing_tokens", timeout_ms=timeout_ms)


class ClerkClient:
    """A thin stand-in for the ``clerk-backend-api`` ``Clerk`` client.

    Exposes the same resource attributes the call sites already use, so it can
    be passed as ``clerk_client=`` anywhere the SDK client was expected.
    """

    def __init__(
        self,
        secret_key: str,
        *,
        base_url: str | None = None,
        timeout_ms: int | None = None,
        transport: Any | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"timeout_ms": timeout_ms, "transport": transport}
        if base_url is not None:
            kwargs["base_url"] = base_url
        self.transport = ClerkTransport(secret_key, **kwargs)

        self.users = UsersResource(self.transport)
        self.organizations = OrganizationsResource(self.transport)
        self.organization_memberships = OrganizationMembershipsResource(self.transport)
        self.email_addresses = EmailAddressesResource(self.transport)
        self.sign_in_tokens = SignInTokensResource(self.transport)
        self.sessions = SessionsResource(self.transport)
        self.invitations = InvitationsResource(self.transport)
        self.testing_tokens = TestingTokensResource(self.transport)


def paginate(
    list_call: Any,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = 100,
    **kwargs: Any,
):
    """Yield every item across a paginated list endpoint.

    Consistent paging for the list operations, so callers stop re-implementing
    the same offset loop. A short page ends iteration; ``max_pages`` bounds the
    loop so an always-full response cannot spin forever.
    """
    from django_clerk_users.clerk_api.objects import ClerkObject

    offset = 0
    for _ in range(max_pages):
        response = list_call(limit=page_size, offset=offset, **kwargs)
        if isinstance(response, ClerkObject):
            page = list(response.get("data") or [])
        elif response is None:
            page = []
        else:
            page = list(response)

        yield from page

        if len(page) < page_size:
            return
        offset += page_size
