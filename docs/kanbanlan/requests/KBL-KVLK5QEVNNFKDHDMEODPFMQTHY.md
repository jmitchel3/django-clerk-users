# Implement thin-client REST resources for all consumed Clerk endpoints

- Kanbanlan: `KBL-KVLK5QEVNNFKDHDMEODPFMQTHY`
- Canonical home: `github`
- Canonical request: [#7](https://github.com/jmitchel3/django-clerk-users/issues/7)

## Request

Outcome: the thin client covers every Clerk endpoint this package actually consumes.

17 operations across users (get, list, create, update, delete), organizations (get, list), organization_memberships (list), email_addresses (create, delete), sign_in_tokens (create), sessions (create, create_token, list, revoke), invitations (create, revoke), and testing_tokens (create).

Call sites use inconsistent argument styles that must be preserved: users.list takes request={...} while organizations.list takes flat limit/offset kwargs, and every call accepts timeout_ms. Pagination handled consistently across list operations.

Depends on the thin client core.

## Decisions

- **The inconsistent argument styles are preserved deliberately**, as the
  request required. `users.list` takes `request={...}` while
  `organizations.list` takes flat `limit`/`offset`; `users.create` takes flat
  kwargs while `sessions.create` and `invitations.create` take `request={...}`.
  Normalizing them would be the tidier API and a breaking change at every call
  site. Each resource method documents which style it accepts, and the module
  docstring explains why the asymmetry is intentional rather than an oversight.
- **Resource methods accept both styles.** A `_body` helper merges a `request`
  dict with flat kwargs. Call sites use one or the other, never both, but
  accepting both means no call site can break on the distinction.
- **`None` values are dropped from request bodies.**
  `migrate_users_to_clerk.py:183` passes `first_name=None` explicitly, and
  sending a literal `null` is not the same as omitting the field.
- **`ClerkClient` mirrors the SDK's resource attribute names exactly**
  (`client.users`, `client.organization_memberships`, ...) so it can be passed
  as `clerk_client=` anywhere the SDK client was expected, with no call edits.
- **`paginate()` is a helper, not a rewrite of the call sites.** The request
  asked for pagination handled consistently across list operations. Adding it
  as an opt-in generator keeps this request additive; converting the existing
  hand-rolled offset loops in the sync commands would change runtime behavior
  and belongs with the cutover work in #10.
- **`paginate` handles both response envelopes**, because `users.list` returns
  a bare JSON array while `organizations.list` returns `{"data": [...]}`.

### Count discrepancy in the request

The request says "17 operations" but the list that follows enumerates 18:
users 5, organizations 2, organization_memberships 1, email_addresses 2,
sign_in_tokens 1, sessions 4, invitations 2, testing_tokens 1. All 18 are
implemented. `test_all_eighteen_operations_are_covered` asserts the total so
the discrepancy cannot quietly become a missing endpoint.

## Verification

- `uv run python -m pytest tests/test_clerk_api_resources.py -q` — 54 passed.
- `uv run python -m pytest -q` — 599 passed, 28 skipped.
- `uv run pre-commit run --files <new files>` — clean.
- The suite has two layers. The first asserts the wire shape of every operation
  (method, path, query, body). The second, which is the one that matters, hands
  a `ClerkClient` to the **real `server_api` helpers** as `clerk_client=` and
  checks they behave identically to the SDK client: `get_clerk_user`,
  `get_clerk_user_by_email`, `create_clerk_user` (including the duplicate
  identifier path through `ClerkAPIError`), `update_clerk_user_public_metadata`
  (merge semantics), `create_clerk_sign_in_token`, `revoke_clerk_user_sessions`,
  `send_clerk_invitation` / `revoke_clerk_invitation`, and
  `set_clerk_user_email` with pruning. A resource that produced the right HTTP
  request but the wrong argument style would pass layer one and fail layer two.
- A parametrized test asserts all 18 operations forward `timeout_ms`.
- `test_membership_public_user_data_is_attribute_accessible` covers the
  `getattr(membership, "public_user_data")` chain from
  `sync_clerk_organizations`.

### A note on the session revocation test

`test_revoke_clerk_user_sessions` deliberately uses a single short page. The
paginated revoke is a separate request on a branch that is not in this stack,
so asserting multi-page behavior here would pass or fail depending on merge
order. The single-page assertion holds both before and after that merge.

## Delivered result

New `clerk_api/resources.py` with eight resource classes covering all 18
consumed operations, plus `ClerkClient` as a drop-in stand-in for the SDK
client and a `paginate()` helper. `ClerkClient` and `paginate` are exported
from `django_clerk_users.clerk_api`.

Nothing is cut over yet. No existing call site was changed, so this request
carries no runtime behavior change; `clerk-backend-api` is still the live path.

Follow-up: #10 makes `clerk-backend-api` optional, which is where these
resources actually get wired in behind an explicit backend selection and where
the sync commands' hand-rolled offset loops can move onto `paginate()`.
