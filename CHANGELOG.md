# Changelog

All notable changes to `django-clerk-users` are documented here.

## 0.4.0 - 2026-08-04

### Security and hardening

Each of these is a behavior change relative to the Clerk SDK's verification
semantics, not a refactor.

- **v2 org claims can no longer be forged.** On a v2 token the flat `org_id`,
  `org_slug`, `org_role`, and `org_permissions` fields are now always derived
  from the nested `o` claim, and cleared when `o` is absent. Previously a v2
  token carrying a custom flat `org_id` and no active organization kept that
  value, and `request.org` is what org-scoped tenancy keys off. v1 tokens,
  which legitimately carry flat claims, are unaffected.
- **Machine tokens are rejected before any network call.** Tokens beginning
  `ak_`, `oat_`, `m2m_`, or `mt_` are API keys, OAuth access tokens, or
  machine-to-machine tokens. They are verified through Clerk's API rather than
  as RS256 JWTs, so they could never authenticate a session; they now fail
  immediately instead of costing a JWKS request first.
- **`sub`, `sid`, and `exp` are now required.** PyJWT validates only the claims
  a token actually contains, so a token omitting `exp` was never checked for
  expiry. Their absence is now a rejection.
- **Unresolvable `kid` values are negative-cached** for 30 seconds, so traffic
  bearing an unknown `kid` can no longer amplify into one outbound JWKS request
  per inbound request. The window is short so a newly rotated signing key
  becomes usable quickly, and an explicit rotation eviction clears it.
- **JWKS fetches are single-flighted and get a strict 3 second timeout.**
  Concurrent misses for the same `kid` now share one request instead of issuing
  one each, and this inline authentication-path call fails fast rather than
  inheriting the longer general Clerk API timeout. A shorter caller-supplied
  timeout still wins.

### Breaking

- **`clerk-backend-api` moved to an optional `[sdk]` extra and is no longer
  installed by default.** It pins `cryptography>=45,<49`, and that pin is what
  resolvers obey, so every default install was held to `cryptography` 48.x
  while 50.x was current. A base install now resolves `cryptography` 50.x.

  Server-side Clerk API calls use a new built-in thin REST client by default.
  If you need the official SDK, install `django-clerk-users[sdk]` **and** set
  `CLERK_CLIENT_BACKEND = "sdk"`.

  Installing the extra alone is deliberately not enough. Selection is by
  setting only, never by importability: `get_clerk_client()` is public API, and
  choosing an implementation based on what happens to be installed would make
  response models, error types, retries, and available methods depend on the
  environment, and would silently restore the `cryptography` ceiling for anyone
  who picked up `clerk-backend-api` transitively. Selecting `"sdk"` without the
  extra installed raises `ClerkConfigurationError` rather than falling back.

  Session token verification does not use the SDK on either backend.

- Added a `NOTICE` file recording MIT attribution for the verification and org
  claim logic ported from `clerk-backend-api` 6.0.1.

### Other changes

- Fixed `revoke_clerk_user_sessions` silently leaving sessions active when a
  user had more than one page of them. The listing call sent no `limit` or
  `offset` and ran no pagination loop, so only the Clerk API's default first
  page was ever revoked. Listing now walks every page before any revoke runs,
  which also keeps the `status="active"` window from shifting under the offset
  cursor mid-loop. The loop is bounded by `CLERK_SESSION_LIST_MAX_PAGES`.
- Fixed token verification failing outright when neither `CLERK_FRONTEND_HOSTS`
  nor `CLERK_AUTH_PARTIES` was set. `options=None` was passed to the Clerk SDK,
  which reads `options.secret_key` unconditionally, so every request raised an
  `AttributeError` that surfaced as a generic token validation error. An options
  object is now always constructed. An empty allowlist is normalized to `None`
  rather than `[]`, because the SDK skips the `azp` check only for `None` and
  would treat an empty list as an allowlist matching nothing.
- Added `django_clerk_users.clerk_api.ClerkClient`, a thin REST client covering
  all 18 Clerk operations this package consumes, plus a `paginate()` helper for
  list endpoints. It mirrors the SDK's resource attribute names and argument
  styles, so it can be passed as `clerk_client=` anywhere the SDK client was
  expected. Nothing is cut over to it yet, so no runtime behavior changes.
- **Fixed `request.org` being `None` for every v2 session token.** v2 tokens
  carry the active organization in a nested `o` claim rather than a top-level
  `org_id`, but `ClerkAuthMiddleware` and the DRF authentication classes all
  read the flat key. The flat org claims (`org_id`, `org_slug`, `org_role`, and
  `org_permissions`) are now synthesised from `o` for v2 tokens. v1 tokens are
  unchanged.
- Session tokens now verify without `clerk-backend-api` installed. Verification
  moved to `django_clerk_users.clerk_api.tokens`, which does RS256 against the
  authenticated JWKS endpoint with a bounded single refresh for key rotation.
  Semantics are a deliberate port of the SDK's, so the set of accepted tokens
  is unchanged.
