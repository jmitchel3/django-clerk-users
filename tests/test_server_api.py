"""
Tests for django_clerk_users.server_api helpers.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from django.test import override_settings

from django_clerk_users import server_api


class FakeClerkIdentifierError(Exception):
    """Small stand-in for the Clerk SDK's structured error response."""

    status_code = 422

    def __init__(self, *, params=None):
        super().__init__("identifier already exists")
        self.data = SimpleNamespace(
            errors=[
                SimpleNamespace(
                    code="form_identifier_exists",
                    meta={"param_names": params or []},
                )
            ]
        )


def make_client():
    client = MagicMock()
    client.users = MagicMock()
    client.sign_in_tokens = MagicMock()
    client.sessions = MagicMock()
    client.email_addresses = MagicMock()
    client.invitations = MagicMock()
    return client


def test_derive_clerk_username_sanitizes_email_local_part():
    with patch(
        "django_clerk_users.server_api.secrets.token_hex", return_value="abc123"
    ):
        username = server_api.derive_clerk_username("Ada.Lovelace+Staff@example.com")

    assert username == "adalovelacestaff_abc123"


def test_build_clerk_sign_in_url_adds_ticket_and_replaces_old_ticket():
    url = server_api.build_clerk_sign_in_url(
        "https://app.example.com/sign-in?next=/dashboard&__clerk_ticket=old",
        "ticket_new",
    )

    assert url == (
        "https://app.example.com/sign-in?next=%2Fdashboard&__clerk_ticket=ticket_new"
    )


@override_settings(CLERK_API_TIMEOUT_MS=12345)
def test_create_clerk_user_passwordless_uses_sdk_and_setting_timeout():
    client = make_client()
    client.users.create.return_value = {"id": "user_123", "email_addresses": []}

    result = server_api.create_clerk_user(
        "ada@example.com",
        first_name="Ada",
        public_metadata={"role": "staff"},
        clerk_client=client,
    )

    assert result == {"id": "user_123", "email_addresses": []}
    client.users.create.assert_called_once_with(
        email_address=["ada@example.com"],
        first_name="Ada",
        last_name="",
        skip_password_requirement=True,
        public_metadata={"role": "staff"},
        timeout_ms=12345,
    )


@override_settings(CLERK_API_TIMEOUT_MS="invalid")
def test_create_clerk_user_uses_default_for_invalid_setting_timeout():
    client = make_client()
    client.users.create.return_value = {"id": "user_123"}

    result = server_api.create_clerk_user(
        "ada@example.com",
        clerk_client=client,
    )

    assert result == {"id": "user_123"}
    client.users.create.assert_called_once_with(
        email_address=["ada@example.com"],
        first_name="",
        last_name="",
        skip_password_requirement=True,
        timeout_ms=10_000,
    )


def test_create_clerk_user_with_password_skips_password_checks():
    client = make_client()
    client.users.create.return_value = {"id": "user_123"}

    server_api.create_clerk_user(
        "ada@example.com",
        password="local-password",
        username="ada",
        clerk_client=client,
        timeout_ms=999,
    )

    client.users.create.assert_called_once_with(
        email_address=["ada@example.com"],
        first_name="",
        last_name="",
        password="local-password",
        skip_password_checks=True,
        username="ada",
        timeout_ms=999,
    )


def test_create_clerk_user_uses_default_for_non_positive_timeout():
    client = make_client()
    client.users.create.return_value = {"id": "user_123"}

    result = server_api.create_clerk_user(
        "ada@example.com",
        clerk_client=client,
        timeout_ms=0,
    )

    assert result == {"id": "user_123"}
    client.users.create.assert_called_once_with(
        email_address=["ada@example.com"],
        first_name="",
        last_name="",
        skip_password_requirement=True,
        timeout_ms=10_000,
    )


@override_settings(CLERK_SECRET_KEY="abc123")
def test_create_clerk_user_returns_no_key_for_local_placeholder():
    assert server_api.create_clerk_user("ada@example.com") == {"no_key": True}


@override_settings(CLERK_SECRET_KEY="  sk_live_replace_me  ")
def test_create_clerk_user_returns_no_key_for_trimmed_placeholder():
    assert server_api.create_clerk_user("ada@example.com") == {"no_key": True}


