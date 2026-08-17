# Cache backend errors cause HTTP 500 on every authenticated request

- Kanbanlan: `KBL-I6Y64J453RERDKK6QBTLY6Q6ZA`
- Canonical home: `github`
- Canonical request: [#32](https://github.com/jmitchel3/django-clerk-users/issues/32)

## Request

## Summary

An unavailable cache backend takes down authentication entirely: every request carrying a valid bearer token returns **HTTP 500**. The cache here is a pure optimization, so it should degrade to a cache miss instead of a hard failure.

This is not hypothetical. It caused a multi-hour production outage on a downstream app when its Upstash Redis instance was temporarily rate-limited. Every authenticated API call returned 500 while Clerk, the tokens, and the app itself were all completely healthy.

Present in **0.1.3** (`authentication/utils.py:73`) and still present, unchanged, in **0.4.0** (`authentication/utils.py:183`). Upgrading does not fix it.

## Root cause

`get_clerk_payload_from_request` reads the cache outside any exception handling, and above the `try` block:

```python
token = get_bearer_token(request)
if not token:
    return None                      # unauthenticated: returns BEFORE the cache

token_hash = hashlib.sha256(token.encode()).hexdigest()
cache_key = f"clerk:payload:{token_hash}"

cached_payload = cache.get(cache_key)   # utils.py:183, unguarded
if cached_payload is not None:
    return cached_payload

try:
    ...
```

When the backend raises (connection refused, auth failure, rate limit, timeout), the exception propagates out of DRF's `authenticate()` and Django returns a 500.

### Why this is unusually hard to diagnose

The early `if not token: return None` means the cache is only touched when a token is present. So during an outage:

| Request | Reaches `cache.get()`? | Response |
|---|---|---|
| No `Authorization` header | no | clean **401** |
| Valid bearer token | yes | **500** |

Probing the API without credentials returns a perfectly healthy-looking 401, and the DRF browsable API shows `"Authentication credentials were not provided."` That points every diagnostic effort at Clerk configuration (secret key, `CLERK_AUTH_PARTIES`, token validity) when the actual fault is the cache. In the incident above this cost several hours before an A/B probe of two endpoints differing only in whether `cache.get()` executed revealed the real cause.

## Secondary: a failed cache write rejects a valid token

`cache.set` at `authentication/utils.py:222` is inside the `try`, but the broad handler below it converts any failure into an auth failure:

```python
except Exception as e:
    logger.warning(f"Clerk token validation error: {e}")
    raise ClerkTokenError(f"Token validation failed: {e}") from e
```

So an unwritable cache produces a spurious **401** on a token that verified successfully. Better than a 500, still wrong: failing to cache should never deny a user.

## Third: the same pattern in `caching.py`

Ten more unguarded calls, all reachable from the authenticated request path via `get_or_create_user_from_payload`:

- `cache.get`: lines 75, 138
- `cache.set`: lines 89, 93, 108, 153, 157, 172
- `cache.delete`: lines 119, 183

Each is an additional 500 vector from the same cause.

## Why fail-open is the correct behavior here

Every one of these caches is a latency optimization over an authoritative source. A miss means "re-verify the token with Clerk" or "re-query the database", which produces an identical result, only slower.

Treating a backend error as a miss therefore never causes the library to **accept** something it would otherwise reject. There is no security tradeoff. (That reasoning is specific to these caches and would not hold for a cache used as a source of truth, for example a revocation list.)

## Proposed fix

Add small internal helpers, then route all thirteen call sites through them:

```python
_CACHE_MISS = object()

def _safe_cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except Exception:
        logger.warning("Cache read failed for %r, treating as a miss", key, exc_info=True)
        return default

def _safe_cache_set(key, value, timeout=None):
    try:
        cache.set(key, value, timeout=timeout)
    except Exception:
        logger.warning("Cache write failed for %r, continuing uncached", key, exc_info=True)

def _safe_cache_delete(key):
    try:
        cache.delete(key)
    except Exception:
        logger.warning("Cache delete failed for %r", key, exc_info=True)
```

Under a cache outage the app then degrades to "slower, more calls to Clerk and Postgres" rather than "entirely down".

Worth considering alongside:

- Rate-limit the warning log so an outage does not itself flood the logs.
- Document that the cache is optional and that the library tolerates its loss.

## Reproduction

```python
from unittest.mock import patch
from django.test import RequestFactory

request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer <valid-token>")

with patch("django_clerk_users.authentication.utils.cache") as mock_cache:
    mock_cache.get.side_effect = ConnectionError("redis is down")
    get_clerk_payload_from_request(request)   # raises ConnectionError; should return a payload
```

Expected: the token is verified normally and a payload is returned, with a logged warning.
Actual: `ConnectionError` propagates, DRF returns 500.

A companion test should assert that a raising `cache.set` still returns a valid payload rather than raising `ClerkTokenError`.

## Affected versions

Confirmed in 0.1.3 and 0.4.0.

## Decisions

- **The helpers live in `caching.py` and are public, not private.** The report
  proposed module-private `_safe_cache_*` helpers, but three modules need them
  (`caching`, `authentication.utils`, `webhooks.handlers`). One home avoids
  three copies of the same `try`/`except`. `caching.py` keeps its
  `from django.core.cache import cache` import, so `django_clerk_users.caching.cache.*`
  remains a valid patch target for tests.
- **Existing tests were retargeted to the helpers, not to the cache object.**
  `authentication/utils.py` and `webhooks/handlers.py` no longer import `cache`,
  so `patch("...authentication.utils.cache.set")` would no longer resolve.
  They now patch `...authentication.utils.safe_cache_set` and
  `...webhooks.handlers.safe_cache_add`, which is also more precise: it scopes
  the patch to the call site under test instead of the process-wide cache proxy.
  The reproduction snippet in the report patches the old target and no longer
  applies as written; `tests/test_cache_failures.py` is the maintained version.
- **`safe_cache_set` returns a bool.** `get_clerk_payload_from_request` only
  emits its "cached for N seconds" debug line when the write actually landed,
  so the logs do not claim a cache entry that does not exist.
- **`safe_cache_add` takes a `default` for what an outage means.** The only
  caller, `is_duplicate_webhook`, wants "treat it as a new event" so the webhook
  is processed rather than dropped. The handlers use `update_or_create`, so
  reprocessing is idempotent; a dropped event is not recoverable.
- **Failed invalidation logs at `ERROR`, everything else at `WARNING`.** A
  swallowed `cache.delete` is the one fail-open case that is not free: the stale
  entry is served until it expires (bounded by `CLERK_CACHE_TIMEOUT` /
  `CLERK_ORG_CACHE_TIMEOUT`). Reads, writes, and adds cost only latency.
- **Log throttling was rejected in favor of conditional tracebacks.** The report
  suggested rate-limiting the warning. A rate limiter needs state and a policy;
  instead `exc_info` is set from `logger.isEnabledFor(logging.DEBUG)`, so an
  outage produces one short line per failure and full tracebacks only when the
  `django_clerk_users.caching` logger is turned up.
- **`clerk_api/tokens.py` was deliberately left alone.** Its `_jwks_cache` is an
  in-process cache, not a Django cache backend, so it has none of the failure
  modes in this report.
- **Two unrelated pre-commit rewrites were reverted** (a `django-upgrade`
  rewrite of `authentication/drf.py` and a whitespace fix in `py.typed`). They
  are pre-existing on `main` and belong to their own request. CI runs `ruff`
  only, so neither blocks this change.

## Verification

- `uv run python -m pytest -q`: 867 passed, 29 skipped.
- Coverage held at 100% (`--cov=django_clerk_users`, branch coverage on):
  `caching.py`, `authentication/utils.py`, and `webhooks/handlers.py` are each
  at 100% including the new `except` branches.
- `uv run --extra drf python -m pytest tests/test_cache_failures.py tests/test_drf.py -q`:
  31 passed, confirming the DRF entry point returns a user rather than
  propagating the backend error.
- `uv run ruff check .` and `uv run ruff format --check .` pass.
- `uv run tox`: all 12 environments OK across Python 3.12, 3.13, and 3.14 with
  Django 4.2, 5.2, and 6.0, plus the `drf`, `sdk`, and `cryptolatest`
  environments. Combined coverage across all of them is 100%.
- `uv run pre-commit run --files <changed files>`: all hooks pass. Note that
  `pre-commit run --all-files` also rewrites `authentication/drf.py`
  (django-upgrade) and `py.typed` (whitespace); both are pre-existing on `main`,
  unrelated to this request, and were reverted rather than folded in.
- New `tests/test_cache_failures.py` drives a raising cache through every
  affected entry point: `get_clerk_payload_from_request` (read and write),
  `ClerkAuthentication.authenticate`, `ClerkOrganizationMiddleware`,
  `is_duplicate_webhook`, and the user and organization caching helpers. Each of
  these tests fails on `main` with the backend error propagating.

## Delivered result

All fourteen Django cache call sites in the package now fail open. A cache
outage degrades to extra traffic against Clerk and the database instead of
HTTP 500 on every authenticated request, HTTP 500 on every request for
org-scoped apps, a spurious 401 on a token that verified, or HTTP 500 on the
webhook endpoint.

The report listed thirteen sites. Two corrections were found while verifying it:

- `webhooks/handlers.py:111` (`cache.add`, webhook deduplication) was not in the
  report and is a fourteenth site.
- The ten `caching.py` sites are not all direct 500 vectors as the report
  states. Reached through `get_or_create_user_from_payload`, the broad handler
  at `authentication/utils.py` converts them to `ClerkAuthenticationError`, so
  they surface as 401s. The genuine additional 500 vector is
  `ClerkOrganizationMiddleware` → `get_cached_organization` → `caching.py`
  `cache.get`, which nothing catches.

The blast radius is also wider than the report describes: `ClerkAuthMiddleware`
catches only `ClerkTokenError` around `get_clerk_payload_from_request`, both on
first authentication and during its periodic session revalidation, so plain
Django views were affected alongside DRF ones.

Documented in the README under "Caching" and in the production checklist, since
operators should alert on `django_clerk_users.caching` warnings: the package
rides out a cache outage, but by sending more traffic to Clerk and the database.

No follow-up work remains for this request.
