# Recipe: hybrid Clerk bearer and Django session authentication (DRF)

For APIs where one population (SPA, mobile, service clients) sends Clerk
session tokens as `Authorization: Bearer ...` and another (staff, admin,
server-rendered pages) uses Django session cookies. No `AUTH_USER_MODEL`
change is required.

Every behavior below is exercised by
[`tests/test_drf_hybrid_recipe.py`](../../tests/test_drf_hybrid_recipe.py),
which loads the module on this page directly.

## 1. Pick a precedence policy

| Request | `ClerkSessionAuthentication` (package default) | `CsrfClerkSessionAuthentication` | `StrictClerkSessionAuthentication` |
| --- | --- | --- | --- |
| Valid `Bearer <token>` | Clerk user | Clerk user | Clerk user |
| Invalid or expired bearer token | 401 | 401 | 401 |
| No `Authorization`, valid session cookie, safe method | Session user | Session user | Session user |
| No `Authorization`, session cookie, unsafe method with CSRF token | Session user | Session user | Session user |
| No `Authorization`, session cookie, unsafe method without CSRF token | **Allowed (CSRF exempt)** | 403 | 403 |
| Non-Bearer scheme (`Basic ...`, `Token ...`) | Session fallback | Session fallback | 401 |
| Empty or whitespace-only `Authorization` header | Session fallback | Session fallback | 401 |
| `Bearer` with no token | Anonymous | Anonymous | 401 |
| Bearer token while Clerk is unconfigured | Anonymous | Anonymous | 401 |

"Anonymous" means the authenticator returns `None`: DRF tries the next class in
`DEFAULT_AUTHENTICATION_CLASSES` and, if none authenticates, permissions decide
(401 for `IsAuthenticated`). That is DRF's normal multi-scheme behavior.

- **`ClerkSessionAuthentication`** uses `CsrfExemptSessionAuthentication` for
  its session fallback. Only use it when cookie sessions are protected some
  other way.
- **`CsrfClerkSessionAuthentication`** overrides the supported
  `session_authentication_class` hook with DRF's `SessionAuthentication`, so
  cookie requests keep Django's CSRF check. Choose this unless you need the
  strict policy.
- **`StrictClerkSessionAuthentication`** treats any supplied `Authorization`
  header as authoritative: malformed credentials or an unconfigured Clerk
  verifier fail authentication instead of letting the session cookie or a
  later authenticator take over. Use it as the only authentication class.

## 2. Copy the authenticators

Save as `myapp/authentication.py`:

```python
"""
Hybrid Clerk bearer + Django session authentication for DRF.

Copy this module into your project (for example ``myapp/authentication.py``).
It only uses supported django-clerk-users APIs: no monkey patches and no
rewriting of request headers.
"""

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, SessionAuthentication

from django_clerk_users.authentication import (
    ClerkAuthentication,
    ClerkSessionAuthentication,
)
from django_clerk_users.authentication.utils import get_bearer_token


class CsrfClerkSessionAuthentication(ClerkSessionAuthentication):
    """
    Default precedence, CSRF enforced for cookie sessions.

    ``ClerkSessionAuthentication`` uses ``CsrfExemptSessionAuthentication`` for
    its session fallback. Overriding ``session_authentication_class`` with DRF's
    ``SessionAuthentication`` keeps Django's CSRF check on unsafe methods.

    A non-Bearer Authorization header (or ``Bearer`` with no token, or Bearer
    while Clerk is unconfigured) returns ``None`` so DRF tries the next
    authenticator, which is DRF's normal multi-scheme behavior.
    """

    session_authentication_class = SessionAuthentication


class StrictClerkSessionAuthentication(BaseAuthentication):
    """
    A supplied Authorization header is authoritative.

    - No Authorization header: Django session with CSRF enforced.
    - ``Authorization: Bearer <token>``: Clerk only. Invalid tokens fail.
    - Any other Authorization value (including an empty or whitespace-only
      header), an empty Bearer token, or Clerk not configured: authentication
      fails. The request never falls through to the session cookie or to a
      later authenticator.

    List it as the only entry in ``DEFAULT_AUTHENTICATION_CLASSES``; any class
    listed after it would only see requests that carried no credentials.
    """

    clerk_authentication_class = ClerkAuthentication
    session_authentication_class = SessionAuthentication

    def __init__(self):
        self.clerk = self.clerk_authentication_class()
        self.session = self.session_authentication_class()

    def authenticate(self, request):
        if "authorization" not in request.headers:
            return self.session.authenticate(request)

        if get_bearer_token(request) is None:
            raise exceptions.AuthenticationFailed(
                "Malformed Authorization header; expected 'Bearer <token>'."
            )

        result = self.clerk.authenticate(request)
        if result is None:
            # A token was supplied, so None means Clerk is not configured
            # (no usable CLERK_SECRET_KEY or CLERK_JWT_KEY).
            raise exceptions.AuthenticationFailed(
                "Clerk bearer authentication is not configured."
            )
        return result

    def authenticate_header(self, request):
        # Makes DRF answer 401 with WWW-Authenticate instead of 403.
        return "Bearer"
```

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "myapp.authentication.StrictClerkSessionAuthentication",
        # or "myapp.authentication.CsrfClerkSessionAuthentication",
    ],
}
```

Cookie clients send the CSRF token in `X-CSRFToken` on unsafe methods (read it
from the `csrftoken` cookie, set by a view using `ensure_csrf_cookie` or any
form render). Bearer clients do not need CSRF tokens.

## 3. Use package settings, not patches

| Local patch or workaround | Supported replacement |
| --- | --- |
| Custom bearer parsing, or rewriting `HTTP_AUTHORIZATION` so only the exact `Bearer ` prefix is seen | `get_bearer_token` already accepts any scheme casing and extra whitespace (`bearer`, `BEARER`, `  Bearer   tok `). |
| Monkey patching `AbstractClerkUser.set_password` to stop Clerk password sync | `CLERK_SYNC_PASSWORDS = False` (or the legacy `CLERK_DISABLE_PASSWORD_SYNC = True`). Per call: `user.set_password(pw, sync_to_clerk=False)`. |
| Wrapping `ClerkSessionAuthentication` to swap its session class | Subclass and set `session_authentication_class`, as above. |
| Catching cache outages around Clerk authentication | Built in since 0.4.1: cache failures degrade to a miss. |

Before deleting a patch, run its existing regression tests against the
replacement.

## 4. What stays in your application

The package authenticates; it does not decide who may use which surface. Keep
these in your code:

- **Account-population rules**: for example, staff must use sessions and
  Clerk users must use bearer tokens. Enforce with a permission class that
  inspects `request.auth` (a `dict` Clerk payload for bearer requests, `None`
  for session requests) and `request.user`.
- **Host or origin restrictions**: which hostnames accept cookies versus
  bearer tokens; `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and
  `CLERK_FRONTEND_HOSTS` (authorized parties) are the relevant settings.
- **Authorization**: permissions, object access, organization checks
  (`request.org` is set for Clerk bearer requests).
- **Session-age limits**: `SESSION_COOKIE_AGE`, idle timeouts, and forced
  re-login for privileged actions.
