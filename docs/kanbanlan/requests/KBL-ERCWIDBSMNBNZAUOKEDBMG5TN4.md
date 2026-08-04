# Port Clerk session token verification and org claim enrichment

- Kanbanlan: `KBL-ERCWIDBSMNBNZAUOKEDBMG5TN4`
- Canonical home: `github`
- Canonical request: [#8](https://github.com/jmitchel3/django-clerk-users/issues/8)

## Request

Outcome: session tokens verify without clerk-backend-api installed.

Scope:
- RS256 verification against the authenticated JWKS endpoint, with azp checked against CLERK_FRONTEND_HOSTS and one bounded rotation refresh.
- Optional static CLERK_JWT_KEY for fully networkless verification.
- v2 org claim enrichment. v2 tokens carry no top-level org_id; it is synthesised from the o claim, and middleware/auth.py:172, :212, :258 and drf.py:116 all read the flat key. Without this, request.org is None for every v2 token.
- RequestState as a real object exposing is_signed_in and payload, since authentication/utils.py:188 and :193 access them with no getattr guard.
- Removes the module-level SDK type import at authentication/utils.py:12 and the Clerk import at client.py:7.

Stays bearer-only. Cookie extraction would be a new authentication mechanism with CSRF implications, not compatibility work.

Tested against v1 and v2 fixtures minted from a locally generated RSA keypair; no live credentials.

## Decisions

- **Ported the SDK's semantics bit-for-bit rather than improving on them.**
  This request swaps the verification engine on the live auth path, so the set
  of accepted tokens must not shift. `compute_org_permissions` in particular is
  a direct port of the SDK's bitmask expansion, including its quirks
  (`bin(int(mapping))[2:].lstrip("0")`, little-endian bit-to-permission
  mapping, skipping features whose scope lacks `o`). Hardening is #9's job.
- **`org_role` is the raw `rol` value, not `org:`-prefixed.** The Python SDK
  sets `payload["org_role"] = org_claims.get("rol")` verbatim, so v2 yields
  `"admin"` where a v1 token carries `"org:admin"`. That asymmetry is upstream
  behavior; matching it is parity, and changing it would be a silent breaking
  change for anyone comparing role strings.
- **PyJWT became a direct dependency.** It is the same library the SDK already
  uses internally, so verification semantics are unchanged; it just stops
  arriving as an SDK transitive. Hand-rolling RS256 against `cryptography` was
  the alternative and was rejected: JWT verification is security-sensitive, and
  a bespoke implementation would diverge from the SDK exactly where parity
  matters most.
- **Rotation retry is bounded to exactly one refetch.** A cached stale key must
  not permanently break verification, but a genuinely bad signature must not
  loop refetching the JWKS. Both directions are tested.
- **The static-key path gets no rotation retry.** With `CLERK_JWT_KEY`
  configured there is nothing to refetch, so a bad signature fails immediately.
- **The JWKS response is read by subscript, not attribute.** `response["keys"]`
  rather than `response.keys`, because `keys` is a `Mapping` method on
  `ClerkObject` and attribute access returns the bound method. This is the
  documented `ClerkObject` limitation from #6 biting in real code; there is a
  test pinning it so the trap is visible to the next reader.
- **`client.py` imports the SDK lazily inside `get_clerk_client`**, and
  `from __future__ import annotations` was required because the `-> Clerk`
  return annotation would otherwise be evaluated at runtime and raise
  `NameError`. A missing SDK now surfaces as `ClerkConfigurationError` with an
  actionable message instead of an ImportError at Django startup.
- **Stayed bearer-only.** The SDK also reads a `__session` cookie. Accepting a
  cookie is a new authentication mechanism with CSRF implications, not
  compatibility work, so it is deliberately not ported.
- **The empty-allowlist normalization from #5 is preserved** in the new call
  path: `_get_auth_parties() or None`, because an empty list would be an
  allowlist matching nothing.

## Verification

- `uv run python -m pytest tests/test_clerk_api_tokens.py -q` — 44 passed.
- `uv run python -m pytest -q` — 545 passed, 28 skipped.
- `uv build` + `uv run python scripts/check_dist.py` — artifacts validated.
- `uv run pre-commit run --files <touched files>` — clean.
- All tokens are minted locally from a generated RSA keypair and the JWKS
  endpoint is served through `httpx.MockTransport`, so the suite runs fully
  offline with no live credentials, as the request required.
- **The headline outcome is directly tested.**
  `test_verification_works_with_the_sdk_uninstalled` blocks every
  `clerk_backend_api` import, drops the relevant modules from `sys.modules`,
  re-imports them under that constraint, and verifies a token successfully.
  It also asserts the SDK path then fails with `ClerkConfigurationError`
  naming `clerk-backend-api` rather than an ImportError.
- Coverage includes: networkless and remote paths, JWKS caching, key rotation
  (success and bounded-failure), unknown `kid`, malformed JWKS, expired /
  not-yet-active tokens, azp allowlist accept/reject/missing/skip, HS256
  algorithm-confusion rejection, v1 passthrough, v2 enrichment, and every
  defensive branch in the permission bitmask expansion.
- `test_without_enrichment_request_org_would_be_none` is a negative control
  pinning the exact bug the enrichment exists to prevent.

### Existing tests that required updating

Four `test_authentication.py` tests mocked `get_clerk_client` and set
`clerk.authenticate_request.return_value`; they now patch
`authenticate_session_token` and return a `RequestState`. They also needed a
usable `CLERK_SECRET_KEY`: `tests/settings.py` uses
`sk_test_mock_secret_key`, which is one of the documented placeholder sentinels
that `get_configured_clerk_secret_key` treats as unconfigured, so the new
config guard correctly short-circuited before verification ran. One
`test_server_api.py` test patched `django_clerk_users.client.Clerk`, which no
longer exists at module scope, and now patches `clerk_backend_api.Clerk`.

## Delivered result

Session tokens now verify without `clerk-backend-api` installed. New module
`clerk_api/tokens.py` provides `verify_session_token`,
`authenticate_session_token`, `RequestState`, `enrich_v2_org_claims`, and
`compute_org_permissions`.

`request.org` now resolves for v2 tokens. Previously `middleware/auth.py`
(three sites) and `authentication/drf.py` all read the flat `org_id` key, which
v2 tokens do not carry, so the active organization was `None` for every v2
token. This is the one user-visible behavior change in the request.

Module-level SDK imports are gone from `authentication/utils.py` and
`client.py`. `CLERK_JWT_KEY` is new and documented in the README settings
table.

Follow-up: #9 hardens verification beyond this parity port (the broad
`except Exception` in `get_clerk_payload_from_request` is still there, and
issuer verification is still disabled via `verify_iss: False`, both inherited
from the SDK). #7 and #10 continue the decoupling; `clerk-backend-api` is still
a hard dependency in `pyproject.toml` because `server_api` still needs it.
