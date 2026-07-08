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
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone


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
