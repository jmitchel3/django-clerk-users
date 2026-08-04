# Reach 100% coverage: commands and webhook handlers batch

- Kanbanlan: `KBL-IGGYGIKPZREARLEW6J7Q3DU4TE`
- Canonical home: `github`
- Canonical request: [#28](https://github.com/jmitchel3/django-clerk-users/issues/28)

## Request

Outcome: raise verified statement and branch coverage to 100% for four operational modules. Scope: (1) management/commands/migrate_users_to_clerk.py; (2) management/commands/sync_clerk_users.py; (3) management/commands/sync_clerk_organizations.py; (4) webhooks/handlers.py. Acceptance: every scoped module reports 100% statements and branches under repository coverage configuration; tests exercise meaningful command validation, dry-run, retry/error, pagination, synchronization, and webhook dispatch paths; targeted and full suites pass; durable verification is recorded.

## Decisions

- Keep the batch test-only. All command and handler branches were reachable
  behavior, so no production exclusions or source changes were required.
- Exercise management commands through Django's `call_command` boundary where
  possible so argument validation, output, pagination, and API request shapes
  are verified together; call private member-sync helpers directly only for
  their isolated paging and persistence fallbacks.
- Treat duplicate-email creation as a race-recovery workflow: verify successful
  relinking, lookup failure, and a vanished lookup result separately from
  ordinary creation failures.
- Verify webhook routing in both optional-organization states and cover handler
  failures at the transaction boundary, including missing identifiers,
  nonexistent users, cache/database failures, and unsupported timestamps.

## Verification

- Scoped branch coverage:
  `uv run coverage run --branch -m pytest -q tests/test_management_commands.py tests/test_webhooks.py`
  — 106 passed; all four modules report 100%, totaling 523 statements and 136
  branches with zero misses or partial branches.
- Full branch coverage: `uv run coverage run --branch -m pytest -q` — 818
  passed, 28 skipped; repository coverage increased from 91.58% to 95.10%.
- Remaining missed statements fell from 243 to 137; partial branches fell from
  84 to 49.
- `uv run ruff check` on both changed test files — passed.
- `uv run ruff format --check` on both changed test files — passed.
- `git diff --check` — passed.

## Delivered result

Added 31 tests across the management-command and webhook suites. Production
source remains unchanged, and the migrate-users command, both sync commands,
and core webhook handlers now have complete statement and branch coverage.

The repository-wide 100% objective remains active. Only organization webhooks
and the server API compatibility layer retain coverage gaps.
