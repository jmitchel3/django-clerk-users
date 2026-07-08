# Changelog

All notable changes to `django-clerk-users` are documented here.

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
