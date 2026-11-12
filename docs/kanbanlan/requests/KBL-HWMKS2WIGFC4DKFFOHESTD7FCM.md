# fix: webhook verification returns None with svix 2.x

- Kanbanlan: `KBL-HWMKS2WIGFC4DKFFOHESTD7FCM`
- Canonical home: `github`
- Canonical request: [#38](https://github.com/jmitchel3/django-clerk-users/issues/38)

## Request

`verify_clerk_webhook` returns the result of `svix.webhooks.Webhook.verify()`. svix 2.x changed `verify()` to return `None` (it calls the inner verifier with `json_parse=False`). `pyproject.toml` allows `svix>=1`, so fresh installs resolve svix 2.10.0 and every verified Clerk webhook yields a `None` payload.

Evidence: CI `Install shape`, `Cryptolatest`, and `Python 3.12-3.14` fail on `tests/test_live_clerk_smoke.py::test_live_clerk_smoke_verifies_signed_webhook` ("Webhook verifier returned unexpected payload: None"); scheduled Cryptography Watch runs on main fail the same way. Reproduced locally with svix 2.10.0. The locked dev env (svix 1.99.1) passes.

Outcome: verification still enforced by svix; the payload is parsed from the verified body so it works on svix 1.x and 2.x. Add a test that fails if `verify()` returns `None`.

## Decisions

- svix still performs signature and timestamp verification. When `verify()` returns `None` (svix 2.x), the verified `request.body` is parsed with `json.loads`; a dict return (svix 1.x) is used as-is, so existing mocks and 1.x installs behave the same.
- Non-object JSON payloads now raise `ClerkWebhookError` instead of reaching handlers that call `.get()`.
- No upper bound added to `svix>=1`; the code supports both majors.

## Verification

- `tests/test_webhook_svix_compat.py`: real signed request against the installed svix, both return contracts, bad signature, non-object and invalid JSON.
- Full suite passes in the locked env (svix 1.99.1) and in a fresh install-shape venv (svix 2.10.0, Django 6.1.3, cryptography 50.0.2), where `test_live_clerk_smoke_verifies_signed_webhook` previously failed. `webhooks/security.py` at 100 percent coverage.

## Delivered result

`verify_clerk_webhook` returns the verified payload on svix 1.x and 2.x; CI install-shape and matrix jobs go green again.
