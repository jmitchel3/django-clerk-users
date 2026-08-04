# Reach 100% coverage: foundational modules batch

- Kanbanlan: `KBL-YD7DZOSY2FGLZKDMYIJ66ODNRU`
- Canonical home: `github`
- Canonical request: [#20](https://github.com/jmitchel3/django-clerk-users/issues/20)

## Request

Outcome: raise verified line and branch coverage to 100% for a coherent batch
of foundational django-clerk-users modules without changing intended production
behavior.

Scope:

1. `src/django_clerk_users/__init__.py`
2. `src/django_clerk_users/authentication/__init__.py`
3. `src/django_clerk_users/settings.py`
4. `src/django_clerk_users/exceptions.py`
5. `src/django_clerk_users/clerk_api/objects.py`
6. `src/django_clerk_users/client.py`
7. `src/django_clerk_users/caching.py`

Acceptance:

- Each scoped module reports 100% statements and branches under the repository
  coverage configuration.
- Tests cover meaningful success, fallback, lazy-import, and error paths rather
  than excluding reachable code.
- The targeted suite and full suite pass.
- Durable verification and delivered results are recorded in this file.

## Decisions

- Keep the iteration test-only. Every reported gap is reachable compatibility,
  fallback, normalization, or cache behavior; no production exclusion or source
  change is needed.
- Exercise package metadata and optional-DRF fallback imports with `runpy` under
  controlled import failures. This covers the real module initialization paths
  without mutating global import state outside each test.
- Test all names in the package `__all__` contract so future public exports
  cannot be declared without resolving through the lazy facade.
- Cover environment-shaped inputs explicitly: bytes, invalid Unicode, empty
  values, wrong types, normalized strings, and configured optional dependencies.

## Verification

- Targeted tests:
  `uv run python -m pytest tests/test_import.py tests/test_clerk_api_client.py tests/test_client_backend.py tests/test_caching.py -q`
  — 130 passed, 1 skipped.
- Scoped branch coverage: all seven modules report 100.00%, totaling 344
  statements and 104 branches with zero misses or partial branches.
- Full branch coverage:
  `COVERAGE_FILE=<temp>/.coverage uv run coverage run -m pytest -q -p no:cacheprovider`
  — 689 passed, 28 skipped; repository total increased from 82.70% to 84.74%.
- `uv run ruff check` on all four changed test files — passed.
- `uv run ruff format --check` on all four changed test files — passed.
- `git diff --check` — passed.

## Delivered result

Added 36 tests across the existing import, client, response-object, and caching
suites. The tests close every statement and branch gap in the seven scoped
modules while preserving production code unchanged.

The repository-wide 100% coverage objective remains in progress; later grouped
Kanbanlan requests will cover the remaining modules.
