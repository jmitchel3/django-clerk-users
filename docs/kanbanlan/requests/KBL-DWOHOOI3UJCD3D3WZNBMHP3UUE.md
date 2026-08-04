# Add thin Clerk HTTP client core: response objects, error type, transport

- Kanbanlan: `KBL-DWOHOOI3UJCD3D3WZNBMHP3UUE`
- Canonical home: `github`
- Canonical request: [#6](https://github.com/jmitchel3/django-clerk-users/issues/6)

## Request

Outcome: a thin Clerk client foundation that existing call sites can consume unchanged.

Scope:
- Recursive attribute-access response objects. Nested email_addresses entries and public_user_data must be attribute-accessible, because getattr on a plain dict returns the default and would silently break the sync commands and update_or_create_clerk_user.
- A stable error type exposing status_code plus structured .data.errors carrying .code and .meta.param_names, so duplicate detection at server_api.py:118 keeps working without SDK types.
- httpx transport honouring timeout_ms, with httpx declared as a direct dependency rather than relying on the svix transitive.

Verified with an httpx MockTransport suite that exercises attribute access through real call sites, not just the wire shape.

First step of the clerk-backend-api decoupling for 0.4.0.

## Decisions

- **`ClerkObject` is both attribute-accessible and a real `Mapping`.** The
  request only required attribute access, but making it a `Mapping` as well is
  what lets the existing helpers keep working untouched. `server_api._get_value`
  and `server_api._plain_data` both branch on `isinstance(value, Mapping)`
  first, and `organizations/webhooks.py:226` calls `.get("public_user_data")`.
  An attribute-only object would have forced edits at all of those call sites.
- **Conversion happens on access, not eagerly.** Decoding a 100-item list
  response does not walk every nested branch up front.
- **Known limitation, documented in the class docstring:** real attributes win
  over data keys, so a response field named `get`, `keys`, `items`, or `values`
  is reachable only by subscripting. `__getattr__` fires only after normal
  lookup fails. Clerk returns no such fields today.
- **`ClerkObject` is read-only.** `__setattr__` and `__delattr__` raise. These
  are decoded API responses; silent local mutation would be a bug source.
- **`model_dump` is implemented for SDK parity** even though `_plain_data`
  reaches the `Mapping` branch before its `model_dump` branch. It keeps the
  object drop-in compatible for any caller that reaches for the pydantic API.
- **Extended the existing `ClerkAPIError` rather than adding a new type.**
  `utils.py:358` already raises it with a bare message, and it is already
  exported from the package root. The signature keeps message-only construction
  working; `status_code`, `data`, and `response` are keyword-only additions.
- **`_coerce_error_data` guarantees `.data.errors` is always present**, even for
  an empty body or a non-JSON error page (an HTML gateway error is stored under
  `data.raw`). Without that, `server_api._clerk_errors` would need a None guard.
- **Non-JSON error bodies are preserved, not discarded**, so a 502 HTML page
  reaches the exception message instead of surfacing as an empty error.
- **`httpx` declared as a direct dependency** rather than leaning on the `svix`
  transitive, as the request specified. `svix` is expected to become droppable.

## Verification

- `uv run python -m pytest tests/test_clerk_api_client.py -q` — 32 passed.
- `uv run python -m pytest -q` — 501 passed, 28 skipped (469 pre-existing + 32).
- `uv run pre-commit run --files <the six touched files>` — clean.
- The suite uses `httpx.MockTransport` and, as the request required, exercises
  attribute access **through the real call sites** rather than only asserting
  the wire shape. `TestRealCallSitesAgainstDecodedResponses` drives:
  - `server_api._list_data` / `_get_value` / `_plain_data`
  - the verbatim `getattr` chain from `utils.update_or_create_clerk_user`
  - the `getattr` chain from the `sync_clerk_users` command
  - the `public_user_data` chain from `sync_clerk_organizations`
- `test_public_user_data_as_plain_dict_would_have_failed` is a deliberate
  negative control: it asserts that a plain dict returns the `getattr` default,
  pinning *why* `ClerkObject` exists rather than decoding straight to dicts.
- `TestErrorType::test_duplicate_identifier_detection_still_works` drives the
  real `server_api._has_duplicate_identifier_error` and `_duplicate_error_params`
  against a `ClerkAPIError`, confirming the `server_api.py:118` duplicate
  detection keeps working without SDK types.

## Delivered result

New `src/django_clerk_users/clerk_api/` package with the three pieces the
request scoped:

- `objects.py` — `ClerkObject`, `clerk_value`, `to_plain_data`.
- `transport.py` — `ClerkTransport`, an httpx transport honouring `timeout_ms`
  with the same setting-fallback semantics as `server_api._timeout_options`.
- Error type extended in `exceptions.py` (`ClerkAPIError` now carries
  `status_code`, `data`, `response`, and an `errors` shortcut).

Nothing is wired into the existing call sites yet, by design. This is the
foundation only, so no runtime behavior changes in this request. `clerk_api`
is additive and `clerk-backend-api` remains the live path.

Note: editing `pyproject.toml` to add `httpx` caused `pyproject-fmt` to also
reorder `keywords`/`requires-python` and normalize `django>=4.2,<7.0` to
`django>=4.2,<7`. Those are formatter normalizations of pre-existing content,
semantically identical, not intentional dependency changes.

Follow-up, already tracked: #7 builds the REST resources on this core, #8 ports
session token verification, and #10 makes `clerk-backend-api` optional. The
`clerk-backend-api` dependency is deliberately untouched here.
