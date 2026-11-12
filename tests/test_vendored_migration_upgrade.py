"""
Reproducible PostgreSQL upgrade for consumers with a vendored migration chain.

Backs docs/recipes/vendored-migrations.md. Skipped unless
DJANGO_CLERK_USERS_POSTGRES_URL points at a server where the test may create
and drop databases, for example:

    DJANGO_CLERK_USERS_POSTGRES_URL=postgres://postgres@127.0.0.1:5432/postgres \\
        uv run --with "psycopg[binary]" python -m pytest \\
        tests/test_vendored_migration_upgrade.py

Each Django step runs in a fresh subprocess with
tests/vendored_upgrade/settings.py, so MIGRATION_MODULES really changes between
steps the way it does when a project edits its settings.
"""

import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest

ADMIN_URL = os.environ.get("DJANGO_CLERK_USERS_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="DJANGO_CLERK_USERS_POSTGRES_URL not set"
)
psycopg = pytest.importorskip("psycopg") if ADMIN_URL else None

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "recipes" / "vendored-migrations.md"
SCHEMA_SQL = (ROOT / "docs" / "recipes" / "clerk_user_schema.sql").read_text()
APP = "django_clerk_users"
UPSTREAM_0005 = "0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more"
SHARED = [
    "0001_initial",
    "0002_make_clerk_id_nullable",
    "0003_add_username_make_email_nullable",
]
LOCAL = SHARED + ["0004_clerkuser_username_index", "0005_clerkuser_unique_uid"]
PACKAGED = SHARED + ["0004_clerkuser_username_index_state", UPSTREAM_0005]

DUP_UID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SEED = """
import uuid
from django.contrib.auth.models import Group
from django_clerk_users.models import ClerkUser
from tests.vendored_upgrade.legacy_app.models import Note

dup = uuid.UUID("{dup}")
users = ClerkUser.objects.bulk_create([
    ClerkUser(pk=101, clerk_id="user_a", email="a@example.com", uid=dup),
    ClerkUser(pk=102, clerk_id="user_b", email="b@example.com", uid=dup),
    ClerkUser(pk=103, clerk_id=None, email="admin@example.com", username="admin",
              uid=uuid.UUID("22222222-2222-4222-8222-222222222222")),
])
staff = Group.objects.create(name="staff")
for user in users:
    user.groups.add(staff)
    Note.objects.create(owner=user, body=f"note for {{user.pk}}")
""".format(dup=DUP_UID)


def db_url(name):
    parts = urlparse(ADMIN_URL)
    return urlunparse(parts._replace(path=f"/{name}"))


def admin_exec(sql):
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql)