@override_settings(CLERK_SECRET_KEY="  sk_test_unit_server_secret  ")
def test_create_clerk_user_trims_secret_before_creating_sdk_client():
    from django_clerk_users.client import get_clerk_client

    client = make_client()
    client.users.create.return_value = {"id": "user_123"}
    get_clerk_client.cache_clear()

    try:
        with patch("django_clerk_users.client.Clerk", return_value=client) as Clerk:
            result = server_api.create_clerk_user("ada@example.com")
    finally:
        get_clerk_client.cache_clear()

    assert result == {"id": "user_123"}
    Clerk.assert_called_once_with(bearer_auth="sk_test_unit_server_secret")


def test_create_clerk_user_returns_already_exists_for_duplicate_email():
    client = make_client()
    client.users.create.side_effect = FakeClerkIdentifierError(params=["email_address"])

    result = server_api.create_clerk_user("ada@example.com", clerk_client=client)

    assert result == {"already_exists": True, "email": "ada@example.com"}


def test_create_clerk_user_retries_derived_username_collision():
    client = make_client()
    client.users.create.side_effect = [
        FakeClerkIdentifierError(params=["username"]),
        {"id": "user_123", "username": "ada_two"},
    ]

    with patch(
        "django_clerk_users.server_api.derive_clerk_username",
        side_effect=["ada_one", "ada_two"],
    ):
        result = server_api.create_clerk_user(
            "ada@example.com",
            auto_username=True,
            clerk_client=client,
            timeout_ms=100,
        )

    assert result == {"id": "user_123", "username": "ada_two"}
    assert client.users.create.call_args_list == [
        call(
            email_address=["ada@example.com"],
            first_name="",
            last_name="",
            skip_password_requirement=True,
            timeout_ms=100,
            username="ada_one",
        ),
        call(
            email_address=["ada@example.com"],
            first_name="",
            last_name="",
            skip_password_requirement=True,
            timeout_ms=100,
            username="ada_two",
        ),
    ]


def test_get_clerk_user_by_email_returns_first_user():
    client = make_client()
    client.users.list.return_value = [{"id": "user_123"}, {"id": "user_456"}]

    result = server_api.get_clerk_user_by_email(
        "ada@example.com",
        clerk_client=client,
        timeout_ms=500,
    )

    assert result == {"id": "user_123"}
    client.users.list.assert_called_once_with(
        request={"email_address": ["ada@example.com"], "limit": 1},
        timeout_ms=500,
    )


def test_get_clerk_user_by_email_accepts_paginated_data_response():
    client = make_client()
    client.users.list.return_value = SimpleNamespace(data=[{"id": "user_123"}])

    result = server_api.get_clerk_user_by_email(
        "ada@example.com",
        clerk_client=client,
    )

    assert result == {"id": "user_123"}


def test_get_clerk_user_by_email_returns_none_for_empty_data_response():
    client = make_client()
    client.users.list.return_value = SimpleNamespace(data=[])

    result = server_api.get_clerk_user_by_email(
        "ada@example.com",
        clerk_client=client,
    )

    assert result is None


def test_create_clerk_sign_in_token_returns_token():
    client = make_client()
    client.sign_in_tokens.create.return_value = {"token": "ticket_123"}

    token = server_api.create_clerk_sign_in_token(
        "user_123",
        expires_in_seconds=3600,
        clerk_client=client,
    )

    assert token == "ticket_123"
    client.sign_in_tokens.create.assert_called_once_with(
        request={"user_id": "user_123", "expires_in_seconds": 3600},
        timeout_ms=10_000,
    )


def test_create_clerk_sign_in_token_returns_none_for_invalid_expiry():
    client = make_client()

    token = server_api.create_clerk_sign_in_token(
        "user_123",
        expires_in_seconds="bad",  # type: ignore[arg-type]
        clerk_client=client,
    )

    assert token is None
    client.sign_in_tokens.create.assert_not_called()


def test_create_clerk_sign_in_link_builds_link_from_token():
    client = make_client()
    client.sign_in_tokens.create.return_value = {"token": "ticket_123"}

    link = server_api.create_clerk_sign_in_link(
        "user_123",
        "https://app.example.com/sign-in",
        clerk_client=client,
    )

    assert link == "https://app.example.com/sign-in?__clerk_ticket=ticket_123"


