"""
Tests for django-clerk-users management commands.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import textwrap
import warnings
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from django_clerk_users.exceptions import ClerkConfigurationError


class StructuredDuplicateEmailError(Exception):
    """Minimal Clerk SDK error shape for duplicate identifier responses."""

    def __init__(self):
        super().__init__("identifier already exists")
        self.data = {
            "errors": [
                {
                    "code": "form_identifier_exists",
                    "meta": {"param_names": ["email_address"]},
                }
            ]
        }


def test_sync_clerk_users_rejects_invalid_pagination_before_api_call(db):
    """Test user sync rejects pagination that cannot advance safely."""
    with patch(
        "django_clerk_users.management.commands.sync_clerk_users.get_clerk_client"
    ) as get_client:
        with pytest.raises(CommandError, match="--limit must be greater than zero"):
            call_command("sync_clerk_users", limit=0)

        with pytest.raises(CommandError, match="--offset must be zero or greater"):
            call_command("sync_clerk_users", offset=-1)

    get_client.assert_not_called()


def test_sync_clerk_organizations_rejects_invalid_pagination_before_api_call(db):
    """Test organization sync rejects pagination that cannot advance safely."""
    with patch(
        "django_clerk_users.management.commands.sync_clerk_organizations.get_clerk_client"
    ) as get_client:
        with pytest.raises(CommandError, match="--limit must be greater than zero"):
            call_command("sync_clerk_organizations", limit=0)

        with pytest.raises(CommandError, match="--offset must be zero or greater"):
            call_command("sync_clerk_organizations", offset=-1)

    get_client.assert_not_called()


def test_migrate_users_to_clerk_rejects_invalid_limit_before_api_call(db):
    """Test migration rejects a non-positive limit before contacting Clerk."""
    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client"
    ) as get_client:
        with pytest.raises(CommandError, match="--limit must be greater than zero"):
            call_command(
                "migrate_users_to_clerk",
                source_model="django_clerk_users.ClerkUser",
                all=True,
                limit=0,
            )

    get_client.assert_not_called()


def test_sync_clerk_organizations_reports_missing_optional_app():
    """Test org sync reports a clean error when the org app is not installed."""
    code = textwrap.dedent(
        """
        import io

        from django.conf import settings

        settings.configure(
            SECRET_KEY="org-command-test",
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "django_clerk_users",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            AUTH_USER_MODEL="django_clerk_users.ClerkUser",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            USE_TZ=True,
            CLERK_SECRET_KEY="sk_test_mock_secret_key",
        )

        import django
        django.setup()

        from django.core.management import call_command

        stderr = io.StringIO()
        call_command("sync_clerk_organizations", limit=1, stderr=stderr)

        assert "Organizations app is not installed" in stderr.getvalue()
        """
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(["src", "."])}

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_sync_clerk_users_uses_current_user_list_request_shape(db):
    """Test user sync calls the Clerk SDK with its current list signature."""
    client = MagicMock()
    client.users.list.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                id="user_sync123",
                email_addresses=[
                    SimpleNamespace(email_address="sync@example.com"),
                ],
                username=None,
            )
        ]
    )
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.sync_clerk_users.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "sync_clerk_users",
            limit=5,
            offset=10,
            dry_run=True,
            stdout=stdout,
        )

    client.users.list.assert_called_once_with(
        request={"limit": 5, "offset": 10},
        timeout_ms=10000,
    )
    assert "Would sync: sync@example.com" in stdout.getvalue()


def test_sync_clerk_users_raises_on_list_failure(db):
    """Test user sync fails the command when the Clerk list call fails."""
    client = MagicMock()
    client.users.list.side_effect = RuntimeError("Clerk unavailable")

    with patch(
        "django_clerk_users.management.commands.sync_clerk_users.get_clerk_client",
        return_value=client,
    ):
        with pytest.raises(CommandError, match="Failed to fetch users"):
            call_command("sync_clerk_users", stdout=io.StringIO())


def test_sync_clerk_organizations_raises_on_list_failure(db):
    """Test organization sync fails the command when the Clerk list call fails."""
    client = MagicMock()
    client.organizations.list.side_effect = RuntimeError("Clerk unavailable")

    with patch(
        "django_clerk_users.management.commands.sync_clerk_organizations.get_clerk_client",
        return_value=client,
    ):
        with pytest.raises(CommandError, match="Failed to fetch organizations"):
            call_command("sync_clerk_organizations", stdout=io.StringIO())


def test_sync_clerk_organizations_uses_timeout_for_page_fetch(db):
    """Test organization sync passes configured timeout options to Clerk list."""
    client = MagicMock()
    client.organizations.list.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(id="org_sync123", name="Sync Org"),
        ]
    )

    with patch(
        "django_clerk_users.management.commands.sync_clerk_organizations.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "sync_clerk_organizations",
            limit=7,
            offset=14,
            dry_run=True,
            stdout=io.StringIO(),
        )

    client.organizations.list.assert_called_once_with(
        limit=7,
        offset=14,
        timeout_ms=10000,
    )


def test_migrate_users_to_clerk_uses_current_user_lookup_request_shape(db):
    """Test migration lookup calls users.list with a request payload."""
    User = get_user_model()
    User.objects.create_user(email="existing@example.com")

    client = MagicMock()
    client.users.list.return_value = SimpleNamespace(
        data=[SimpleNamespace(id="user_existing")]
    )
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email="existing@example.com",
            skip_existing=True,
            dry_run=True,
            stdout=stdout,
        )

    client.users.list.assert_called_once_with(
        request={"email_address": ["existing@example.com"], "limit": 1},
        timeout_ms=10000,
    )
    assert "Would skip (exists in Clerk): existing@example.com" in stdout.getvalue()


def test_migrate_users_to_clerk_links_existing_dict_response(db):
    """Test migration links source users when Clerk list returns dict data."""
    User = get_user_model()
    source_user = User.objects.create_user(email="dict-existing@example.com")

    client = MagicMock()
    client.users.list.return_value = {
        "data": [{"id": "user_dict_existing"}],
    }
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email=source_user.email,
            skip_existing=True,
            stdout=stdout,
        )

    source_user.refresh_from_db()
    assert source_user.clerk_id == "user_dict_existing"
    assert "Linked existing: 1" in stdout.getvalue()


def test_migrate_users_to_clerk_created_before_uses_aware_model_timestamp(db):
    """Test created-before works for ClerkUser.created_at without TZ warnings."""
    User = get_user_model()
    old_user = User.objects.create_user(
        email="old-created@example.com",
        created_at=timezone.make_aware(datetime(2024, 1, 1)),
    )
    new_user = User.objects.create_user(
        email="new-created@example.com",
        created_at=timezone.make_aware(datetime(2026, 1, 1)),
    )

    client = MagicMock()
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            call_command(
                "migrate_users_to_clerk",
                source_model="django_clerk_users.ClerkUser",
                created_before="2025-01-01",
                dry_run=True,
                stdout=stdout,
            )

    output = stdout.getvalue()
    assert f"Would create: {old_user.email}" in output
    assert new_user.email not in output
    assert not any(
        "received a naive datetime" in str(warning.message)
        for warning in caught_warnings
    )
    client.users.create.assert_not_called()


def test_migrate_users_to_clerk_uses_timeout_for_user_create(db):
    """Test migration create calls pass configured timeout options to Clerk."""
    User = get_user_model()
    source_user = User.objects.create_user(
        email="create-timeout@example.com",
        first_name="Create",
        last_name="Timeout",
    )

    client = MagicMock()
    client.users.create.return_value = SimpleNamespace(id="user_create_timeout")

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email=source_user.email,
            stdout=io.StringIO(),
        )

    client.users.create.assert_called_once_with(
        email_address=["create-timeout@example.com"],
        first_name="Create",
        last_name="Timeout",
        skip_password_requirement=True,
        skip_password_checks=True,
        timeout_ms=10000,
    )


def test_migrate_users_to_clerk_links_after_duplicate_create_race(db):
    """Test structured duplicate create errors recover by linking existing Clerk user."""
    User = get_user_model()
    source_user = User.objects.create_user(email="race-existing@example.com")

    client = MagicMock()
    client.users.create.side_effect = StructuredDuplicateEmailError()
    client.users.list.return_value = SimpleNamespace(
        data=[SimpleNamespace(id="user_race_existing")]
    )
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email=source_user.email,
            stdout=stdout,
        )

    client.users.list.assert_called_once_with(
        request={"email_address": ["race-existing@example.com"], "limit": 1},
        timeout_ms=10000,
    )
    source_user.refresh_from_db()
    assert source_user.clerk_id == "user_race_existing"
    assert (
        "Email already exists in Clerk: race-existing@example.com" in stdout.getvalue()
    )
    assert "Linked existing: 1" in stdout.getvalue()
    assert "Skipped: 1" in stdout.getvalue()
    assert "Errors: 0" in stdout.getvalue()


def test_migrate_users_to_clerk_does_not_create_after_lookup_failure(db):
    """Test skip-existing lookup failures do not fall through to user creation."""
    User = get_user_model()
    User.objects.create_user(email="lookup-fails@example.com")

    client = MagicMock()
    client.users.list.side_effect = RuntimeError("lookup failed")
    stderr = io.StringIO()
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email="lookup-fails@example.com",
            skip_existing=True,
            stderr=stderr,
            stdout=stdout,
        )

    client.users.create.assert_not_called()
    assert "Error checking if lookup-fails@example.com exists" in stderr.getvalue()
    assert "Errors: 1" in stdout.getvalue()


@pytest.mark.django_db
def test_sync_organization_members_uses_current_membership_sdk():
    """Test organization member sync uses organization_memberships.list."""
    from django_clerk_users.management.commands.sync_clerk_organizations import (
        Command,
    )
    from django_clerk_users.organizations.models import Organization, OrganizationMember

    User = get_user_model()
    clerk_user = User.objects.create_user(
        clerk_id="user_member_sync",
        email="member-sync@example.com",
    )
    organization = Organization.objects.create(
        clerk_id="org_member_sync",
        name="Member Sync",
        slug="member-sync",
    )

    client = MagicMock()
    first_page = [
        SimpleNamespace(id=f"mem_skip_{index}", public_user_data=None, role="member")
        for index in range(100)
    ]
    second_page = [
        SimpleNamespace(
            id="mem_sdk123",
            public_user_data=SimpleNamespace(user_id=clerk_user.clerk_id),
            role="admin",
        )
    ]
    client.organization_memberships.list.side_effect = [
        SimpleNamespace(data=first_page),
        SimpleNamespace(data=second_page),
    ]
    command = Command(stdout=io.StringIO(), stderr=io.StringIO())

    with patch("django_clerk_users.client.get_clerk_client", return_value=client):
        command._sync_organization_members(
            organization,
            organization.clerk_id,
            dry_run=False,
        )

    assert client.organization_memberships.list.call_args_list == [
        call(
            organization_id=organization.clerk_id,
            limit=100,
            offset=0,
            timeout_ms=10000,
        ),
        call(
            organization_id=organization.clerk_id,
            limit=100,
            offset=100,
            timeout_ms=10000,
        ),
    ]
    assert OrganizationMember.objects.filter(
        clerk_membership_id="mem_sdk123",
        organization=organization,
        user=clerk_user,
        role="admin",
    ).exists()


def test_migrate_users_rejects_invalid_source_model_and_missing_selector(db):
    with pytest.raises(CommandError, match="Invalid source model"):
        call_command("migrate_users_to_clerk", source_model="invalid-model")

    with pytest.raises(CommandError, match="You must specify"):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
        )


def test_migrate_users_reports_missing_clerk_configuration(db):
    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        side_effect=ClerkConfigurationError("missing"),
    ):
        with pytest.raises(CommandError, match="CLERK_SECRET_KEY is not configured"):
            call_command(
                "migrate_users_to_clerk",
                source_model="django_clerk_users.ClerkUser",
                all=True,
            )


def test_migrate_users_skips_users_without_email(db):
    User = get_user_model()
    source_user = User.objects.create_user(
        clerk_id="source-email-less", username="email-less"
    )
    client = MagicMock()
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            all=True,
            stdout=stdout,
            stderr=stderr,
        )

    assert f"Skipping user {source_user.pk}: no email" in stderr.getvalue()
    assert "Skipped: 1" in stdout.getvalue()
    client.users.create.assert_not_called()


def test_migrate_users_creates_when_skip_existing_lookup_is_empty(db):
    User = get_user_model()
    source_user = User.objects.create_user(email="new-after-lookup@example.com")
    client = MagicMock()
    client.users.list.return_value = SimpleNamespace(data=[])
    client.users.create.return_value = SimpleNamespace(id="user_new_after_lookup")

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            all=True,
            skip_existing=True,
            stdout=io.StringIO(),
        )

    source_user.refresh_from_db()
    assert source_user.clerk_id == "user_new_after_lookup"
    client.users.create.assert_called_once()


def test_migrate_users_reports_duplicate_lookup_failure(db):
    User = get_user_model()
    source_user = User.objects.create_user(email="duplicate-lookup@example.com")
    client = MagicMock()
    client.users.create.side_effect = StructuredDuplicateEmailError()
    client.users.list.side_effect = RuntimeError("lookup unavailable")
    stderr = io.StringIO()
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email=source_user.email,
            stdout=stdout,
            stderr=stderr,
        )

    assert "Error linking existing Clerk user" in stderr.getvalue()
    assert "Errors: 1" in stdout.getvalue()
    assert "Skipped: 1" in stdout.getvalue()


def test_migrate_users_handles_duplicate_without_lookup_match(db):
    User = get_user_model()
    source_user = User.objects.create_user(email="duplicate-gone@example.com")
    client = MagicMock()
    client.users.create.side_effect = StructuredDuplicateEmailError()
    client.users.list.return_value = SimpleNamespace(data=[])
    stdout = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email=source_user.email,
            stdout=stdout,
        )

    assert "Linked existing: 0" in stdout.getvalue()
    assert "Skipped: 1" in stdout.getvalue()


def test_migrate_users_reports_nonduplicate_creation_failure(db):
    User = get_user_model()
    source_user = User.objects.create_user(email="create-fails@example.com")
    client = MagicMock()
    client.users.create.side_effect = RuntimeError("service unavailable")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch(
        "django_clerk_users.management.commands.migrate_users_to_clerk.get_clerk_client",
        return_value=client,
    ):
        call_command(
            "migrate_users_to_clerk",
            source_model="django_clerk_users.ClerkUser",
            email=source_user.email,
            stdout=stdout,
            stderr=stderr,
        )

    assert "Failed to create create-fails@example.com" in stderr.getvalue()
    assert "Errors: 1" in stdout.getvalue()


def test_migrate_users_helper_edge_cases():
    from django_clerk_users.management.commands.migrate_users_to_clerk import Command

    command = Command(stdout=io.StringIO())

    with pytest.raises(CommandError, match="Invalid date format"):
        command._parse_created_before("01/02/2025")

    class MetaWithoutCreationFields:
        def get_field(self, field_name):
            raise FieldDoesNotExist(field_name)

    source_model = SimpleNamespace(_meta=MetaWithoutCreationFields())
    with pytest.raises(CommandError, match="date_joined or created_at"):
        command._created_before_field(source_model)

    assert command._is_duplicate_email_error(
        RuntimeError("email_address already exists")
    )
    assert not command._is_duplicate_email_error(RuntimeError("request failed"))

    source_without_clerk_id = SimpleNamespace()
    command._link_user(source_without_clerk_id, {"id": "user_123"})
    command._link_user(source_without_clerk_id, {})


@override_settings(USE_TZ=False)
def test_migrate_created_before_remains_naive_without_timezone_support():
    from django_clerk_users.management.commands.migrate_users_to_clerk import Command

    result = Command._parse_created_before("2025-01-02")

    assert timezone.is_naive(result)


def test_sync_users_reports_missing_clerk_configuration(db):
    with patch(
        "django_clerk_users.management.commands.sync_clerk_users.get_clerk_client",
        side_effect=ClerkConfigurationError("missing"),
    ):
        with pytest.raises(CommandError, match="CLERK_SECRET_KEY is not configured"):
            call_command("sync_clerk_users")


def test_sync_users_paginates_and_records_all_outcomes(db):
    client = MagicMock()
    users = [
        SimpleNamespace(id=None, email_addresses=[], username=None),
        SimpleNamespace(id="user_created", email_addresses=[], username="created"),
        SimpleNamespace(
            id="user_updated",
            email_addresses=[SimpleNamespace(email_address="updated@example.com")],
            username=None,
        ),
        SimpleNamespace(id="user_failed", email_addresses=[], username=None),
    ]
    client.users.list.side_effect = [
        SimpleNamespace(data=users),
        SimpleNamespace(data=[]),
    ]
    created_user = SimpleNamespace(
        email=None, username="created", clerk_id="user_created"
    )
    updated_user = SimpleNamespace(
        email="updated@example.com", username=None, clerk_id="user_updated"
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        patch(
            "django_clerk_users.management.commands.sync_clerk_users.get_clerk_client",
            return_value=client,
        ),
        patch(
            "django_clerk_users.management.commands.sync_clerk_users.update_or_create_clerk_user",
            side_effect=[
                (created_user, True),
                (updated_user, False),
                RuntimeError("sync failed"),
            ],
        ),
    ):
        call_command(
            "sync_clerk_users",
            limit=4,
            all=True,
            stdout=stdout,
            stderr=stderr,
        )

    assert client.users.list.call_args_list == [
        call(request={"limit": 4, "offset": 0}, timeout_ms=10000),
        call(request={"limit": 4, "offset": 4}, timeout_ms=10000),
    ]
    assert "No more users to sync" in stdout.getvalue()
    assert "Created: 1" in stdout.getvalue()
    assert "Updated: 1" in stdout.getvalue()
    assert "Errors: 2" in stdout.getvalue()
    assert "Failed to sync user_failed" in stderr.getvalue()


def test_sync_organizations_reports_missing_app_in_process(db):
    stderr = io.StringIO()

    with (
        patch(
            "django_clerk_users.management.commands.sync_clerk_organizations.apps.is_installed",
            return_value=False,
        ),
        patch(
            "django_clerk_users.management.commands.sync_clerk_organizations.get_clerk_client"
        ) as get_client,
    ):
        call_command("sync_clerk_organizations", stderr=stderr)

    assert "Organizations app is not installed" in stderr.getvalue()
    get_client.assert_not_called()


def test_sync_organizations_reports_missing_clerk_configuration(db):
    with patch(
        "django_clerk_users.management.commands.sync_clerk_organizations.get_clerk_client",
        side_effect=ClerkConfigurationError("missing"),
    ):
        with pytest.raises(CommandError, match="CLERK_SECRET_KEY is not configured"):
            call_command("sync_clerk_organizations")


def test_sync_organizations_paginates_and_records_all_outcomes(db):
    client = MagicMock()
    orgs = [
        SimpleNamespace(id=None, name="Missing ID"),
        SimpleNamespace(id="org_created", name="Created Org"),
        SimpleNamespace(id="org_updated", name="Updated Org"),
        SimpleNamespace(id="org_failed", name="Failed Org"),
    ]
    client.organizations.list.side_effect = [
        SimpleNamespace(data=orgs),
        SimpleNamespace(data=[]),
    ]
    created_org = SimpleNamespace(name="Created Org")

    class FalsyOrganization:
        name = "Updated Org"

        def __bool__(self):
            return False

    updated_org = FalsyOrganization()
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        patch(
            "django_clerk_users.management.commands.sync_clerk_organizations.get_clerk_client",
            return_value=client,
        ),
        patch(
            "django_clerk_users.organizations.webhooks.update_or_create_organization",
            side_effect=[
                (created_org, True),
                (updated_org, False),
                RuntimeError("sync failed"),
            ],
        ),
        patch(
            "django_clerk_users.management.commands.sync_clerk_organizations.Command._sync_organization_members"
        ) as sync_members,
    ):
        call_command(
            "sync_clerk_organizations",
            limit=4,
            all=True,
            sync_members=True,
            stdout=stdout,
            stderr=stderr,
        )

    assert client.organizations.list.call_args_list == [
        call(limit=4, offset=0, timeout_ms=10000),
        call(limit=4, offset=4, timeout_ms=10000),
    ]
    sync_members.assert_called_once_with(created_org, "org_created", False)
    assert "No more organizations to sync" in stdout.getvalue()
    assert "Created: 1" in stdout.getvalue()
    assert "Updated: 1" in stdout.getvalue()
    assert "Errors: 2" in stdout.getvalue()
    assert "Failed to sync Failed Org" in stderr.getvalue()


@pytest.mark.django_db
def test_sync_organization_members_handles_fetch_empty_and_dry_run():
    from django_clerk_users.management.commands.sync_clerk_organizations import (
        Command,
    )
    from django_clerk_users.organizations.models import Organization

    organization = Organization.objects.create(
        clerk_id="org_member_edges", name="Edges", slug="edges"
    )
    command = Command(stdout=io.StringIO(), stderr=io.StringIO())
    client = MagicMock()
    client.organization_memberships.list.side_effect = RuntimeError("fetch failed")

    with patch("django_clerk_users.client.get_clerk_client", return_value=client):
        command._sync_organization_members(organization, organization.clerk_id, False)
    assert "Failed to fetch members" in command.stderr.getvalue()

    command.stderr = io.StringIO()
    client.organization_memberships.list.side_effect = None
    client.organization_memberships.list.return_value = SimpleNamespace(data=[])
    with patch("django_clerk_users.client.get_clerk_client", return_value=client):
        command._sync_organization_members(organization, organization.clerk_id, False)

    membership = SimpleNamespace(
        id="mem_dry",
        public_user_data=SimpleNamespace(user_id="user_dry"),
        role="member",
    )
    client.organization_memberships.list.return_value = SimpleNamespace(
        data=[membership]
    )
    with patch("django_clerk_users.client.get_clerk_client", return_value=client):
        command._sync_organization_members(organization, organization.clerk_id, True)
    assert "Would sync member: user_dry" in command.stdout.getvalue()


@pytest.mark.django_db
def test_sync_organization_members_creates_missing_user_and_reports_write_error():
    from django_clerk_users.management.commands.sync_clerk_organizations import (
        Command,
    )
    from django_clerk_users.organizations.models import Organization, OrganizationMember

    User = get_user_model()
    created_user = User.objects.create_user(
        clerk_id="user_member_created", email="created-member@example.com"
    )
    organization = Organization.objects.create(
        clerk_id="org_member_create", name="Create", slug="create"
    )
    client = MagicMock()
    client.organization_memberships.list.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                id="mem_create",
                public_user_data=SimpleNamespace(user_id="remote_missing_user"),
                role="admin",
            )
        ]
    )
    command = Command(stdout=io.StringIO(), stderr=io.StringIO())

    with (
        patch("django_clerk_users.client.get_clerk_client", return_value=client),
        patch(
            "django_clerk_users.utils.update_or_create_clerk_user",
            return_value=(created_user, True),
        ) as create_user,
    ):
        command._sync_organization_members(organization, organization.clerk_id, False)

    create_user.assert_called_once_with("remote_missing_user")
    assert OrganizationMember.objects.filter(clerk_membership_id="mem_create").exists()

    with (
        patch("django_clerk_users.client.get_clerk_client", return_value=client),
        patch(
            "django_clerk_users.utils.update_or_create_clerk_user",
            return_value=(created_user, False),
        ),
        patch.object(
            OrganizationMember.objects,
            "update_or_create",
            side_effect=RuntimeError("write failed"),
        ),
    ):
        command._sync_organization_members(organization, organization.clerk_id, False)

    assert "Failed to sync member remote_missing_user" in command.stderr.getvalue()
