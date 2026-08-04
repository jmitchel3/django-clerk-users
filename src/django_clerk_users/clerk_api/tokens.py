"""
Session token verification without ``clerk-backend-api``.

Ported to match the SDK's semantics rather than improve on them, so swapping
the verification path does not change which tokens are accepted. Hardening
beyond SDK parity is tracked separately.

Two verification modes:

- **Networkless**, when ``CLERK_JWT_KEY`` is configured: the PEM public key is
  used directly and no JWKS request is made.
- **Remote JWKS**, otherwise: the key is fetched from Clerk's authenticated
  ``/jwks`` endpoint and cached by ``kid``. A signature failure evicts the
  cached key and retries exactly once, which covers key rotation without
  turning a genuinely bad signature into an unbounded refetch loop.

This module is bearer-token only. The SDK also reads a ``__session`` cookie,
but accepting a cookie is a new authentication mechanism with CSRF
implications, not compatibility work, so it is deliberately not ported.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import jwt
from jwt.algorithms import RSAAlgorithm

from django_clerk_users.clerk_api.transport import ClerkTransport
from django_clerk_users.exceptions import ClerkTokenError

__all__ = [
    "RequestState",
    "authenticate_session_token",
    "compute_org_permissions",
    "enrich_v2_org_claims",
    "verify_session_token",
]

DEFAULT_CLOCK_SKEW_MS = 5000
JWKS_CACHE_SECONDS = 300


@dataclass
class RequestState:
    """The result of verifying a request's session token.

    A real object rather than a dict because ``authentication/utils.py`` reads
    ``request_state.is_signed_in`` and ``request_state.payload`` directly, with
    no ``getattr`` guard.
    """

    is_signed_in: bool = False
    payload: dict[str, Any] | None = None
    reason: str | None = None

    @property
    def is_signed_out(self) -> bool:
        return not self.is_signed_in


@dataclass
class _JWKSCache:
    """In-memory PEM cache keyed by ``kid``, mirroring the SDK's 5 minute TTL."""

    ttl_seconds: int = JWKS_CACHE_SECONDS
    _entries: dict[str, tuple[str, float]] = field(default_factory=dict)

    def get(self, kid: str | None) -> str | None:
        if kid is None:
            return None
        entry = self._entries.get(kid)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() >= expires_at:
            del self._entries[kid]
            return None
        return value

    def set(self, kid: str | None, value: str) -> None:
        if kid is None:
            return
        self._entries[kid] = (value, time.time() + self.ttl_seconds)

    def delete(self, kid: str | None) -> None:
        if kid is not None:
            self._entries.pop(kid, None)

    def clear(self) -> None:
        self._entries.clear()


_jwks_cache = _JWKSCache()


def clear_jwks_cache() -> None:
    """Drop every cached JWKS key. Exposed for tests and key-rotation tooling."""
    _jwks_cache.clear()


def compute_org_permissions(claims: dict[str, Any]) -> list[str]:
    """Expand v2 feature/permission bitmaps into ``org:<feature>:<permission>``.

    A v2 token encodes org permissions compactly across three claims:
    ``fea`` (scoped feature list), ``o.per`` (permission names), and
    ``o.fpm`` (a per-feature bitmask selecting which permissions apply).
    Ported from the SDK bit-for-bit so the expansion stays identical.
    """
    features_str = claims.get("fea")
    if features_str is None:
        return []

    org_claims = claims.get("o") or {}
    permissions_str = org_claims.get("per")
    mappings_str = org_claims.get("fpm")

    if not all(isinstance(value, str) for value in (permissions_str, mappings_str)):
        return []

    features = features_str.split(",")
    permissions = permissions_str.split(",")
    mappings = mappings_str.split(",")

    org_permissions: list[str] = []

    for index, mapping in enumerate(mappings):
        if index >= len(features):
            continue
        feature_parts = features[index].split(":")
        if len(feature_parts) != 2:
            continue

        scope, feature = feature_parts
        # Features can be scoped to the user ("u"), the org ("o"), or both.
        if "o" not in scope:
            continue

        try:
            binary = bin(int(mapping))[2:].lstrip("0")
        except ValueError:
            continue

        # The bitmask is little-endian relative to the permission list: bit i
        # selects permissions[i].
        for position, bit in enumerate(binary[::-1]):
            if bit == "1" and position < len(permissions):
                org_permissions.append(f"org:{feature}:{permissions[position]}")

    return org_permissions


