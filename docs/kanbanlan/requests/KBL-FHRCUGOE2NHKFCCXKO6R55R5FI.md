# Always construct AuthenticateRequestOptions in token verification

- Kanbanlan: `KBL-FHRCUGOE2NHKFCCXKO6R55R5FI`
- Canonical home: `github`
- Canonical request: [#5](https://github.com/jmitchel3/django-clerk-users/issues/5)

## Request

Outcome: token verification never passes options=None to the Clerk SDK.

authentication/utils.py:180 leaves auth_options as None when CLERK_FRONTEND_HOSTS and CLERK_AUTH_PARTIES are both empty. The SDK dereferences options.secret_key (sdk.py:389), so verification fails and is surfaced as a generic token error via the broad except at :200.

checks.py:92 already warns on the empty allowlist, and tests/settings.py:80 sets it, so the suite never exercises this path. Add coverage for it.

Target 0.3.5.

## Decisions

- **Always construct the options object.** `clerk_backend_api/sdk.py:389` reads
  `options.secret_key` with no `None` guard, so `options=None` raises
  `AttributeError`. The broad `except Exception` in
  `get_clerk_payload_from_request` swallowed it and reported a generic token
  validation failure, hiding the real cause.
- **Normalize an empty allowlist to `None`, not `[]`.** This is the subtle half
  of the fix and is not visible from the request text.
  `clerk_backend_api/security/verifytoken.py:43` reads:

  ```python
  if options.authorized_parties is not None:
      if azp is None or azp not in options.authorized_parties:
          raise ...
  ```

  An empty list is *not* `None`, so passing `[]` would enable the `azp` check
  against an allowlist that matches nothing, rejecting every token. The fix
  passes `_get_auth_parties() or None` so an unset allowlist means "skip the azp
  check", matching the prior behavior when `options` was `None`.
- Left the broad `except Exception` and the `checks.py:92` warning as they are.
  Narrowing the exception handler is a separate concern, and the empty-allowlist
  warning is still correct guidance.

## Verification

- `uv run python -m pytest tests/test_authentication.py -q` — 28 passed.
- `uv run python -m pytest -q` — 472 passed, 28 skipped.
- `uv run pre-commit run --files src/django_clerk_users/authentication/utils.py tests/test_authentication.py` — clean.
- **Confirmed the new coverage fails against the unfixed source.** Reverting only
  `authentication/utils.py` and rerunning the three new tests produced
  `assert None is not None` at `tests/test_authentication.py:302`, so the
  regression test genuinely pins the bug rather than passing either way.
- New tests in `tests/test_authentication.py::TestClerkPayloadFromRequest`:
  - `test_options_are_built_when_no_authorized_parties_configured` — with both
    `CLERK_FRONTEND_HOSTS` and `CLERK_AUTH_PARTIES` empty, the SDK still
    receives a non-`None` options object whose `authorized_parties` is `None`.
  - `test_configured_authorized_parties_reach_the_sdk` — a configured allowlist
    is forwarded unchanged.
  - `test_empty_allowlist_does_not_reject_a_valid_token` — pins the `[]` vs
    `None` distinction directly against the real `AuthenticateRequestOptions`.

As the request noted, `tests/settings.py:80` sets `CLERK_FRONTEND_HOSTS`, so the
suite never reached this path before. The new tests override it per-test via the
`settings` fixture rather than changing the shared test settings, which would
have weakened coverage of the configured path.

## Delivered result

`get_clerk_payload_from_request` now always passes an `AuthenticateRequestOptions`
instance to `clerk.authenticate_request`, so deployments with no configured
authorized parties verify tokens instead of failing with a generic token error.

No follow-up work remains for this request. Related but out of scope: the broad
`except Exception` that masked this failure mode is what made the bug present as
a generic error, and #9 (harden session token verification beyond SDK parity)
covers that area more directly.
