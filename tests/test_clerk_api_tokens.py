"""
Tests for session token verification without ``clerk-backend-api``.

Tokens are minted locally from a generated RSA keypair, so the whole suite runs
offline with no Clerk credentials. The JWKS endpoint is served through
``httpx.MockTransport``, which means the remote path is exercised end to end
(fetch, cache, rotation retry) rather than stubbed out.
"""

from __future__ import annotations

import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from django_clerk_users.clerk_api import ClerkTransport
from django_clerk_users.clerk_api.tokens import (
    RequestState,
    _fetch_jwks,
    _JWKSCache,
    _jwks_timeout_ms,
    _reject_machine_tokens,
    _unverified_kid,
    authenticate_session_token,
    clear_jwks_cache,
    compute_org_permissions,
    enrich_v2_org_claims,
    verify_session_token,
)
from django_clerk_users.exceptions import ClerkTokenError

SECRET_KEY = "sk_test_tokens"
AZP = "https://app.example.com"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_jwks_cache()
    yield
    clear_jwks_cache()


def make_keypair(kid="kid_primary"):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk.setdefault("alg", "RS256")
    jwk.setdefault("use", "sig")
    return private_pem, public_pem, jwk


KEYPAIR = make_keypair()
PRIVATE_PEM, PUBLIC_PEM, JWK = KEYPAIR


def mint(claims=None, *, private_pem=None, kid="kid_primary"):
    now = int(time.time())
    payload = {
        "sub": "user_123",
        "sid": "sess_123",
        "azp": AZP,
        "iat": now,
        "nbf": now - 5,
        "exp": now + 600,
    }
    payload.update(claims or {})
    return jwt.encode(
        payload,
        private_pem or PRIVATE_PEM,
        algorithm="RS256",
        headers={"kid": kid},
    )


def jwks_transport(keys=None, *, on_request=None):
    payload = {"keys": keys if keys is not None else [JWK]}

    def handler(request: httpx.Request) -> httpx.Response:
        if on_request is not None:
            on_request(request)
        return httpx.Response(200, json=payload)

    return ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))


class TestNetworklessVerification:
    def test_static_jwt_key_verifies_without_any_request(self):
        token = mint()

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["sub"] == "user_123"

    def test_newlines_in_the_configured_pem_are_tolerated(self):
        """Keys pasted into env vars keep their newlines."""
        token = mint()

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM + "\n\n")

        assert payload["sub"] == "user_123"

    def test_wrong_key_is_rejected_without_a_rotation_retry(self):
        other_private, _, _ = make_keypair(kid="kid_other")
        token = mint(private_pem=other_private)

        with pytest.raises(ClerkTokenError, match="invalid signature"):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_missing_configuration_is_reported(self):
        with pytest.raises(ClerkTokenError, match="no CLERK_SECRET_KEY"):
            verify_session_token(mint())


class TestRemoteJWKSVerification:
    def test_fetches_the_key_and_verifies(self):
        token = mint()

        payload = verify_session_token(
            token, secret_key=SECRET_KEY, transport=jwks_transport()
        )

        assert payload["sub"] == "user_123"

    def test_jwks_endpoint_is_called_authenticated(self):
        seen = {}

        def record(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")

        verify_session_token(
            mint(),
            secret_key=SECRET_KEY,
            transport=jwks_transport(on_request=record),
        )

        assert seen["url"] == "https://api.clerk.com/v1/jwks"
        assert seen["auth"] == f"Bearer {SECRET_KEY}"

    def test_key_is_cached_across_calls(self):
        calls = []
        transport = jwks_transport(on_request=lambda r: calls.append(1))

        verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)
        verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)

        assert len(calls) == 1

    def test_unknown_kid_is_reported(self):
        token = mint(kid="kid_missing")

        with pytest.raises(ClerkTokenError, match="no JWKS key matched"):
            verify_session_token(
                token, secret_key=SECRET_KEY, transport=jwks_transport()
            )

    def test_empty_jwks_is_reported(self):
        with pytest.raises(ClerkTokenError, match="no JWKS key matched"):
            verify_session_token(
                mint(), secret_key=SECRET_KEY, transport=jwks_transport(keys=[])
            )

    def test_jwks_without_keys_field_is_reported(self):
        def handler(request):
            return httpx.Response(200, json={"unexpected": True})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))

        with pytest.raises(ClerkTokenError, match="no keys"):
            verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)

    def test_jwks_response_is_read_by_subscript_not_attribute(self):
        """``keys`` is a Mapping method on ClerkObject, so attribute access
        would return the bound method instead of the key list."""
        from django_clerk_users.clerk_api import clerk_value

        response = clerk_value({"keys": [JWK]})

        assert callable(response.keys)
        assert response["keys"][0]["kid"] == "kid_primary"