- Added `CLERK_JWT_KEY` for fully networkless verification against a static PEM
  public key, skipping the JWKS request entirely.
- `clerk-backend-api` is no longer imported at module scope. It is imported
  lazily when a server API call needs it, and a missing install now raises
  `ClerkConfigurationError` with an actionable message instead of failing at
  Django startup.
- Declared `pyjwt` as a direct dependency. It is the same library the Clerk SDK
  uses internally; it just no longer arrives as a transitive.
- Added `django_clerk_users.clerk_api`, a thin Clerk HTTP client core: a
  recursive `ClerkObject` response type that is both attribute-accessible and a
  `Mapping`, and a `ClerkTransport` built on httpx that honours `timeout_ms`.
  This is the foundation for decoupling from `clerk-backend-api` and is not yet
  wired into any call site, so no runtime behavior changes.
- `ClerkAPIError` now carries `status_code` and a structured `data` body, so
  callers can branch on Clerk error codes (`exc.data.errors[0].code`,
  `.meta.param_names`) without depending on SDK types. Constructing it with only
  a message is unchanged.
- Declared `httpx` as a direct dependency instead of relying on it arriving
  transitively through `svix`.

## 0.3.4 - 2026-08-03

- Declared `cryptography>=45` with no upper bound so the package tracks new
  `cryptography` releases instead of being held to a pinned version. A release
  test now fails if anything reintroduces an upper bound.
- Raised the `clerk-backend-api` floor to `>=6.0.1`, which lifts that SDK's own
  `cryptography` ceiling from `<46` to `<49` and lets resolvers pick up newer
  releases. `cryptography` 50 is verified working against the test suite but is
  still capped by the `clerk-backend-api` upper bound, which this package does
  not control.
- Added `scripts/check_cryptography_ceiling.py` and a scheduled
  `Cryptography Watch` workflow that reports where the upstream ceiling sits
  and fails once it lifts, so the `clerk-backend-api` floor can be raised
  promptly.
- Added a `py313-cryptolatest` tox environment that runs the suite against the
  newest `cryptography` regardless of the upstream cap.
- Added `timeout-minutes` to every GitHub Actions job so a hung runner cannot
  burn the full six-hour default.
- Pinned `ruff` to the 0.14 line for now; 0.15 widened its default rule set and
  that lint expansion needs its own change.

## 0.3.3 - 2026-07-18

- Exposed the active Clerk organization id as `request.org` from the DRF
  `ClerkAuthentication` class, mirroring what `ClerkAuthMiddleware` sets on the
  WSGI path. Previously the active organization was only available when using
  the WSGI auth middleware, so DRF-authenticated (bearer-token) requests had no
  way to resolve the tenant/organization without extra wiring. The id is also
  set on the underlying Django `HttpRequest` so middleware and non-DRF
  consumers can read it.

## 0.3.2 - 2026-07-08

- Fixed the release workflow so publishing is not blocked when optional live
  Clerk smoke-test credentials are not configured in the release environment.
- Added production release checks for built artifacts, installed wheels, and
  read-only live Clerk smoke validation.
- Updated package metadata from beta to production/stable.
- Added author and keyword metadata and removed the misleading Funding URL.
- Expanded CI to cover Python 3.12 through 3.14 and Django 4.2, 5.2, and 6.0.
- Added optional organization webhook handling, webhook deduplication, and
  endpoint-specific Svix signing secret support.
- Hardened webhook routers so handler failures are reported as processing
  failures instead of silent successes.
- Hardened session authentication, Clerk API helpers, cache timeout parsing,
  placeholder secret handling, admin registration, and management command
  failure behavior.
- Hardened environment-style configuration parsing for comma-separated host
  lists, numeric timeouts, boolean password-sync flags, and trimmed secrets.
- Hardened environment-style parsing for the synchronous username generation
  flag.
- Rejected invalid-looking Clerk API and Svix webhook secret prefixes before
  constructing SDK clients.
- Hardened byte-string setting normalization so invalid bytes do not crash
  startup, authentication, webhook verification, or Django system checks.
- Hardened first-login Clerk user synchronization against concurrent
  `clerk_id` creation races.
- Enforced database uniqueness for public user and organization UUIDs, repaired
  duplicate UUIDs during migration, and removed redundant duplicate indexes from
  the bundled models.
- Normalized webhook signing secrets consistently across runtime verification
  and the live smoke-check script.
- Added Django system checks for placeholder Clerk secrets, DRF-only Clerk auth,
  missing frontend host allowlists, and middleware ordering mistakes.
- Added a `py.typed` marker so type checkers can consume the package's inline
  typing information.
- Added Django REST Framework session/bearer hybrid authentication support.
- Added server-side Clerk helpers for user provisioning, sign-in links,
  invitations, session revocation, and metadata/email sync workflows.
