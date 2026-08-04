# Harden session token verification beyond SDK parity

- Kanbanlan: `KBL-4Y724KJNOBEQ5N4HMEXRVVKSAE`
- Canonical home: `github`
- Canonical request: [#9](https://github.com/jmitchel3/django-clerk-users/issues/9)

## Request

Outcome: deliberate, documented hardening on top of the ported verification path.

Items, each needing a changelog entry and a test because each is a behaviour change rather than a refactor:
- Reject machine token prefixes (ak_, oat_, m2m_, mt_) before any network call.
- Negative-cache unresolved kids so unknown-kid traffic cannot amplify into outbound requests.
- Require sub, sid, and exp, since PyJWT only validates claims that are present.
- For v2 tokens always overwrite or clear the flat org_ fields, so a signed custom claim cannot survive when the o claim is absent.
- Single-flight locking around JWKS fetches and a strict timeout.

Depends on the verification port.

## Decisions

All five requested items are implemented. Each got a changelog entry and tests,
as the request required, because each changes behavior relative to the SDK.

- **v2 org claims: clear, do not just skip.** The SDK's `_process_payload`
  returns early when there is no `o` claim, leaving any flat `org_id` in the
  token untouched. A v2 token is not supposed to carry one, but Clerk instances
  can add custom claims, so a token with a hand-set `org_id` and no active
  organization would have been reported as scoped to that organization.
  `request.org` is what org-scoped tenancy keys off, so this is a privilege
  boundary. The flat fields are now derived solely from `o`. `org_permissions`
  is set to `[]` rather than left absent, so a forged list cannot survive
  either.
  v1 tokens legitimately carry flat claims and are explicitly untouched.
- **Machine tokens are rejected on prefix, before the JWKS fetch.** They could
  never have verified as RS256 JWTs, so the only thing the old path bought was
  an outbound request per bad token. The check strips surrounding whitespace so
  padding cannot bypass it.
- **Required claims are enforced through PyJWT's own `require` option** rather
  than a post-decode check, so the failure comes from the library's validated
  path.
- **Negative cache TTL is 30s, deliberately much shorter than the 300s positive
  TTL.** It has to be long enough to blunt amplification but short enough that
  a newly rotated signing key becomes usable quickly. An explicit eviction (the
  rotation path) clears the negative entry too, so rotation is never blocked by
  it.
- **Single-flight holds the lock across the fetch and re-checks the cache
  inside it.** Without the re-check, every thread queued on the lock would
  still issue its own request once it acquired the lock. The negative cache is
  re-checked inside the lock for the same reason.
- **The JWKS timeout is a ceiling, not an override.** A caller passing a
  shorter `timeout_ms` still gets the shorter value; only longer values are
  clamped. A 3s ceiling suits an inline authentication-path call.

## Verification

- `uv run python -m pytest tests/test_clerk_api_token_hardening.py -q` — 29 passed.
- `uv run python -m pytest -q` — 647 passed, 28 skipped.
- `uv run pre-commit run --files <touched files>` — clean.

### Mutation check on the single-flight tests

Concurrency tests can pass for the wrong reason, so the lock was neutralized
(replaced with `contextlib.nullcontext()`) and the tests rerun. Both concurrency
tests failed with `assert 4 == 1`, showing four real JWKS requests where the
locked version makes one. The lock was then restored. This confirms the tests
exercise single-flight rather than being satisfied by timing luck.

### Coverage per item

- Machine tokens: parametrized over all four prefixes, including an assertion
  that **zero** JWKS requests are made, plus a whitespace-padding case.
- Required claims: parametrized over `sub`/`sid`/`exp`. The `exp` case first
  asserts that bare PyJWT *accepts* the token, so the test demonstrates the gap
  being closed rather than just a rejection.
- v2 forgery: custom `org_id` cleared with no `o`, overwritten with `o`, slug /
  role / permissions all cleared, forged permissions replaced by the computed
  set, and v1 left alone.
- Negative caching: 5 attempts produce 1 request; the entry expires; a
  resolvable kid is not negative-cached; rotation is not blocked by it.
- Single-flight and timeout: 4 concurrent threads produce 1 request for both
  the resolvable and unknown-kid cases, the strict ceiling is applied, a longer
  caller timeout is clamped, and a shorter one wins.

## Delivered result

Session token verification now applies five deliberate hardening measures on
top of the SDK-parity port. The module docstring was updated: it previously
said hardening was tracked separately, which is no longer true.

The v2 org claim change is the one with a security consequence, and it is the
only one that can change the payload seen by an existing valid token: a v2
token carrying custom flat `org_*` claims will now see them cleared or
overwritten. Any deployment relying on custom flat org claims in v2 tokens
should read `payload["o"]` instead.

No follow-up work remains. This closes the 0.4.0 decoupling series.