@pytest.fixture
def make_db():
    created = []

    def make(suffix):
        name = f"clerk_vendored_{suffix}_{uuid.uuid4().hex[:8]}"
        admin_exec(f'CREATE DATABASE "{name}"')
        created.append(name)
        return name

    yield make
    for name in created:
        admin_exec(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def django(db, *args, legacy=None, check=True):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "tests.vendored_upgrade.settings",
        "DJANGO_CLERK_USERS_POSTGRES_URL": db_url(db),
    }
    env.pop("LEGACY_CLERK_MIGRATIONS", None)
    if legacy:
        env["LEGACY_CLERK_MIGRATIONS"] = legacy
    result = subprocess.run(
        [sys.executable, "-m", "django", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"django {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
        )
    return result


def query(db, sql):
    with psycopg.connect(db_url(db)) as conn:
        return conn.execute(sql).fetchall()


def schema(db):
    return query(db, SCHEMA_SQL)


def recorded(db):
    return [
        row[0]
        for row in query(
            db, f"SELECT name FROM django_migrations WHERE app = '{APP}' ORDER BY id"
        )
    ]


def references(db):
    return {
        "users": query(
            db,
            "SELECT id, clerk_id, email, uid FROM django_clerk_users_clerkuser "
            "ORDER BY id",
        ),
        "notes": query(
            db, "SELECT id, owner_id, body FROM legacy_app_note ORDER BY id"
        ),
        "groups": query(
            db,
            "SELECT clerkuser_id, group_id FROM django_clerk_users_clerkuser_groups "
            "ORDER BY clerkuser_id",
        ),
    }


def legacy_install(make_db, flavor):
    """A 0.2.x install with a vendored chain, seeded before UID uniqueness."""
    db = make_db(flavor)
    django(db, "migrate", APP, "0003", legacy=flavor)
    django(db, "migrate", "auth", legacy=flavor)
    django(db, "migrate", "legacy_app", legacy=flavor)
    django(db, "shell", "-c", SEED, legacy=flavor)
    django(db, "migrate", legacy=flavor)
    return db


def test_fresh_install_matches_documented_schema(make_db):
    db = make_db("fresh")
    django(db, "migrate")
    django(db, "makemigrations", "--check", "--dry-run")
    assert recorded(db) == PACKAGED
    assert schema(db) == documented_schema()


def test_vendored_chain_returns_to_packaged_migrations(make_db):
    fresh = make_db("expected")
    django(fresh, "migrate")
    expected = schema(fresh)

    db = legacy_install(make_db, "local")
    before = references(db)

    # Step 1: model state. The local chain must already be clean.
    django(db, "makemigrations", "--check", "--dry-run", legacy="local")
    # Step 2: recorded graph. Same schema, different migration identities.
    assert recorded(db) == LOCAL
    # Step 3: schema. Matches a fresh packaged install exactly.
    assert schema(db) == expected

    # Step 4: switch settings to packaged migrations and inspect the plan.
    plan = django(db, "showmigrations", APP).stdout
    for name in SHARED:
        assert f"[X] {name}" in plan
    assert "[ ] 0004_clerkuser_username_index_state" in plan
    assert f"[ ] {UPSTREAM_0005}" in plan

    # Step 5: record only the two verified-equivalent upstream migrations.
    django(db, "migrate", APP, UPSTREAM_0005, "--fake")
    django(db, "migrate")
    django(db, "migrate", "--check")
    django(db, "makemigrations", "--check", "--dry-run")

    assert recorded(db) == LOCAL + PACKAGED[3:]
    assert schema(db) == expected
    after = references(db)
    assert after == before
    pks = [row[0] for row in after["users"]]
    assert pks == [101, 102, 103]
    uids = [row[3] for row in after["users"]]
    assert len(set(uids)) == 3
    assert uids[0] == DUP_UID  # lowest pk keeps the shared uid

    # The UID constraint is live after the switch.
    with pytest.raises(psycopg.errors.UniqueViolation):
        query(
            db,
            "INSERT INTO django_clerk_users_clerkuser (password, is_superuser, uid, "
            "clerk_id, email, first_name, last_name, image_url, is_active, is_staff, "
            "created_at, updated_at) VALUES ('', false, "
            f"'{DUP_UID}', 'user_c', 'c@example.com', '', '', '', true, false, "
            "now(), now())",
        )


def test_drifted_port_is_caught_by_schema_comparison(make_db):
    fresh = make_db("expected")
    django(fresh, "migrate")
    expected = schema(fresh)

    db = legacy_install(make_db, "drift")
    # Model state looks fine, so makemigrations alone would not catch it.
    django(db, "makemigrations", "--check", "--dry-run", legacy="drift")

    extra = set(schema(db)) - set(expected)
    assert {row[1] for row in extra} == {"django_cler_usernam_323ad9_idx"}
    assert set(expected) <= set(schema(db))

    # Documented fix: drop the leftover index, then the schemas match.
    query_autocommit(db, 'DROP INDEX IF EXISTS "django_cler_usernam_323ad9_idx"')
    assert schema(db) == expected


def test_retaining_the_local_chain_is_stable(make_db):
    db = legacy_install(make_db, "local")
    django(db, "migrate", "--check", legacy="local")
    django(db, "makemigrations", "--check", "--dry-run", legacy="local")
    assert recorded(db) == LOCAL


def query_autocommit(db, sql):
    with psycopg.connect(db_url(db), autocommit=True) as conn:
        conn.execute(sql)


def documented_schema():
    text = DOC.read_text()
    block = re.search(r"<!-- expected-schema -->\n```text\n(.*?)```", text, re.S).group(
        1
    )
    rows = []
    for line in block.strip().splitlines()[2:]:
        kind, name, definition = (part.strip() for part in line.split("|", 2))
        rows.append((kind, name, definition))
    return rows


def test_doc_embeds_schema_query():
    assert SCHEMA_SQL in DOC.read_text()
