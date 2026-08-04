"""
Tests for verification hardening applied on top of the SDK-parity port.

Each behavior here is a deliberate divergence from ``clerk-backend-api``, not a
refactor, so each gets a test that would fail against the SDK's semantics.
"""

from __future__ import annotations

import threading
import time

import httpx
import jwt
import pytest

from django_clerk_users.clerk_api import ClerkTransport
from django_clerk_users.clerk_api.tokens import (
    JWKS_FETCH_TIMEOUT_MS,
    MACHINE_TOKEN_PREFIXES,
    REQUIRED_CLAIMS,
    clear_jwks_cache,
    enrich_v2_org_claims,
    verify_session_token,
)
from django_clerk_users.exceptions import ClerkTokenError
from tests.test_clerk_api_tokens import JWK, PRIVATE_PEM, PUBLIC_PEM, mint

SECRET_KEY = "sk_test_hardening"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_jwks_cache()
    yield
    clear_jwks_cache()


def counting_transport(keys=None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"keys": keys if keys is not None else [JWK]})

    transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))
    return transport, calls


class TestMachineTokensRejectedBeforeNetwork:
    @pytest.mark.parametrize("prefix", MACHINE_TOKEN_PREFIXES)
    def test_machine_token_prefixes_are_rejected(self, prefix):
        with pytest.raises(ClerkTokenError, match="machine token"):
            verify_session_token(f"{prefix}abc123", jwt_key=PUBLIC_PEM)

    @pytest.mark.parametrize("prefix", MACHINE_TOKEN_PREFIXES)
    def test_rejection_happens_before_any_jwks_request(self, prefix):
        """The point of rejecting by prefix: no outbound request is spent."""
        transport, calls = counting_transport()

        with pytest.raises(ClerkTokenError, match="machine token"):
            verify_session_token(
                f"{prefix}abc123", secret_key=SECRET_KEY, transport=transport
            )

        assert calls == []

    def test_session_tokens_are_unaffected(self):
        payload = verify_session_token(mint(), jwt_key=PUBLIC_PEM)

        assert payload["sub"] == "user_123"

    def test_surrounding_whitespace_does_not_bypass_the_check(self):
        with pytest.raises(ClerkTokenError, match="machine token"):
            verify_session_token("  ak_abc123  ", jwt_key=PUBLIC_PEM)


class TestRequiredClaims:
    @pytest.mark.parametrize("claim", REQUIRED_CLAIMS)
    def test_missing_required_claim_is_rejected(self, claim):
        """PyJWT only validates claims that are present, so absence must fail."""
        now = int(time.time())
        claims = {
            "sub": "user_123",
            "sid": "sess_123",
            "azp": "https://app.example.com",
            "iat": now,
            "exp": now + 600,
        }
        del claims[claim]
        token = jwt.encode(
            claims, PRIVATE_PEM, algorithm="RS256", headers={"kid": "kid_primary"}
        )

        with pytest.raises(ClerkTokenError):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_a_token_with_no_exp_cannot_be_eternally_valid(self):
        """Without the require option this token would verify forever."""
        token = jwt.encode(
            {"sub": "user_123", "sid": "sess_123"},
            PRIVATE_PEM,
            algorithm="RS256",
            headers={"kid": "kid_primary"},
        )

        # Confirm the token really is otherwise valid: PyJWT alone accepts it.
        assert jwt.decode(token, PUBLIC_PEM, algorithms=["RS256"])["sub"] == "user_123"

        with pytest.raises(ClerkTokenError):
            verify_session_token(token, jwt_key=PUBLIC_PEM)

    def test_all_required_claims_present_verifies(self):
        payload = verify_session_token(mint(), jwt_key=PUBLIC_PEM)

        assert all(claim in payload for claim in REQUIRED_CLAIMS)


class TestV2OrgClaimsCannotBeForged:
    """The privilege boundary: request.org must come only from the o claim."""

    def test_custom_flat_org_id_is_cleared_when_o_is_absent(self):
        token = mint({"v": 2, "org_id": "org_attacker"})

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_id"] is None

    def test_custom_flat_org_id_is_overwritten_when_o_is_present(self):
        token = mint({"v": 2, "org_id": "org_attacker", "o": {"id": "org_real"}})

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_id"] == "org_real"

    def test_slug_role_and_permissions_are_also_cleared(self):
        token = mint(
            {
                "v": 2,
                "org_id": "org_attacker",
                "org_slug": "attacker",
                "org_role": "admin",
                "org_permissions": ["org:billing:manage"],
            }
        )

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_id"] is None
        assert payload["org_slug"] is None
        assert payload["org_role"] is None
        assert payload["org_permissions"] == []

    def test_forged_permissions_do_not_survive_a_real_org(self):
        token = mint(
            {
                "v": 2,
                "org_permissions": ["org:billing:manage"],
                "o": {"id": "org_real", "per": "read", "fpm": "1"},
                "fea": "o:billing",
            }
        )

        payload = verify_session_token(token, jwt_key=PUBLIC_PEM)

        assert payload["org_permissions"] == ["org:billing:read"]

    def test_v1_tokens_keep_their_flat_claims(self):
        """v1 legitimately carries flat claims; only v2 is normalized."""
        payload = enrich_v2_org_claims({"org_id": "org_v1", "org_role": "org:admin"})

        assert payload["org_id"] == "org_v1"
        assert payload["org_role"] == "org:admin"