def enrich_v2_org_claims(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Synthesise flat org claims on v2 tokens, in place.

    v2 tokens carry no top-level ``org_id``; the active organization lives in
    the nested ``o`` claim. Every consumer in this package reads the flat key
    (``middleware/auth.py`` and ``authentication/drf.py`` all do
    ``payload.get("org_id")``), so without this ``request.org`` would be
    ``None`` for every v2 token.

    v1 tokens already carry the flat claims and are left untouched.
    """
    if payload is None or payload.get("v") != 2:
        return payload

    org_claims = payload.get("o") or {}
    if not org_claims:
        return payload

    payload["org_id"] = org_claims.get("id")
    payload["org_slug"] = org_claims.get("slg")
    payload["org_role"] = org_claims.get("rol")

    org_permissions = compute_org_permissions(payload)
    if org_permissions:
        payload["org_permissions"] = org_permissions

    return payload


def _normalize_jwt_key(jwt_key: str) -> str:
    """Strip newlines the way the SDK does, so env-var PEMs work verbatim."""
    return re.sub(r"(\r\n|\n|\r)", "", jwt_key)


def _unverified_kid(token: str) -> str | None:
    try:
        return jwt.get_unverified_header(token).get("kid")
    except jwt.InvalidTokenError as exc:
        raise ClerkTokenError(f"Token validation failed: {exc}") from exc


def _fetch_jwks(
    *, secret_key: str, transport: ClerkTransport | None, timeout_ms: int | None
) -> list[dict[str, Any]]:
    transport = transport or ClerkTransport(secret_key)
    response = transport.get("/jwks", timeout_ms=timeout_ms)
    if response is None:
        raise ClerkTokenError("Token validation failed: JWKS response was empty")

    # Subscripting, not attribute access: ``keys`` is a Mapping method on
    # ClerkObject, so ``response.keys`` would return the bound method.
    try:
        keys = response["keys"]
    except (KeyError, TypeError) as exc:
        raise ClerkTokenError(
            "Token validation failed: JWKS response had no keys"
        ) from exc

    return list(keys or [])


def _remote_public_key(
    token: str,
    *,
    secret_key: str,
    transport: ClerkTransport | None,
    timeout_ms: int | None,
) -> str:
    kid = _unverified_kid(token)
    cached = _jwks_cache.get(kid)
    if cached is not None:
        return cached

    for key in _fetch_jwks(
        secret_key=secret_key, transport=transport, timeout_ms=timeout_ms
    ):
        key_data = dict(key)
        if key_data.get("kid") != kid:
            continue
        public_key = RSAAlgorithm.from_jwk(key_data)
        pem = public_key.public_bytes(
            encoding=_serialization().Encoding.PEM,
            format=_serialization().PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        _jwks_cache.set(kid, pem)
        return pem

    raise ClerkTokenError(f"Token validation failed: no JWKS key matched kid {kid!r}")


def _serialization():
    from cryptography.hazmat.primitives import serialization

    return serialization


def _decode(
    token: str,
    key: str,
    *,
    audience: Any,
    authorized_parties: list[str] | None,
    clock_skew_ms: int,
) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=audience,
        options={"verify_iss": False},
        leeway=timedelta(milliseconds=float(clock_skew_ms)),
    )

    # Matches the SDK: the azp check runs only when an allowlist is configured.
    # An empty list would reject every token, so callers must pass None to skip.
    if authorized_parties is not None:
        azp = payload.get("azp")
        if azp is None or azp not in authorized_parties:
            raise ClerkTokenError("Token validation failed: invalid authorized party")

    return payload


def verify_session_token(
    token: str,
    *,
    secret_key: str | None = None,
    jwt_key: str | None = None,
    authorized_parties: list[str] | None = None,
    audience: Any = None,
    clock_skew_ms: int = DEFAULT_CLOCK_SKEW_MS,
    transport: ClerkTransport | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    """Verify a Clerk session token and return its enriched payload.

    Raises :class:`ClerkTokenError` for every rejection so callers keep a
    single exception type to handle.
    """
    if jwt_key:
        key = _normalize_jwt_key(jwt_key)
        allow_rotation_retry = False
    elif secret_key:
        key = _remote_public_key(
            token,
            secret_key=secret_key,
            transport=transport,
            timeout_ms=timeout_ms,
        )
        allow_rotation_retry = True
    else:
        raise ClerkTokenError(
            "Token validation failed: no CLERK_SECRET_KEY or CLERK_JWT_KEY configured"
        )

    try:
        payload = _decode(
            token,
            key,
            audience=audience,
            authorized_parties=authorized_parties,
            clock_skew_ms=clock_skew_ms,
        )
    except jwt.InvalidSignatureError as exc:
        if not allow_rotation_retry:
            raise ClerkTokenError("Token validation failed: invalid signature") from exc

        # Key rotation: evict the cached key and refetch exactly once. Bounded
        # deliberately, so a genuinely bad signature cannot loop.
        kid = _unverified_kid(token)
        _jwks_cache.delete(kid)
        refreshed = _remote_public_key(
            token,
            secret_key=secret_key,
            transport=transport,
            timeout_ms=timeout_ms,
        )
        try:
            payload = _decode(
                token,
                refreshed,
                audience=audience,
                authorized_parties=authorized_parties,
                clock_skew_ms=clock_skew_ms,
            )
        except jwt.InvalidSignatureError as retry_exc:
            raise ClerkTokenError(
                "Token validation failed: invalid signature"
            ) from retry_exc
    except jwt.ExpiredSignatureError as exc:
        raise ClerkTokenError("Token validation failed: token expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise ClerkTokenError("Token validation failed: invalid audience") from exc
    except jwt.ImmatureSignatureError as exc:
        raise ClerkTokenError("Token validation failed: token not active yet") from exc
    except jwt.InvalidIssuedAtError as exc:
        raise ClerkTokenError("Token validation failed: iat is in the future") from exc
    except jwt.InvalidTokenError as exc:
        raise ClerkTokenError(f"Token validation failed: {exc}") from exc

    return enrich_v2_org_claims(payload)


def authenticate_session_token(token: str | None, **kwargs: Any) -> RequestState:
    """Verify a token and report the outcome as a :class:`RequestState`.

    Takes the already-extracted token rather than the request so this module
    stays independent of ``authentication.utils``, which imports from here.
    """
    if not token:
        return RequestState(is_signed_in=False, reason="session token missing")

    try:
        payload = verify_session_token(token, **kwargs)
    except ClerkTokenError as exc:
        return RequestState(is_signed_in=False, reason=str(exc))

    if not payload:
        return RequestState(is_signed_in=False, reason="no payload")

    return RequestState(is_signed_in=True, payload=payload)
