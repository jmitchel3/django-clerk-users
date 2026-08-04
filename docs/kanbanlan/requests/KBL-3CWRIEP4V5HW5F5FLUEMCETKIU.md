# Reach 100% coverage: authentication boundaries batch

- Kanbanlan: `KBL-3CWRIEP4V5HW5F5FLUEMCETKIU`
- Canonical home: `github`
- Canonical request: [#26](https://github.com/jmitchel3/django-clerk-users/issues/26)

## Request

Outcome: raise verified statement and branch coverage to 100% for five authentication-boundary modules and correct the prior durable remaining-module count. Scope: (1) authentication/utils.py; (2) authentication/drf.py; (3) middleware/auth.py; (4) checks.py; (5) testing.py; (6) correct KBL-YCWJ2DCYZRAXTPRXBEAMCDWBL4 follow-up count from eight to eleven remaining modules. Acceptance: each scoped module reports 100% statements and branches under repository coverage configuration; tests exercise meaningful request, token, configuration, optional-DRF, and testing-helper paths; targeted and full suites pass; durable verification is recorded.

## Decisions

- Keep the batch test-only. Every missed statement and partial branch was
  reachable defensive or compatibility behavior, so no production exclusions
  or source changes were needed.
- Cover the optional DRF success import in the dependency-light base
  environment by executing the module with a minimal in-memory
  `rest_framework` stand-in. This verifies both dependency states without
  making DRF a required installation.
- Test authentication boundaries at their public effects: token and setting
  normalization, cache and verification fallbacks, request payload propagation,
  middleware session rotation, system-check traversal, and testing-client
  lifecycle behavior.
- Correct the preceding iteration's historical remaining-module count from
  eight to eleven; this iteration then reduces the live remainder to six.

## Verification

- Scoped branch coverage:
  `uv run coverage run --branch -m pytest -q tests/test_authentication.py tests/test_drf_combined.py tests/test_middleware.py tests/test_checks.py tests/test_testing.py`
  — 160 passed; all five modules report 100%, totaling 597 statements and 190
  branches with zero misses or partial branches.
- Full branch coverage: `uv run coverage run --branch -m pytest -q` — 787
  passed, 28 skipped; repository coverage increased from 86.61% to 91.58%
  (displayed as 92%).
- Remaining missed statements fell from 382 to 243; partial branches fell from
  126 to 84.
- `uv run ruff check` on all five changed test files — passed.
- `uv run ruff format --check` on all five changed test files — passed.
- Optional dependency matrix: `uv run tox run -e py312-django52-drf` — 31
  passed with DRF installed.
- `git diff --check` — passed.

## Delivered result

Added 65 tests across the authentication utility, optional DRF, middleware,
system-check, and testing-helper suites. Production source remains unchanged,
and each of the five scoped modules now has complete statement and branch
coverage.

The repository-wide 100% objective remains active. The remaining gaps are
concentrated in six modules: the three management commands, webhook handlers,
organization webhooks, and the server API compatibility layer.
