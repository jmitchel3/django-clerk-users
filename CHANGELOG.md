# Changelog

All notable changes to `django-clerk-users` are documented here.

## Unreleased

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
