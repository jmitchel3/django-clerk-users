# Upgrading with a vendored migration chain

This guide is for projects that set
`MIGRATION_MODULES = {"django_clerk_users": "myapp.clerk_migrations"}` while on
0.2.x and ported later upstream changes (such as UID uniqueness) into their own
chain. Current releases ship complete migrations, but that alone does not make
it safe to remove the override.

Fresh installs need none of this: do not set `MIGRATION_MODULES` for
`django_clerk_users`, run `migrate`, and you get the packaged chain.

Every step below runs against PostgreSQL in
[`tests/test_vendored_migration_upgrade.py`](../../tests/test_vendored_migration_upgrade.py),
using a representative legacy fixture in
[`tests/vendored_upgrade/`](../../tests/vendored_upgrade/).

## Why similar migrations are not interchangeable

Django tracks three separate things. Only the first two are usually checked.

| Kind of equivalence | What Django compares | How to check |
| --- | --- | --- |
| Migration identity | `(app, name)` rows in `django_migrations` | `showmigrations django_clerk_users` |
| Model state | The models versus the state your migration graph builds | `makemigrations --check --dry-run` |
| Database schema | The real columns, constraints, and indexes | The SQL query in step 3 |

A typical vendored chain:

| Packaged (0.3.1+) | Typical local chain |
| --- | --- |
| `0001_initial` | `0001_initial` (copied) |
| `0002_make_clerk_id_nullable` | `0002_make_clerk_id_nullable` (copied) |
| `0003_add_username_make_email_nullable` | `0003_add_username_make_email_nullable` (copied) |
| `0004_clerkuser_username_index_state` (state only, no SQL) | `0004_clerkuser_username_index` (really creates the index) |
| `0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more` | `0005_clerkuser_unique_uid` |

The two 0004s differ in kind, not only in name. The 0.2.x model declared
`Index(fields=["username"])` without a migration, so `makemigrations` in a
downstream project generated a real `AddIndex`. Upstream later recorded that
index in state only, because the packaged chain never created it. Both 0005s
then remove it, one for real and one in state only. A port that copied
upstream's state-only removal keeps an extra index in the database while
`makemigrations --check` reports nothing.

## Option A: keep the local chain (always supported)

Keeping `MIGRATION_MODULES` is a valid, permanent choice. For each release:

1. Read the release's new files under `django_clerk_users/migrations/`.
2. Port each one into your chain as a new local migration, keeping its
   operations (including any `RunPython` data steps) and your own numbering
   and dependencies.
3. Run `makemigrations django_clerk_users --check --dry-run`; it must report
   no changes.
4. Compare your schema with a fresh packaged install (step 3 below) in CI or
   before deploying.

Choose this when any precondition for option B fails, when you have local
operations that have no upstream equivalent, or when you would rather not
touch the recorder.

## Option B: return to packaged migrations

Do this on a staging copy of production first. Take a backup.

### Preconditions

All must hold. If one fails, stay on option A, or add a local migration that
closes the gap and start again.

1. The local chain's `0001` to `0003` are recorded under the packaged names
   (they were copied unchanged).
2. Your local chain includes the equivalent of everything up to packaged
   `0005` (UID dedup, removing the four `Meta` indexes, `uid` unique) and
   nothing beyond the packaged release you are moving to.
3. Model state is clean with the local chain.
4. The database schema equals a fresh packaged install of the same release.

### Step 1: model state (local settings)

```sh
python manage.py makemigrations django_clerk_users --check --dry-run
python manage.py migrate --check
```

Both must exit 0.

### Step 2: recorded graph

```sql
SELECT name FROM django_migrations WHERE app = 'django_clerk_users' ORDER BY id;
```

Expect the shared `0001` to `0003` names followed by your local names. Note
which packaged names are absent (normally `0004_clerkuser_username_index_state`
and `0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more`).

### Step 3: database schema

Run this against production (or its staging copy) and against an empty scratch
database where you ran `migrate` with packaged migrations and the same
package and Django versions:

```sql
-- Columns, constraints, and indexes of the Clerk user table (PostgreSQL).
-- Replace django_clerk_users_clerkuser if you subclass AbstractClerkUser.
SELECT 'column' AS kind,
       column_name AS name,
       data_type || CASE WHEN is_nullable = 'YES' THEN ' NULL' ELSE ' NOT NULL' END
           AS definition
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'django_clerk_users_clerkuser'
UNION ALL
SELECT 'constraint', conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'django_clerk_users_clerkuser'::regclass
UNION ALL
SELECT 'index', indexname, indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename = 'django_clerk_users_clerkuser'
ORDER BY 1, 2;
```

Diff the two outputs. On PostgreSQL with the default `ClerkUser`, the
packaged result is:

