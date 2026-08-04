# Reach 100% coverage: near-complete modules batch

- Kanbanlan: `KBL-YCWJ2DCYZRAXTPRXBEAMCDWBL4`
- Canonical home: `github`
- Canonical request: [#24](https://github.com/jmitchel3/django-clerk-users/issues/24)

## Request

Outcome: raise verified statement and branch coverage to 100% for ten
near-complete modules without changing intended production behavior.

Scope:

1. `src/django_clerk_users/managers.py`
2. `src/django_clerk_users/migrations/0005_*.py`
3. `src/django_clerk_users/organizations/migrations/0002_*.py`
4. `src/django_clerk_users/webhooks/views.py`
5. `src/django_clerk_users/clerk_api/transport.py`
6. `src/django_clerk_users/clerk_api/resources.py`
7. `src/django_clerk_users/organizations/models.py`
8. `src/django_clerk_users/utils.py`
9. `src/django_clerk_users/webhooks/security.py`
10. `src/django_clerk_users/clerk_api/tokens.py`

Acceptance:

- Every scoped module reports 100% statements and branches under the repository
  coverage configuration.
- Tests exercise meaningful success, fallback, validation, and error paths.
- Targeted and full suites pass.
- Durable verification is recorded in this file.

## Decisions

- Keep the batch test-only. All 48 missed statements and 30 partial branches
  were reachable behavior; no source exclusions or production changes were
  needed.
- Group modules by coverage maturity rather than create a card per small gap.
  This closes ten independently listed items in one reviewable iteration.
- Exercise rare bounded fallbacks directly: repeated UUID collisions, username
  retry exhaustion, stale and negative JWKS cache entries, invalid JWT claim
  types, shared HTTP client ownership, and webhook verifier exceptions.
- Preserve behavior at compatibility boundaries, including raw negative-cache
  sentinels and local username durability when remote synchronization fails.

## Verification

- Scoped tests:
  `uv run python -m pytest tests/test_auto_username.py tests/test_models.py tests/test_migrations.py tests/test_webhook_views.py tests/test_clerk_api_client.py tests/test_clerk_api_resources.py tests/test_organizations.py tests/test_utils.py tests/test_webhooks.py tests/test_clerk_api_tokens.py tests/test_clerk_api_token_hardening.py -q`
  — 415 passed.
- Scoped branch coverage: all ten modules report 100.00%, totaling 926
  statements and 258 branches with zero misses or partial branches.
- Full branch coverage:
  `COVERAGE_FILE=<temp>/.coverage uv run coverage run -m pytest -q -p no:cacheprovider`
  — 722 passed, 28 skipped; repository coverage increased from 84.74% to
  86.61%.
- Remaining missed statements fell from 430 to 382; partial branches fell from
  156 to 126.
- `uv run ruff check` on all nine changed test files — passed.
- `uv run ruff format --check` on all nine changed test files — passed.
- `git diff --check` — passed.

## Delivered result

Added 33 tests across the existing manager, migration, thin-client, token,
organization, utility, and webhook suites. Production source remains unchanged,
and each of the ten scoped modules now has complete statement and branch
coverage.

The repository-wide 100% objective remains active. The remaining gaps are
concentrated in eleven larger modules and will be handled by later grouped
Kanbanlan requests.