class TestKeyRotation:
    def test_rotated_key_is_refetched_once_and_succeeds(self):
        """A cached stale key must not permanently break verification."""
        rotated_private, _, rotated_jwk = make_keypair(kid="kid_primary")
        token = mint(private_pem=rotated_private)

        calls = []
        served = [[JWK], [rotated_jwk]]

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            keys = served[min(len(calls) - 1, len(served) - 1)]
            return httpx.Response(200, json={"keys": keys})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))

        payload = verify_session_token(
            token, secret_key=SECRET_KEY, transport=transport
        )

        assert payload["sub"] == "user_123"
        assert len(calls) == 2

    def test_rotation_refresh_is_bounded_to_one_retry(self):
        """A genuinely bad signature must not loop refetching the JWKS."""
        other_private, _, _ = make_keypair(kid="kid_primary")
        token = mint(private_pem=other_private)

        calls = []
        transport = jwks_transport(on_request=lambda r: calls.append(1))

        with pytest.raises(ClerkTokenError, match="invalid signature"):
            verify_session_token(token, secret_key=SECRET_KEY, transport=transport)

        assert len(calls) == 2


class TestClaimValidation:
    def test_expired_token_is_rejected(self):
        now = int(time.time())
        token = mint({"iat": now - 1200, "nbf": now - 1200, "exp": now - 600})

        with pytest.raises(ClerkTokenError, match="expired"):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_not_yet_active_token_is_rejected(self):
        now = int(time.time())
        token = mint({"nbf": now + 600, "exp": now + 1200})

        with pytest.raises(ClerkTokenError, match="not active yet"):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_invalid_audience_is_rejected(self):
        token = mint({"aud": "unexpected"})

        with pytest.raises(ClerkTokenError, match="invalid audience"):
            verify_session_token(token, jwt_key=PUBLIC_PEM, audience="expected")

    def test_non_integer_iat_is_rejected(self):
        token = mint({"iat": "tomorrow"})

        with pytest.raises(ClerkTokenError, match="iat is in the future"):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_authorized_party_allowlist_accepts_a_match(self):
        payload = verify_session_token(
            mint(), jwt_key=PUBLIC_PEM, authorized_parties=[AZP]
        )

        assert payload["azp"] == AZP

    def test_authorized_party_allowlist_rejects_a_mismatch(self):
        with pytest.raises(ClerkTokenError, match="authorized party"):
            verify_session_token(
                mint(), jwt_key=PUBLIC_PEM, authorized_parties=["https://other.test"]
            )

    def test_missing_azp_is_rejected_when_an_allowlist_is_configured(self):
        token = mint({"azp": None})

        with pytest.raises(ClerkTokenError, match="authorized party"):
            verify_session_token(token, jwt_key=PUBLIC_PEM, authorized_parties=[AZP])

    def test_no_allowlist_skips_the_azp_check(self):
        token = mint({"azp": None})

        payload = verify_session_token(
            token, jwt_key=PUBLIC_PEM, authorized_parties=None
        )

        assert payload["sub"] == "user_123"

    def test_hs256_token_is_rejected(self):
        """Algorithm confusion: only RS256 is accepted."""
        token = jwt.encode({"sub": "user_123"}, "a" * 64, algorithm="HS256")

        with pytest.raises(ClerkTokenError):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_garbage_token_is_rejected(self):
        with pytest.raises(ClerkTokenError):
            verify_session_token("not-a-jwt", jwt_key=PUBLIC_PEM)


class TestV1Tokens:
    def test_flat_org_claims_are_left_untouched(self):
        token = mint(
            {
                "org_id": "org_v1",
                "org_slug": "acme",
                "org_role": "org:admin",
            }
        )

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_id"] == "org_v1"
        assert payload["org_slug"] == "acme"
        assert payload["org_role"] == "org:admin"

    def test_v1_token_without_org_has_no_org_id(self):
        payload = verify_session_token(mint(), jwt_key=PUBLIC_PEM)

        assert payload.get("org_id") is None


