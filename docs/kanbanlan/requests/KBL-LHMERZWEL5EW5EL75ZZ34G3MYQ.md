# Paginate session listing in revoke_clerk_user_sessions

- Kanbanlan: `KBL-LHMERZWEL5EW5EL75ZZ34G3MYQ`
- Canonical home: `github`
- Canonical request: [#4](https://github.com/jmitchel3/django-clerk-users/issues/4)

## Request

Outcome: revoke_clerk_user_sessions covers all active sessions rather than a single page.

server_api.py:564 calls sessions.list with no limit or offset and no pagination loop. tests/test_server_api.py:420 asserts the current call shape, so it needs updating alongside the fix rather than being kept as-is.

Target 0.3.5, independent of the clerk-backend-api decoupling work. Analysis recorded in the request record on delivery.

## Decisions

- **List every page before revoking anything.** Revoking a session removes it
  from the `status="active"` result set, so revoking while paging would shift
  the offset cursor and silently skip sessions. `_list_active_clerk_session_ids`
  therefore drains the listing into a plain list of IDs first, and
  `revoke_clerk_user_sessions` only then iterates that list.
- **Offset pagination with a page size of 100**, matching the loop shape already
  used by `sync_clerk_users` and `sync_clerk_organizations`. A short page ends
  the loop, consistent with those commands.
- **Bounded page count.** `CLERK_SESSION_LIST_MAX_PAGES = 100` caps the loop at
  10,000 sessions so a misbehaving or always-full response cannot spin forever.
  Hitting the ceiling logs a warning rather than raising; the sessions collected
  so far are still revoked.
- **De-duplicate IDs across pages.** Concurrent session churn can surface the
  same session on two pages; the `seen` set keeps the revoke count honest.
- Error handling is unchanged: any SDK exception is still funneled through
  `_log_clerk_error` and the function returns `None`.

## Verification

- `uv run python -m pytest tests/test_server_api.py -q` — 28 passed.
- `uv run python -m pytest -q` — 473 passed, 28 skipped.
- `uv run pre-commit run --files src/django_clerk_users/server_api.py tests/test_server_api.py` — all applicable hooks passed.
- New regression tests in `tests/test_server_api.py`:
  - `test_revoke_clerk_user_sessions_follows_every_page` — a full first page plus
    a short second page yields two `sessions.list` calls at offsets 0 and 100,
    and the second page's session is revoked.
  - `test_revoke_clerk_user_sessions_lists_all_pages_before_revoking` — asserts
    both list calls happen before the first revoke.
  - `test_revoke_clerk_user_sessions_stops_at_page_ceiling` — an endlessly full
    response stops at `CLERK_SESSION_LIST_MAX_PAGES`.
  - `test_revoke_clerk_user_sessions_skips_duplicate_ids_across_pages` — a
    session repeated across pages is revoked once.
- The pre-existing single-page test was updated for the new call shape
  (`limit` and `offset` are now always sent), as the request anticipated.

## Delivered result

`revoke_clerk_user_sessions` now covers all active sessions for a user instead
of whichever ones fit in the Clerk API's default first page. Listing moved into
a new module-private helper, `_list_active_clerk_session_ids`, alongside two new
module constants, `CLERK_SESSION_LIST_PAGE_SIZE` and
`CLERK_SESSION_LIST_MAX_PAGES`.

Public behavior is otherwise unchanged: the function still returns the number of
sessions revoked, `None` when no secret key is configured, and `None` on API
error.

No follow-up work remains for this request. Independent of the
`clerk-backend-api` decoupling effort tracked separately.