class TestNegativeCaching:
    def test_unknown_kid_does_not_refetch_on_every_attempt(self):
        token = mint(kid="kid_missing")
        transport, calls = counting_transport()

        for _ in range(5):
            with pytest.raises(ClerkTokenError, match="no JWKS key matched"):
                verify_session_token(token, secret_key=SECRET_KEY, transport=transport)

        assert len(calls) == 1

    def test_negative_entry_expires(self, monkeypatch):
        from django_clerk_users.clerk_api import tokens

        token = mint(kid="kid_missing")
        transport, calls = counting_transport()

        with pytest.raises(ClerkTokenError):
            verify_session_token(token, secret_key=SECRET_KEY, transport=transport)

        # Jump past the negative TTL.
        real_time = time.time
        monkeypatch.setattr(
            tokens.time,
            "time",
            lambda: real_time() + tokens.JWKS_NEGATIVE_CACHE_SECONDS + 1,
        )

        with pytest.raises(ClerkTokenError):
            verify_session_token(token, secret_key=SECRET_KEY, transport=transport)

        assert len(calls) == 2

    def test_a_resolvable_kid_is_not_negative_cached(self):
        transport, calls = counting_transport()

        verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)
        verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)

        assert len(calls) == 1

    def test_negative_cache_does_not_block_a_rotated_key(self):
        """Rotation evicts both positive and negative entries."""
        from tests.test_clerk_api_tokens import make_keypair

        rotated_private, _, rotated_jwk = make_keypair(kid="kid_primary")
        token = mint(private_pem=rotated_private)

        calls = []
        served = [[JWK], [rotated_jwk]]

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                200, json={"keys": served[min(len(calls) - 1, len(served) - 1)]}
            )

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))

        payload = verify_session_token(
            token, secret_key=SECRET_KEY, transport=transport
        )

        assert payload["sub"] == "user_123"


class TestSingleFlightAndTimeout:
    def test_concurrent_first_fetches_issue_one_request(self):
        calls = []
        barrier = threading.Barrier(4)

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            # Hold the fetch open so any un-serialized caller would overlap.
            time.sleep(0.05)
            return httpx.Response(200, json={"keys": [JWK]})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)
            except Exception as exc:  # pragma: no cover - surfaced via assert
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert errors == []
        assert len(calls) == 1

    def test_concurrent_unknown_kids_issue_one_request(self):
        """The amplification case: many callers, one unknown kid."""
        calls = []
        barrier = threading.Barrier(4)

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            time.sleep(0.05)
            return httpx.Response(200, json={"keys": [JWK]})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))
        token = mint(kid="kid_missing")
        rejections = []

        def worker():
            barrier.wait(timeout=5)
            try:
                verify_session_token(token, secret_key=SECRET_KEY, transport=transport)
            except ClerkTokenError as exc:
                rejections.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(rejections) == 4
        assert len(calls) == 1

    def test_jwks_fetch_uses_the_strict_timeout(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={"keys": [JWK]})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))

        verify_session_token(mint(), secret_key=SECRET_KEY, transport=transport)

        assert seen["timeout"]["read"] == pytest.approx(JWKS_FETCH_TIMEOUT_MS / 1000)

    def test_a_longer_caller_timeout_does_not_relax_the_ceiling(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={"keys": [JWK]})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))

        verify_session_token(
            mint(), secret_key=SECRET_KEY, transport=transport, timeout_ms=60_000
        )

        assert seen["timeout"]["read"] == pytest.approx(JWKS_FETCH_TIMEOUT_MS / 1000)

    def test_a_shorter_caller_timeout_still_wins(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={"keys": [JWK]})

        transport = ClerkTransport(SECRET_KEY, transport=httpx.MockTransport(handler))

        verify_session_token(
            mint(), secret_key=SECRET_KEY, transport=transport, timeout_ms=250
        )

        assert seen["timeout"]["read"] == pytest.approx(0.25)