class TestV2OrgClaimEnrichment:
    """v2 tokens carry no top-level org_id; every consumer reads the flat key."""

    def test_org_id_is_synthesised_from_the_o_claim(self):
        token = mint(
            {
                "v": 2,
                "o": {"id": "org_v2", "slg": "acme", "rol": "admin"},
            }
        )

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_id"] == "org_v2"
        assert payload["org_slug"] == "acme"
        assert payload["org_role"] == "admin"

    def test_without_enrichment_request_org_would_be_none(self):
        """Pins the bug this enrichment exists to prevent."""
        raw = {"v": 2, "o": {"id": "org_v2"}}

        assert raw.get("org_id") is None
        assert enrich_v2_org_claims(dict(raw))["org_id"] == "org_v2"

    def test_v2_token_without_an_active_org(self):
        token = mint({"v": 2})

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload.get("org_id") is None

    def test_org_permissions_are_expanded_from_the_bitmask(self):
        token = mint(
            {
                "v": 2,
                "fea": "o:memberships,o:billing",
                "o": {
                    "id": "org_v2",
                    "slg": "acme",
                    "rol": "admin",
                    "per": "read,manage",
                    "fpm": "3,1",
                },
            }
        )

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_permissions"] == [
            "org:memberships:read",
            "org:memberships:manage",
            "org:billing:read",
        ]

    def test_user_scoped_features_are_skipped(self):
        claims = {
            "v": 2,
            "fea": "u:profile,o:billing",
            "o": {"id": "org_v2", "per": "read,manage", "fpm": "3,1"},
        }

        assert compute_org_permissions(claims) == ["org:billing:read"]

    def test_missing_fea_yields_no_permissions(self):
        claims = {"v": 2, "o": {"id": "o", "per": "read", "fpm": "1"}}

        assert compute_org_permissions(claims) == []

    def test_non_string_permission_claims_yield_no_permissions(self):
        claims = {"v": 2, "fea": "o:billing", "o": {"per": None, "fpm": "1"}}

        assert compute_org_permissions(claims) == []

    def test_unparseable_mapping_is_skipped(self):
        claims = {"v": 2, "fea": "o:billing", "o": {"per": "read", "fpm": "abc"}}

        assert compute_org_permissions(claims) == []

    def test_zero_mapping_grants_nothing(self):
        claims = {"v": 2, "fea": "o:billing", "o": {"per": "read", "fpm": "0"}}

        assert compute_org_permissions(claims) == []

    def test_unset_permission_bit_is_skipped(self):
        claims = {
            "v": 2,
            "fea": "o:billing",
            "o": {"per": "read,manage", "fpm": "2"},
        }

        assert compute_org_permissions(claims) == ["org:billing:manage"]

    def test_malformed_feature_entry_is_skipped(self):
        claims = {"v": 2, "fea": "billing", "o": {"per": "read", "fpm": "1"}}

        assert compute_org_permissions(claims) == []

    def test_more_mappings_than_features_are_ignored(self):
        claims = {"v": 2, "fea": "o:billing", "o": {"per": "read", "fpm": "1,1,1"}}

        assert compute_org_permissions(claims) == ["org:billing:read"]

    def test_v1_payload_is_not_enriched(self):
        payload = {"org_id": "org_v1", "o": {"id": "ignored"}}

        assert enrich_v2_org_claims(payload)["org_id"] == "org_v1"

    def test_none_payload_is_passed_through(self):
        assert enrich_v2_org_claims(None) is None


class TestRequestState:
    def test_signed_in_state_exposes_payload(self):
        state = authenticate_session_token(mint(), jwt_key=PUBLIC_PEM)

        assert state.is_signed_in is True
        assert state.payload["sub"] == "user_123"
        assert state.is_signed_out is False

    def test_attributes_are_real_not_dict_keys(self):
        """utils.py reads .is_signed_in and .payload with no getattr guard."""
        state = authenticate_session_token(mint(), jwt_key=PUBLIC_PEM)

        assert isinstance(state, RequestState)
        assert state.is_signed_in
        assert state.payload

    def test_missing_token_is_signed_out(self):
        state = authenticate_session_token(None, jwt_key=PUBLIC_PEM)

        assert state.is_signed_in is False
        assert state.reason == "session token missing"

    def test_invalid_token_is_signed_out_with_a_reason(self):
        now = int(time.time())
        token = mint({"iat": now - 1200, "nbf": now - 1200, "exp": now - 600})

        state = authenticate_session_token(token, jwt_key=PUBLIC_PEM)

        assert state.is_signed_in is False
        assert "expired" in state.reason

    def test_empty_verified_payload_is_signed_out(self, monkeypatch):
        import django_clerk_users.clerk_api.tokens as token_module

        monkeypatch.setattr(token_module, "verify_session_token", lambda *a, **k: {})

        state = token_module.authenticate_session_token("token")

        assert state.is_signed_in is False
        assert state.reason == "no payload"


