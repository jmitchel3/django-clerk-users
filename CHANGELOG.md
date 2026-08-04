# Changelog

All notable changes to `django-clerk-users` are documented here.

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
