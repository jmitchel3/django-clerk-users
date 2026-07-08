"""
Tests for data-preserving schema migrations.
"""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

USER_UID_BEFORE = ("django_clerk_users", "0004_clerkuser_username_index_state")
USER_UID_AFTER = (
    "django_clerk_users",
    "0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more",
)
ORG_UID_BEFORE = ("clerk_organizations", "0001_initial")
ORG_UID_AFTER = (
    "clerk_organizations",
    "0002_remove_organization_clerk_organ_clerk_i_b2b811_idx_and_more",
)


def _migrate_to(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def _migrate_to_latest():
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_clerk_user_uid_unique_migration_deduplicates_existing_values():
    """Test the user uid uniqueness migration repairs pre-existing duplicates."""
    try:
        apps = _migrate_to([USER_UID_BEFORE])
        ClerkUser = apps.get_model("django_clerk_users", "ClerkUser")

        duplicate_uid = uuid.uuid4()
        ClerkUser.objects.create(
            password="!",
            clerk_id="user_duplicate_uid_one",
            email="duplicate-one@example.com",
            uid=duplicate_uid,
        )
        ClerkUser.objects.create(
            password="!",
            clerk_id="user_duplicate_uid_two",
            email="duplicate-two@example.com",
            uid=duplicate_uid,
        )

        apps = _migrate_to([USER_UID_AFTER])
        ClerkUser = apps.get_model("django_clerk_users", "ClerkUser")
        migrated_uids = list(
            ClerkUser.objects.filter(
                clerk_id__in=["user_duplicate_uid_one", "user_duplicate_uid_two"]
            )
            .order_by("clerk_id")
            .values_list("uid", flat=True)
        )

        assert len(migrated_uids) == 2
        assert len(set(migrated_uids)) == 2
        assert duplicate_uid in migrated_uids
    finally:
        _migrate_to_latest()


@pytest.mark.django_db(transaction=True)
def test_organization_uid_unique_migration_deduplicates_existing_values():
    """Test the organization uid uniqueness migration repairs duplicates."""
    try:
        apps = _migrate_to([ORG_UID_BEFORE])
        Organization = apps.get_model("clerk_organizations", "Organization")

        duplicate_uid = uuid.uuid4()
        Organization.objects.create(
            clerk_id="org_duplicate_uid_one",
            name="Duplicate UID One",
            slug="duplicate-uid-one",
            uid=duplicate_uid,
        )
        Organization.objects.create(
            clerk_id="org_duplicate_uid_two",
            name="Duplicate UID Two",
            slug="duplicate-uid-two",
            uid=duplicate_uid,
        )

        apps = _migrate_to([ORG_UID_AFTER])
        Organization = apps.get_model("clerk_organizations", "Organization")
        migrated_uids = list(
            Organization.objects.filter(
                clerk_id__in=["org_duplicate_uid_one", "org_duplicate_uid_two"]
            )
            .order_by("clerk_id")
            .values_list("uid", flat=True)
        )

        assert len(migrated_uids) == 2
        assert len(set(migrated_uids)) == 2
        assert duplicate_uid in migrated_uids
    finally:
        _migrate_to_latest()