class TestTokenHelperEdgeCases:
    def test_jwks_cache_handles_none_and_expired_entries(self):
        cache = _JWKSCache()

        cache.set(None, "ignored")
        cache.mark_missing(None)
        cache.delete(None)
        assert cache.get(None) is None
        assert cache.is_known_missing(None) is False

        cache._entries["expired"] = ("pem", 0)
        assert cache.get("expired") is None
        assert "expired" not in cache._entries

    def test_non_string_token_is_ignored_by_machine_prefix_check(self):
        assert _reject_machine_tokens(object()) is None

    def test_invalid_jwks_timeout_uses_strict_default(self):
        from django_clerk_users.clerk_api.tokens import JWKS_FETCH_TIMEOUT_MS

        assert _jwks_timeout_ms(object()) == JWKS_FETCH_TIMEOUT_MS

    def test_malformed_token_header_is_wrapped(self):
        with pytest.raises(ClerkTokenError, match="Token validation failed"):
            _unverified_kid("not-a-jwt")

    def test_empty_jwks_response_is_rejected(self):
        class EmptyTransport:
            def get(self, path, **kwargs):
                return None

        with pytest.raises(ClerkTokenError, match="JWKS response was empty"):
            _fetch_jwks(
                secret_key=SECRET_KEY,
                transport=EmptyTransport(),
                timeout_ms=250,
            )


class TestNoSDKImportRequired:
    def test_token_module_does_not_import_clerk_backend_api(self):
        import django_clerk_users.clerk_api.tokens as tokens_module

        source = open(tokens_module.__file__).read()

        assert "clerk_backend_api" not in source

    def test_authentication_utils_does_not_import_the_sdk_at_module_scope(self):
        import django_clerk_users.authentication.utils as utils_module

        source = open(utils_module.__file__).read()

        assert "clerk_backend_api" not in source

    def test_client_module_has_no_module_level_sdk_import(self):
        import django_clerk_users.client as client_module

        assert not hasattr(client_module, "Clerk")

    def test_verification_works_with_the_sdk_uninstalled(self, monkeypatch):
        """The headline outcome: session tokens verify with no SDK present.

        Simulates an uninstalled clerk-backend-api by making any import of it
        raise ImportError, then re-imports the verification modules from
        scratch under that constraint.
        """
        import builtins
        import sys

        real_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "clerk_backend_api" or name.startswith("clerk_backend_api."):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        for module in list(sys.modules):
            if module.startswith("clerk_backend_api"):
                monkeypatch.delitem(sys.modules, module)
        for module in (
            "django_clerk_users.clerk_api.tokens",
            "django_clerk_users.authentication.utils",
            "django_clerk_users.client",
        ):
            monkeypatch.delitem(sys.modules, module, raising=False)

        monkeypatch.setattr(builtins, "__import__", blocked_import)

        import importlib

        tokens = importlib.import_module("django_clerk_users.clerk_api.tokens")
        importlib.import_module("django_clerk_users.authentication.utils")
        client = importlib.import_module("django_clerk_users.client")

        payload = tokens.verify_session_token(mint(), jwt_key=PUBLIC_PEM)
        assert payload["sub"] == "user_123"

        # Explicitly selecting the SDK backend without the SDK installed fails
        # with an actionable configuration error, not an ImportError at import
        # time. The default (thin) backend never reaches that code path.
        from django.test import override_settings

        from django_clerk_users.exceptions import ClerkConfigurationError

        client.get_clerk_client.cache_clear()
        try:
            with override_settings(
                CLERK_SECRET_KEY="sk_test_unit_backend_secret",
                CLERK_CLIENT_BACKEND="sdk",
            ):
                with pytest.raises(ClerkConfigurationError, match="clerk-backend-api"):
                    client.get_clerk_client()
        finally:
            client.get_clerk_client.cache_clear()
