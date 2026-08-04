# Reach repository-wide 100% coverage: final integration batch

- Kanbanlan: `KBL-YQNOIDPE6ZE2BER2C75JEQI5JI`
- Canonical home: `github`
- Canonical request: [#30](https://github.com/jmitchel3/django-clerk-users/issues/30)

## Request

Outcome: reach verified repository-wide 100% statement and branch coverage by closing the final two module gaps. Scope: (1) organizations/webhooks.py; (2) server_api.py. Acceptance: both scoped modules and the full src/django_clerk_users package report 100% statements and branches under repository coverage configuration; tests exercise meaningful organization lifecycle, membership/invitation, pagination, compatibility, normalization, duplicate-error, and fallback paths; targeted and full suites pass; durable verification is recorded.

## Decisions

- Keep the final batch test-only. Every remaining path was reachable lifecycle,
  normalization, retry, or compatibility behavior; no production exclusions or
  source changes were needed.
- Exercise organization webhooks through their transactional handlers, covering
  absent identifiers, payload-only and API-assisted organization resolution,
  missing related records, user synchronization, signal-producing success
  paths, and caught persistence failures.
- Test the server API at its stable wrapper contract while directly covering
  small normalization and structured-error helpers. This preserves SDK
  independence while verifying model-dump, plain-object, mapping, tuple, and
  opaque response shapes.
- Require the final repository report itself to pass `--fail-under=100`, rather
  than inferring completion from the two scoped reports.

## Verification

- Scoped branch coverage:
  `uv run coverage run --branch -m pytest -q tests/test_organization_webhooks.py tests/test_server_api.py`
  — 71 passed; both modules report 100%, totaling 562 statements and 188
  branches with zero misses or partial branches.
- Full branch coverage: `uv run coverage run --branch -m pytest -q` — 849
  passed, 28 skipped.
- Enforced repository report: `uv run coverage report --show-missing --fail-under=100`
  — 3,245 of 3,245 statements and 922 of 922 branches covered; zero missed
  statements and zero partial branches.
- Repository coverage increased from 95.10% to 100.00% in this iteration and
  from the initiative baseline of 82.70% to 100.00% overall.
- `uv run ruff check` on both changed test files — passed.
- `uv run ruff format --check` on both changed test files — passed.
- `git diff --check` — passed.

## Delivered result

Added 31 tests across the organization-webhook and server-API suites.
Production source remains unchanged, both final modules now have complete
statement and branch coverage, and the entire `src/django_clerk_users` package
meets the repository-wide 100% coverage objective.