def test_provision_clerk_user_access_link_resolves_existing_user():
    client = make_client()
    client.users.create.side_effect = FakeClerkIdentifierError(params=["email_address"])
    client.users.list.return_value = [{"id": "user_existing"}]
    client.sign_in_tokens.create.return_value = {"token": "ticket_123"}

    result = server_api.provision_clerk_user_access_link(
        "ada@example.com",
        "https://app.example.com/sign-in",
        clerk_client=client,
    )

    assert result == {
        "clerk_user_id": "user_existing",
        "access_link": "https://app.example.com/sign-in?__clerk_ticket=ticket_123",
        "sign_in_token": "ticket_123",
        "created": False,
        "already_exists": True,
        "no_key": False,
    }


@override_settings(CLERK_SECRET_KEY="abc123")
def test_provision_clerk_user_access_link_reports_no_key():
    result = server_api.provision_clerk_user_access_link(
        "ada@example.com",
        "https://app.example.com/sign-in",
    )

    assert result == {
        "clerk_user_id": None,
        "access_link": "",
        "sign_in_token": "",
        "created": False,
        "already_exists": False,
        "no_key": True,
    }


def test_update_clerk_user_public_metadata_merges_existing_metadata():
    client = make_client()
    client.users.get.return_value = {"public_metadata": {"old": "keep"}}

    result = server_api.update_clerk_user_public_metadata(
        "user_123",
        {"new": "value"},
        clerk_client=client,
        timeout_ms=250,
    )

    assert result is True
    client.users.update.assert_called_once_with(
        user_id="user_123",
        public_metadata={"old": "keep", "new": "value"},
        timeout_ms=250,
    )


def test_set_clerk_user_email_creates_primary_and_prunes_old_emails():
    client = make_client()
    client.email_addresses.create.return_value = {"id": "email_new"}
    client.users.get.return_value = {
        "email_addresses": [{"id": "email_old"}, {"id": "email_new"}]
    }

    result = server_api.set_clerk_user_email(
        "user_123",
        "new@example.com",
        clerk_client=client,
        timeout_ms=250,
    )

    assert result is True
    client.email_addresses.create.assert_called_once_with(
        request={
            "user_id": "user_123",
            "email_address": "new@example.com",
            "verified": True,
            "primary": True,
        },
        timeout_ms=250,
    )
    client.email_addresses.delete.assert_called_once_with(
        email_address_id="email_old",
        timeout_ms=250,
    )


def test_revoke_clerk_user_sessions_revokes_active_sessions():
    client = make_client()
    client.sessions.list.return_value = [
        {"id": "sess_1"},
        {"id": None},
        {"id": "sess_2"},
    ]

    result = server_api.revoke_clerk_user_sessions(
        "user_123",
        clerk_client=client,
        timeout_ms=250,
    )

    assert result == 2
    client.sessions.list.assert_called_once_with(
        user_id="user_123",
        status="active",
        timeout_ms=250,
    )
    assert client.sessions.revoke.call_args_list == [
        call(session_id="sess_1", timeout_ms=250),
        call(session_id="sess_2", timeout_ms=250),
    ]


def test_revoke_clerk_user_sessions_accepts_paginated_data_response():
    client = make_client()
    client.sessions.list.return_value = SimpleNamespace(data=[{"id": "sess_1"}])

    result = server_api.revoke_clerk_user_sessions(
        "user_123",
        clerk_client=client,
    )

    assert result == 1
    client.sessions.revoke.assert_called_once_with(
        session_id="sess_1",
        timeout_ms=10_000,
    )


def test_send_and_revoke_clerk_invitation():
    client = make_client()
    client.invitations.create.return_value = {"id": "inv_123"}

    invitation = server_api.send_clerk_invitation(
        "ada@example.com",
        public_metadata={"role": "staff"},
        redirect_url="https://app.example.com/accept",
        clerk_client=client,
        timeout_ms=250,
    )
    revoked = server_api.revoke_clerk_invitation(
        "inv_123",
        clerk_client=client,
        timeout_ms=250,
    )

    assert invitation == {"id": "inv_123"}
    assert revoked is True
    client.invitations.create.assert_called_once_with(
        request={
            "email_address": "ada@example.com",
            "notify": True,
            "ignore_existing": True,
            "public_metadata": {"role": "staff"},
            "redirect_url": "https://app.example.com/accept",
        },
        timeout_ms=250,
    )
    client.invitations.revoke.assert_called_once_with(
        invitation_id="inv_123",
        timeout_ms=250,
    )
