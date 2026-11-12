# docs: add a tested hybrid Clerk and Django session integration recipe

- Kanbanlan: `KBL-KFV2YMPYLRHRNFWBQPQRQNLBGI`
- Canonical home: `github`
- Canonical request: [#34](https://github.com/jmitchel3/django-clerk-users/issues/34)

## Request

A downstream Django/DRF application uses Clerk bearer authentication for one population and Django sessions for another. It currently maintains a custom authentication wrapper and historical compatibility patches. A consolidated, tested recipe would help consumers use the package's supported behavior and keep only application-specific policy locally.

Reviewed version: 0.4.1, main `a59ed29bc78cb58674b1a4064827d01121a166a2`.

### Already supported — do not reimplement

- `get_bearer_token` already accepts case-insensitive bearer schemes and whitespace. A downstream comment claiming only the exact `Bearer ` prefix works is stale.
- `CLERK_SYNC_PASSWORDS=False` and `CLERK_DISABLE_PASSWORD_SYNC=True` already disable password synchronization. A downstream `AbstractClerkUser.set_password` monkey patch can be retired after its regression checks pass.
- Cache-backend outage handling was delivered in #32; this is not another request for that fix.

### Requested documentation outcome

Provide one copyable, tested hybrid-auth recipe that:

1. Uses ordinary DRF `SessionAuthentication` for cookie-backed sessions, preserving CSRF checks. Explain that the existing `ClerkSessionAuthentication` defaults to `CsrfExemptSessionAuthentication`, and show the supported `session_authentication_class` override.
2. Documents explicit-credential precedence. For apps that require a supplied Authorization header to be authoritative, show how malformed credentials or an unconfigured Clerk verifier produce an authentication failure rather than permission to try another authenticator. Distinguish this optional strict policy from DRF's normal multi-scheme behavior.
3. Uses the existing password-sync settings and bearer parser instead of global monkey patches or rewriting request headers.
4. Keeps account-population rules, host restrictions, authorization, and session-age limits in the application.

Acceptance: executable examples cover valid bearer, valid cookie with CSRF, unsafe cookie request without CSRF, malformed supplied credentials, and unconfigured Clerk. Explain which existing patches can be removed and which application policies must remain. No switch of `AUTH_USER_MODEL` is required.

Evidence: [DRF authenticators](https://github.com/jmitchel3/django-clerk-users/blob/a59ed29bc78cb58674b1a4064827d01121a166a2/src/django_clerk_users/authentication/drf.py), [bearer parsing](https://github.com/jmitchel3/django-clerk-users/blob/a59ed29bc78cb58674b1a4064827d01121a166a2/src/django_clerk_users/authentication/utils.py), [password-sync implementation](https://github.com/jmitchel3/django-clerk-users/blob/a59ed29bc78cb58674b1a4064827d01121a166a2/src/django_clerk_users/models.py).

## Decisions

- Recipe lives in `docs/recipes/hybrid-auth.md`; its copyable module `docs/recipes/hybrid_auth_authentication.py` is loaded by the tests, and a test asserts the markdown embeds that file verbatim, so the doc cannot drift.
- No package code change. Two recipe classes: `CsrfClerkSessionAuthentication` (package precedence, CSRF enforced via the supported `session_authentication_class` hook) and `StrictClerkSessionAuthentication` (supplied Authorization header is authoritative; malformed credentials and unconfigured Clerk raise `AuthenticationFailed`).
- Strict class detects "Clerk unconfigured" as `ClerkAuthentication.authenticate()` returning `None` after `get_bearer_token` found a token, so it needs no private imports.
- Documented nuance: the package `ClerkSessionAuthentication` treats `Bearer` with an empty token as anonymous (no session fallback), and its session fallback is CSRF exempt.

## Verification

- `tests/test_drf_hybrid_recipe.py` (real DRF, `APIClient(enforce_csrf_checks=True)`): valid bearer, case/whitespace-tolerant scheme, valid cookie GET and POST with CSRF, unsafe cookie POST without CSRF (403), invalid bearer with a session cookie present (401), strict malformed credentials (401 for Basic, empty Bearer, Token), strict unconfigured Clerk (None, empty, placeholder key), default-policy contrasts, package default CSRF exemption, `CLERK_SYNC_PASSWORDS=False` replacing a `set_password` patch, and doc/module sync.
- Added to the tox `drf` env. Full suite passes.

## Delivered result

Tested hybrid-auth recipe with precedence table, copyable authenticators, a patch-retirement table, and the list of policies that stay in the application. README DRF section links to it.
