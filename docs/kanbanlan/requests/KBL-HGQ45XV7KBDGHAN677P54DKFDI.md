# docs: document upgrades for consumers with vendored Clerk migrations

- Kanbanlan: `KBL-HGQ45XV7KBDGHAN677P54DKFDI`
- Canonical home: `github`
- Canonical request: [#35](https://github.com/jmitchel3/django-clerk-users/issues/35)

## Request

A downstream application adopted a local `MIGRATION_MODULES` chain while using 0.2.x, then ported the UID-uniqueness change into that chain. It now uses 0.4.1 but still cannot safely remove its override simply because the current package ships migrations.

Reviewed main: `a59ed29bc78cb58674b1a4064827d01121a166a2`.

### Concrete compatibility problem

The local chain uses `0004_clerkuser_username_index` and `0005_clerkuser_unique_uid`. Upstream uses `0004_clerkuser_username_index_state` and `0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more`. Similar schema operations do not make the migration recorder identities equivalent. The local 0005 already carries UID deduplication, index removal, and the unique constraint.

This is a request for a supported upgrade guide, not an allegation that current packaged migrations are missing, and not a request to rewrite applied migration history.

### Requested outcome

- Document how to compare the recorded migration graph, actual database schema, index/constraint state, and model state for these historical installations.
- Explain when retaining the local chain and deliberately porting new upstream changes is the supported choice.
- If a path back to packaged migrations is supported, demonstrate it using a representative legacy fixture and clearly state its preconditions; do not prescribe unconditional `--fake` or deleting recorder entries.
- Cover fresh installs and upgrades without changing the user model identity, losing users, changing existing primary keys, or breaking foreign keys.

Acceptance: a reproducible PostgreSQL upgrade example preserves rows and references, applies UID uniqueness correctly, and leaves `makemigrations --check` clean. Distinguish schema equivalence from migration-name equivalence.

Evidence: [upstream 0004](https://github.com/jmitchel3/django-clerk-users/blob/a59ed29bc78cb58674b1a4064827d01121a166a2/src/django_clerk_users/migrations/0004_clerkuser_username_index_state.py), [upstream 0005](https://github.com/jmitchel3/django-clerk-users/blob/a59ed29bc78cb58674b1a4064827d01121a166a2/src/django_clerk_users/migrations/0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more.py).

## Decisions

- Guide at `docs/recipes/vendored-migrations.md` distinguishes migration identity, model state, and database schema, and offers two supported paths: keep the local chain (always supported) or return to packaged migrations under stated preconditions.
- The return path uses `migrate django_clerk_users <upstream 0005> --fake` only after model-state, recorder, and schema checks pass; old local recorder rows are kept, not deleted.
- Root cause of the 0004 mismatch: the 0.2.x model declared `Index(fields=["username"])` with no migration, so downstream `makemigrations` created a real index while upstream 0004 is state-only. A port that copies upstream 0005's state-only removal leaves an extra DB index invisible to `makemigrations --check`; the fixture `clerk_migrations_drift` reproduces it and the schema query catches it.
- Legacy fixture under `tests/vendored_upgrade/`: 0001 to 0003 copied verbatim from v0.2.4, local 0004/0005 as described in the issue, plus a `legacy_app` with a PROTECT FK to the user.
- The schema query is a versioned SQL file embedded in the guide; the guide's expected-output block is asserted against a fresh packaged install.

## Verification

- `tests/test_vendored_migration_upgrade.py` (PostgreSQL, subprocess per Django step): fresh install matches the documented schema and `makemigrations --check`; legacy chain seeded with duplicate UIDs, group m2m, and FK rows, then switched to packaged migrations, preserves pks, FKs, m2m rows, dedupes UIDs (lowest pk keeps the value), enforces the unique constraint, and leaves `migrate --check` and `makemigrations --check` clean; drift variant detected and fixed; retaining the local chain stays clean.
- Passed locally on PostgreSQL 14.19. New CI job `postgres-upgrade` runs it on postgres:17 with job and step timeouts. Skipped elsewhere without `DJANGO_CLERK_USERS_POSTGRES_URL`.

## Delivered result

Supported, tested upgrade guide for vendored-migration consumers, with a reproducible PostgreSQL scenario in CI. No package migration or model changes.