<!-- expected-schema -->
```text
    kind    |                        name                         |                                                                     definition
------------+-----------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------
 column     | clerk_id                                            | character varying NULL
 column     | created_at                                          | timestamp with time zone NOT NULL
 column     | email                                               | character varying NULL
 column     | first_name                                          | character varying NOT NULL
 column     | id                                                  | bigint NOT NULL
 column     | image_url                                           | character varying NOT NULL
 column     | is_active                                           | boolean NOT NULL
 column     | is_staff                                            | boolean NOT NULL
 column     | is_superuser                                        | boolean NOT NULL
 column     | last_login                                          | timestamp with time zone NULL
 column     | last_logout                                         | timestamp with time zone NULL
 column     | last_name                                           | character varying NOT NULL
 column     | password                                            | character varying NOT NULL
 column     | uid                                                 | uuid NOT NULL
 column     | updated_at                                          | timestamp with time zone NOT NULL
 column     | username                                            | character varying NULL
 constraint | django_clerk_users_clerkuser_clerk_id_key           | UNIQUE (clerk_id)
 constraint | django_clerk_users_clerkuser_email_key              | UNIQUE (email)
 constraint | django_clerk_users_clerkuser_pkey                   | PRIMARY KEY (id)
 constraint | django_clerk_users_clerkuser_uid_b28768d6_uniq      | UNIQUE (uid)
 constraint | django_clerk_users_clerkuser_username_key           | UNIQUE (username)
 index      | django_cler_is_acti_ceff9c_idx                      | CREATE INDEX django_cler_is_acti_ceff9c_idx ON public.django_clerk_users_clerkuser USING btree (is_active)
 index      | django_clerk_users_clerkuser_clerk_id_5c5c59aa_like | CREATE INDEX django_clerk_users_clerkuser_clerk_id_5c5c59aa_like ON public.django_clerk_users_clerkuser USING btree (clerk_id varchar_pattern_ops)
 index      | django_clerk_users_clerkuser_clerk_id_key           | CREATE UNIQUE INDEX django_clerk_users_clerkuser_clerk_id_key ON public.django_clerk_users_clerkuser USING btree (clerk_id)
 index      | django_clerk_users_clerkuser_email_5a8a3939_like    | CREATE INDEX django_clerk_users_clerkuser_email_5a8a3939_like ON public.django_clerk_users_clerkuser USING btree (email varchar_pattern_ops)
 index      | django_clerk_users_clerkuser_email_key              | CREATE UNIQUE INDEX django_clerk_users_clerkuser_email_key ON public.django_clerk_users_clerkuser USING btree (email)
 index      | django_clerk_users_clerkuser_pkey                   | CREATE UNIQUE INDEX django_clerk_users_clerkuser_pkey ON public.django_clerk_users_clerkuser USING btree (id)
 index      | django_clerk_users_clerkuser_uid_b28768d6_uniq      | CREATE UNIQUE INDEX django_clerk_users_clerkuser_uid_b28768d6_uniq ON public.django_clerk_users_clerkuser USING btree (uid)
 index      | django_clerk_users_clerkuser_username_89469527_like | CREATE INDEX django_clerk_users_clerkuser_username_89469527_like ON public.django_clerk_users_clerkuser USING btree (username varchar_pattern_ops)
 index      | django_clerk_users_clerkuser_username_key           | CREATE UNIQUE INDEX django_clerk_users_clerkuser_username_key ON public.django_clerk_users_clerkuser USING btree (username)
```

A leftover `django_cler_usernam_323ad9_idx` means your 0005 removed the
username index in state only. Drop it (with `migrations.RunSQL` in a new local
migration, or once by hand) and repeat step 3. Any other difference is a
precondition failure: resolve it in your local chain first.

### Step 4: switch settings and inspect the plan

Remove `django_clerk_users` from `MIGRATION_MODULES`, then:

```sh
python manage.py showmigrations django_clerk_users
```

`0001` to `0003` must show `[X]`. Only the packaged migrations you verified as
equivalent (normally `0004` and `0005`) may show `[ ]`.

### Step 5: record the verified migrations

```sh
python manage.py migrate django_clerk_users 0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more --fake
python manage.py migrate
python manage.py migrate --check
python manage.py makemigrations --check --dry-run
```

`--fake` here only records migrations whose effects steps 1 to 3 proved are
already in the database. Never fake a migration you have not verified, and never
fake past the last migration your local chain covered: the plain `migrate`
applies any newer packaged migrations for real.

Leave the old local rows (`0004_clerkuser_username_index`,
`0005_clerkuser_unique_uid`) in `django_migrations`. Django ignores recorded
names that are not in the graph, and they keep the history accurate if you
ever need to restore the old settings.

### What this does not change

- `AUTH_USER_MODEL` and the user table name.
- Primary keys, so foreign keys and many-to-many rows from other apps keep
  pointing at the same users.
- Existing UIDs, except duplicates already rewritten by your 0005 (the lowest
  primary key keeps the shared value).

The test seeds users with a duplicated UID, group memberships, and a protected
foreign key from another app before UID uniqueness, then checks all of them
after the switch, along with a live unique constraint on `uid`.
