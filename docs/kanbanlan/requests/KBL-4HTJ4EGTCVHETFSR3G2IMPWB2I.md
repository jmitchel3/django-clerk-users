# fix: preserve database routing for session activity updates

- Kanbanlan: `KBL-4HTJ4EGTCVHETFSR3G2IMPWB2I`
- Canonical home: `github`
- Canonical request: [#44](https://github.com/jmitchel3/django-clerk-users/issues/44)

## Request

The v0.5.0 code review reproduced session-created and session-ended writes targeting an unrelated default-database user with the same primary key as a user loaded from a shard. Preserve instance-aware write routing and refresh from the selected write database, including primary/replica routers. Add regressions for both activity fields. Scope: webhook handlers, routed database test configuration, and activity tests. Deliver in v0.5.1.

## Decisions

- Resolve the write database with Django's `router.db_for_write(model, instance=user)`, preserving both explicit router decisions and Django's fallback to the loaded instance's database.
- Keep the existing conditional update so concurrent or delayed events cannot regress timestamps. Use the selected write database for the refresh too; refreshing through a read router can otherwise expose stale replica data to lifecycle signal receivers.
- Do not force writes to `user._state.db`: a user loaded from a replica must still write to its primary.

## Verification

- Four real SQLite multi-database regressions cover both `last_login` and `last_logout`: a shard user whose primary key collides with an unrelated default-database user, and a stale replica whose instance-aware router directs writes to a primary. All four fail against v0.5.0 and pass with the fix.
- Replica tests cover both advancing and stale events, and assert the signal receives the primary's stored value and the correct `activity_advanced` flag.
- Python 3.12 / Django 6.0.7 / Svix 2.10.0: full suite **908 passed, 35 skipped**; focused activity, webhook handler, and webhook view suite **120 passed**.
- Python 3.12 / Django 4.2: activity suite **33 passed**.
- Ruff checks, formatting checks, and `git diff --check` pass for the changed files.

## Delivered result

Session webhook updates now preserve database routing and refresh activity from the database that accepted the write. This prevents cross-database primary-key collisions from changing unrelated users and keeps signal payloads current when reads use replicas. No model or migration changes are required.
