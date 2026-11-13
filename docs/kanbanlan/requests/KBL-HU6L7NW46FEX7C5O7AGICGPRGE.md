# fix: reject empty Authorization headers in strict hybrid auth recipe

- Kanbanlan: `KBL-HU6L7NW46FEX7C5O7AGICGPRGE`
- Canonical home: `github`
- Canonical request: [#46](https://github.com/jmitchel3/django-clerk-users/issues/46)

## Request

The strict hybrid authentication recipe treats supplied empty or whitespace-only Authorization headers as absent and authenticates using a session cookie, contrary to its documented strict policy. Use header presence to select fallback, reject empty supplied values, update the embedded documentation, and cover valid-cookie GET and CSRF-valid POST cases. Scope: hybrid recipe source and Markdown, tests/test_drf_hybrid_recipe.py. Deliver in v0.5.1.

## Decisions

- The strict recipe chooses session fallback only when the Authorization header
  is absent. A supplied empty or whitespace-only value goes through the existing
  malformed-credentials rejection, matching the documented strict policy.
- The copyable Python module and its embedded Markdown remain identical. The
  precedence table explicitly describes empty and whitespace-only headers.

## Verification

- Added six real DRF cases: empty, space-only, and tab-containing whitespace
  headers on GET and CSRF-valid POST requests carrying a valid session cookie.
  All six returned HTTP 200 before the fix and HTTP 401 afterwards, with the
  expected `WWW-Authenticate: Bearer` challenge.
- `tests/test_drf_hybrid_recipe.py`, `tests/test_drf.py`, and
  `tests/test_drf_combined.py`: 62 passed under Python 3.12 / Django 5.2 / DRF.
  Existing tests retain absent-header session fallback and CSRF enforcement.
- Ruff lint and format checks passed for the changed Python files;
  `git diff --check` passed.

## Delivered result

The strict hybrid authentication recipe now rejects supplied empty Authorization
headers instead of silently authenticating the session user. Included in the
v0.5.1 release work; versioning and publication are tracked separately in #47.
