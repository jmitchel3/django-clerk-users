# fix: keep session activity timestamps monotonic across delayed webhooks

- Kanbanlan: `KBL-TAEOQUW2AFDHBLXYBGNN2ZMJBE`
- Canonical home: `github`
- Canonical request: [#36](https://github.com/jmitchel3/django-clerk-users/issues/36)

## Request

Delayed or replayed session webhooks should not make a user's latest recorded activity move backward. Downstream activity reports depend on these timestamps.

Source-reviewed in 0.4.1 / main `a59ed29bc78cb58674b1a4064827d01121a166a2`; this report is based on the handlers' assignment behavior, not a new live production reproduction.

### Current behavior

`handle_session_created` unconditionally assigns parsed `created_at` to `last_login`. `handle_session_ended` similarly assigns parsed `abandoned_at` or `updated_at` to `last_logout`. An older event can replace a newer value, and a missing timestamp can replace a known value with `None`. `transaction.atomic` alone does not prevent concurrent read/modify/write races.

### Expected outcome

- Each stored timestamp is the maximum of its current value and a valid incoming event time; initialize a null value from the first valid event.
- Duplicate, older, and missing/malformed timestamps never erase or regress known activity.
- Make the update safe under concurrent delivery, using an appropriate conditional database update or locking.
- Preserve the existing handled/missing-user contract and explicitly document whether stale events still emit lifecycle signals. Do not silently change revocation or downstream receiver behavior while fixing timestamp storage.

Acceptance tests: newer-then-older delivery, replay, missing/malformed timestamps, initial null values, and a concurrent-update regression case. Apply the same monotonic rule to both session activity fields.

Evidence: [session webhook handlers](https://github.com/jmitchel3/django-clerk-users/blob/a59ed29bc78cb58674b1a4064827d01121a166a2/src/django_clerk_users/webhooks/handlers.py#L248).

## Decisions

- Monotonic writes use one conditional `UPDATE ... WHERE field IS NULL OR field < value` instead of `save()`. This is race-safe on PostgreSQL (row lock plus WHERE re-check under READ COMMITTED) and SQLite (serialized writes) without `select_for_update`.
- Because the write is a queryset `update()`, these two fields no longer trigger `post_save` for the user. No package code listens for that; the session signals remain the supported hook.
- Session signals still fire for stale, replayed, and timestamp-less events so revocation receivers are unchanged. A new `activity_advanced` keyword lets receivers ignore stale events.
- `parse_clerk_timestamp` now rejects booleans and out-of-range millisecond values (returns `None`) instead of raising, so malformed payloads are acknowledged rather than retried forever.

## Verification

- `tests/test_session_activity.py` covers, for both fields: null initialization, newer-then-older, older-then-newer, replay (no `updated_at` churn), missing/malformed/bool/overflow/wrong-type timestamps, in-memory user state seen by receivers, and a concurrent newer write landing between user load and update.
- Full suite: 896+ passed; `webhooks/handlers.py` at 100 percent coverage.

## Delivered result

`last_login` and `last_logout` are now monotonic under delayed, replayed, malformed, and concurrent session webhooks. Signal contract preserved and documented in the README and `webhooks/signals.py`.
