# Make clerk-backend-api optional behind explicit backend selection

- Kanbanlan: `KBL-3SCB22V2IBF4LHURIBXQVGP6NQ`
- Canonical home: `github`
- Canonical request: [#10](https://github.com/jmitchel3/django-clerk-users/issues/10)

## Request

Outcome: default installs are free of the clerk-backend-api cryptography ceiling.

clerk-backend-api 6.0.1 pins cryptography>=45,<49, and that pin is what resolvers obey, so users get 48.x while 50.x is current. This package declares no upper bound of its own, and no other dependency constrains cryptography.

Scope:
- Thin client is the default and only required path. Move clerk-backend-api to an [sdk] extra.
- Opt in via an explicit CLERK_CLIENT_BACKEND setting, never by mere importability. get_clerk_client() is public API (__init__.py:31); switching implementations based on what happens to be installed makes models, errors, retries, and available methods environment-dependent, and silently restores the cap for anyone who picks up the SDK transitively.
- MIT attribution for ported logic, recording the upstream version it came from.
- README and CHANGELOG updates.
- CI covering both base and [sdk] installs, with the existing cryptolatest env passing on a base install.

Final step of the 0.4.0 decoupling.

## Decisions

- **Selection is by setting only, never by importability**, exactly as the
  request specified. `get_clerk_client_backend()` reads `CLERK_CLIENT_BACKEND`
  and nothing else. Installing the `[sdk]` extra is deliberately *not* enough
  to change behavior; you must also set the backend. The reasoning is in the
  request and is reproduced in the function docstring and README so it survives
  the next person's "why doesn't this auto-detect?" instinct.
- **An unrecognized backend value raises rather than falling back.** A silent
  fallback to thin would hide a typo like `CLERK_CLIENT_BACKEND = "SDK "` on a
  deployment that genuinely needs the SDK. The value is normalized for case and
  whitespace first, so only genuinely unknown names raise.
- **Selecting `"sdk"` without the extra installed raises** with an actionable
  message naming both fixes. Falling back to thin would defeat the point of an
  explicit setting.
- **`clerk-backend-api` stays in the dev dependency group.** It is no longer a
  runtime dependency, but the suite must be able to exercise the SDK backend.
  Tests that need it use `pytest.importorskip`, so the same suite passes on a
  base install (3 extra skips) and on an `[sdk]` install.
- **`check_dist.py` gained an explicit forbidden-entry check.** Its existing
  allowlist only detects *missing* metadata, so an accidental re-add of
  `clerk-backend-api` to `dependencies` would have passed silently while
  restoring the ceiling for every user. The new check fails on any
  `Requires-Dist: clerk-backend-api` without an `extra ==` marker.
- **Attribution lives in a top-level `NOTICE`** rather than being appended to
  `LICENSE`, so this package's own MIT grant stays unambiguous. It records the
  upstream project, version 6.0.1, source URL, license, and the specific ported
  functions. `clerk_api/tokens.py` carries a pointer to it.
- **CI covers both install shapes as a real wheel install**, not a `uv sync`
  variation, because the property under test is what a resolver does for an end
  user. Each shape asserts `clerk-backend-api` presence matches expectation, so
  a leak into the base install fails loudly rather than silently passing.
- **`cryptolatest` runs as its own base-install job.** That is the request's
  acceptance criterion and it now means something: with no SDK, nothing caps
  `cryptography`.

## Verification

- `uv run python -m pytest -q` (dev env, SDK installed) — 618 passed, 28
  skipped.
- **Base install, built wheel, no SDK** — 615 passed, 31 skipped. The 3 extra
  skips are the `importorskip`-guarded SDK-backend tests.
- `uv build` + `uv run python scripts/check_dist.py` — validated.
- `uv run pre-commit run --files <touched files>` — clean.

### The measurement that proves the outcome

Built the wheel and installed it two ways in clean venvs:

| Install | `clerk_backend_api` present | resolved `cryptography` |
| --- | --- | --- |
| `django_clerk_users-0.3.4-py3-none-any.whl` | no | **50.0.0** |
| `django_clerk_users-0.3.4-py3-none-any.whl[sdk]` | yes | 48.0.1 |

That is the request's outcome directly: default installs are free of the
`clerk-backend-api` ceiling, and opting into the SDK reinstates it, visibly.

### A real bug this surfaced

Switching the default backend made
`test_create_clerk_user_trims_secret_before_creating_sdk_client` issue a **live
HTTPS request to `api.clerk.com`**, which came back 401. The test patched
`clerk_backend_api.Clerk`, so with the thin client as default nothing was
mocked and the helper used a real `ClerkClient`. Fixed by pinning that test to
`CLERK_CLIENT_BACKEND="sdk"`. Worth noting as a hazard: unlike the SDK path,
the thin client will happily make real network calls if a test forgets to
inject a mock transport.

`test_verification_works_with_the_sdk_uninstalled` also needed updating: it
asserted an SDK-missing error from `get_clerk_client()`, which the thin default
no longer reaches. It now sets the SDK backend explicitly before asserting.

## Delivered result

Default installs no longer carry `clerk-backend-api`, so nothing caps
`cryptography` (50.x resolves where 48.x did before). Server-side Clerk API
calls use the built-in thin client by default.

- `clerk-backend-api` moved from `dependencies` to `optional-dependencies.sdk`.
- New `CLERK_CLIENT_BACKEND` setting (`"thin"` default, `"sdk"` opt-in), with
  `get_clerk_client_backend()` exported alongside it.
- New `NOTICE` with MIT attribution for logic ported from 6.0.1, shipped in the
  sdist.
- CI: an `install-shapes` matrix (base and `[sdk]`) and a `cryptolatest-base`
  job; a `py313-sdk` tox env.
- README documents both backends, the install commands, the ceiling tradeoff,
  and why selection is explicit. CHANGELOG flags this as breaking.

This is the final step of the 0.4.0 decoupling. `svix` remains a runtime
dependency for webhook verification and is untouched here.
