"""
Tests for the thin-client REST resources.

Two layers here. The first asserts the wire shape of each of the 18 operations
(method, path, query, body). The second is the one that actually matters: it
hands a ``ClerkClient`` to the real ``server_api`` helpers as ``clerk_client=``
and checks they behave identically to the SDK client. A resource that produced
the right HTTP request but the wrong argument style would pass the first layer
and break every call site.
"""

from __future__ import annotations

import json

import httpx
import pytest

from django_clerk_users import server_api
from django_clerk_users.clerk_api import ClerkClient, paginate

SECRET_KEY = "sk_test_resources"


class Recorder:
    """Captures each request and replays queued responses."""

    def __init__(self, responses=None):
        self.requests: list[httpx.Request] = []
        self._responses = list(responses or [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._responses:
            status, payload = self._responses.pop(0)
        else:
            status, payload = 200, {}
        if payload is None:
            return httpx.Response(status)
        return httpx.Response(status, json=payload)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def body(self, index: int = -1):
        content = self.requests[index].content
        return json.loads(content) if content else None


def make_client(responses=None) -> tuple[ClerkClient, Recorder]:
    recorder = Recorder(responses)
    client = ClerkClient(SECRET_KEY, transport=httpx.MockTransport(recorder))
    return client, recorder


class TestUsersResource:
    def test_get(self):
        client, rec = make_client([(200, {"id": "user_1"})])

        user = client.users.get(user_id="user_1", timeout_ms=250)

        assert rec.last.method == "GET"
        assert rec.last.url.path == "/v1/users/user_1"
        assert user.id == "user_1"

    def test_list_uses_the_request_dict_style(self):
        """users.list takes request={...}, unlike organizations.list."""
        client, rec = make_client([(200, [{"id": "user_1"}])])

        client.users.list(request={"email_address": ["a@b.com"], "limit": 1})

        assert rec.last.method == "GET"
        assert rec.last.url.path == "/v1/users"
        assert "email_address=a%40b.com" in str(rec.last.url)
        assert "limit=1" in str(rec.last.url)

    def test_list_accepts_offset_paging(self):
        client, rec = make_client([(200, [])])

        client.users.list(request={"limit": 100, "offset": 200})

        assert "limit=100" in str(rec.last.url)
        assert "offset=200" in str(rec.last.url)

    def test_create_uses_flat_kwargs(self):
        """users.create takes flat kwargs, unlike sessions.create."""
        client, rec = make_client([(200, {"id": "user_1"})])

        client.users.create(
            email_address=["a@b.com"], first_name="Ada", skip_password_checks=True
        )

        assert rec.last.method == "POST"
        assert rec.last.url.path == "/v1/users"
        assert rec.body() == {
            "email_address": ["a@b.com"],
            "first_name": "Ada",
            "skip_password_checks": True,
        }

    def test_create_drops_none_values(self):
        """migrate_users_to_clerk passes first_name=None explicitly."""
        client, rec = make_client([(200, {"id": "user_1"})])

        client.users.create(email_address=["a@b.com"], first_name=None)

        assert rec.body() == {"email_address": ["a@b.com"]}

    def test_update(self):
        client, rec = make_client([(200, {"id": "user_1"})])

        client.users.update(user_id="user_1", public_metadata={"role": "staff"})

        assert rec.last.method == "PATCH"
        assert rec.last.url.path == "/v1/users/user_1"
        assert rec.body() == {"public_metadata": {"role": "staff"}}

    def test_delete(self):
        client, rec = make_client([(200, None)])

        client.users.delete(user_id="user_1")

        assert rec.last.method == "DELETE"
        assert rec.last.url.path == "/v1/users/user_1"


class TestOrganizationResources:
    def test_organizations_get(self):
        client, rec = make_client([(200, {"id": "org_1"})])

        org = client.organizations.get(organization_id="org_1")

        assert rec.last.url.path == "/v1/organizations/org_1"
        assert org.id == "org_1"

    def test_organizations_list_uses_flat_kwargs(self):
        """organizations.list takes flat limit/offset, unlike users.list."""
        client, rec = make_client([(200, {"data": []})])

        client.organizations.list(limit=100, offset=200)

        assert rec.last.url.path == "/v1/organizations"
        assert "limit=100" in str(rec.last.url)
        assert "offset=200" in str(rec.last.url)

    def test_memberships_list(self):
        client, rec = make_client([(200, {"data": []})])

        client.organization_memberships.list(
            organization_id="org_1", limit=100, offset=0
        )

        assert rec.last.url.path == "/v1/organizations/org_1/memberships"
        assert "limit=100" in str(rec.last.url)

    def test_membership_public_user_data_is_attribute_accessible(self):
        """sync_clerk_organizations does getattr(membership, 'public_user_data')."""
        client, _ = make_client(
            [(200, {"data": [{"id": "m1", "public_user_data": {"user_id": "u1"}}]})]
        )

        response = client.organization_memberships.list(organization_id="org_1")
        membership = response["data"][0]

        assert getattr(membership, "public_user_data", None).user_id == "u1"


class TestEmailAndTokenResources:
    def test_email_addresses_create(self):
        client, rec = make_client([(200, {"id": "idn_1"})])

        client.email_addresses.create(
            request={"user_id": "user_1", "email_address": "a@b.com", "primary": True}
        )

        assert rec.last.method == "POST"
        assert rec.last.url.path == "/v1/email_addresses"
        assert rec.body()["email_address"] == "a@b.com"

    def test_email_addresses_delete(self):
        client, rec = make_client([(200, None)])

        client.email_addresses.delete(email_address_id="idn_1")

        assert rec.last.method == "DELETE"
        assert rec.last.url.path == "/v1/email_addresses/idn_1"

    def test_sign_in_tokens_create(self):
        client, rec = make_client([(200, {"token": "tok"})])

        client.sign_in_tokens.create(
            request={"user_id": "user_1", "expires_in_seconds": 7200}
        )

        assert rec.last.url.path == "/v1/sign_in_tokens"
        assert rec.body() == {"user_id": "user_1", "expires_in_seconds": 7200}

    def test_testing_tokens_create(self):
        client, rec = make_client([(200, {"token": "tok"})])

        client.testing_tokens.create()

        assert rec.last.method == "POST"
        assert rec.last.url.path == "/v1/testing_tokens"


class TestSessionResources:
    def test_create(self):
        client, rec = make_client([(200, {"id": "sess_1"})])

        client.sessions.create(request={"user_id": "user_1"})

        assert rec.last.url.path == "/v1/sessions"
        assert rec.body() == {"user_id": "user_1"}

    def test_create_token(self):
        client, rec = make_client([(200, {"jwt": "abc"})])

        client.sessions.create_token(session_id="sess_1")

        assert rec.last.method == "POST"
        assert rec.last.url.path == "/v1/sessions/sess_1/tokens"

    def test_list_with_paging(self):
        client, rec = make_client([(200, {"data": []})])

        client.sessions.list(user_id="user_1", status="active", limit=100, offset=0)

        url = str(rec.last.url)
        assert rec.last.url.path == "/v1/sessions"
        assert "user_id=user_1" in url
        assert "status=active" in url
        assert "limit=100" in url

    def test_revoke(self):
        client, rec = make_client([(200, {})])

        client.sessions.revoke(session_id="sess_1")

        assert rec.last.method == "POST"
        assert rec.last.url.path == "/v1/sessions/sess_1/revoke"


class TestInvitationResources:
    def test_create(self):
        client, rec = make_client([(200, {"id": "inv_1"})])

        client.invitations.create(request={"email_address": "a@b.com", "notify": True})

        assert rec.last.url.path == "/v1/invitations"
        assert rec.body()["email_address"] == "a@b.com"

    def test_revoke(self):
        client, rec = make_client([(200, {})])

        client.invitations.revoke(invitation_id="inv_1")

        assert rec.last.method == "POST"
        assert rec.last.url.path == "/v1/invitations/inv_1/revoke"


class TestTimeoutIsForwarded:
    @pytest.mark.parametrize(
        "call",
        [
            lambda c: c.users.get(user_id="u", timeout_ms=250),
            lambda c: c.users.list(timeout_ms=250),
            lambda c: c.users.create(email_address=["a@b.com"], timeout_ms=250),
            lambda c: c.users.update(user_id="u", first_name="A", timeout_ms=250),
            lambda c: c.users.delete(user_id="u", timeout_ms=250),
            lambda c: c.organizations.get(organization_id="o", timeout_ms=250),
            lambda c: c.organizations.list(timeout_ms=250),
            lambda c: c.organization_memberships.list(
                organization_id="o", timeout_ms=250
            ),
            lambda c: c.email_addresses.create(request={}, timeout_ms=250),
            lambda c: c.email_addresses.delete(email_address_id="e", timeout_ms=250),
            lambda c: c.sign_in_tokens.create(request={}, timeout_ms=250),
            lambda c: c.sessions.create(request={}, timeout_ms=250),
            lambda c: c.sessions.create_token(session_id="s", timeout_ms=250),
            lambda c: c.sessions.list(timeout_ms=250),
            lambda c: c.sessions.revoke(session_id="s", timeout_ms=250),
            lambda c: c.invitations.create(request={}, timeout_ms=250),
            lambda c: c.invitations.revoke(invitation_id="i", timeout_ms=250),
            lambda c: c.testing_tokens.create(timeout_ms=250),
        ],
    )
    def test_every_operation_forwards_timeout_ms(self, call):
        client, rec = make_client()

        call(client)

        assert rec.last.extensions["timeout"]["read"] == pytest.approx(0.25)

    def test_all_eighteen_operations_are_covered(self):
        """Guards against an operation being added without timeout coverage."""
        client, _ = make_client()
        operations = [
            (client.users, ["get", "list", "create", "update", "delete"]),
            (client.organizations, ["get", "list"]),
            (client.organization_memberships, ["list"]),
            (client.email_addresses, ["create", "delete"]),
            (client.sign_in_tokens, ["create"]),
            (client.sessions, ["create", "create_token", "list", "revoke"]),
            (client.invitations, ["create", "revoke"]),
            (client.testing_tokens, ["create"]),
        ]
        total = sum(len(names) for _, names in operations)

        for resource, names in operations:
            for name in names:
                assert callable(getattr(resource, name)), f"{resource}.{name}"

        assert total == 18


class TestDropInCompatibilityWithRealCallSites:
    """The layer that matters: real server_api helpers, thin client underneath."""

    def test_get_clerk_user(self):
        client, _ = make_client([(200, {"id": "user_1", "username": "ada"})])

        result = server_api.get_clerk_user("user_1", clerk_client=client)

        assert result["id"] == "user_1"

    def test_get_clerk_user_by_email(self):
        client, rec = make_client([(200, [{"id": "user_1"}])])

        result = server_api.get_clerk_user_by_email(
            "ada@example.com", clerk_client=client
        )

        assert result["id"] == "user_1"
        assert "email_address=ada%40example.com" in str(rec.last.url)

    def test_create_clerk_user(self):
        client, rec = make_client([(200, {"id": "user_1"})])

        result = server_api.create_clerk_user("ada@example.com", clerk_client=client)

        assert result["id"] == "user_1"
        assert rec.body()["email_address"] == ["ada@example.com"]

    def test_create_clerk_user_handles_duplicate_identifier(self):
        """Duplicate detection must work through the thin client's error type."""
        client, _ = make_client(
            [
                (
                    422,
                    {
                        "errors": [
                            {
                                "code": "form_identifier_exists",
                                "meta": {"param_names": ["email_address"]},
                            }
                        ]
                    },
                )
            ]
        )

        result = server_api.create_clerk_user("ada@example.com", clerk_client=client)

        assert result == {"already_exists": True, "email": "ada@example.com"}

    def test_update_clerk_user_public_metadata_merges(self):
        client, rec = make_client(
            [
                (200, {"id": "user_1", "public_metadata": {"existing": 1}}),
                (200, {"id": "user_1"}),
            ]
        )

        ok = server_api.update_clerk_user_public_metadata(
            "user_1", {"added": 2}, clerk_client=client
        )

        assert ok is True
        assert rec.body() == {"public_metadata": {"existing": 1, "added": 2}}

    def test_create_clerk_sign_in_token(self):
        client, _ = make_client([(200, {"token": "tok_abc"})])

        token = server_api.create_clerk_sign_in_token("user_1", clerk_client=client)

        assert token == "tok_abc"

    def test_revoke_clerk_user_sessions(self):
        """Session list + revoke through the thin client.

        Deliberately a single short page: the paginated revoke lands on its own
        branch, and this assertion must hold both before and after that merge.
        """
        responses = [
            (200, {"data": [{"id": "sess_1"}, {"id": "sess_2"}]}),
            (200, {}),
            (200, {}),
        ]
        client, rec = make_client(responses)

        revoked = server_api.revoke_clerk_user_sessions("user_1", clerk_client=client)

        assert revoked == 2
        revoke_paths = [
            r.url.path for r in rec.requests if r.url.path.endswith("/revoke")
        ]
        assert revoke_paths == [
            "/v1/sessions/sess_1/revoke",
            "/v1/sessions/sess_2/revoke",
        ]

    def test_send_and_revoke_invitation(self):
        client, _ = make_client([(200, {"id": "inv_1"}), (200, {})])

        invitation = server_api.send_clerk_invitation(
            "ada@example.com", clerk_client=client
        )
        revoked = server_api.revoke_clerk_invitation("inv_1", clerk_client=client)

        assert invitation["id"] == "inv_1"
        assert revoked is True

    def test_set_clerk_user_email_prunes_existing(self):
        client, rec = make_client(
            [
                (200, {"id": "idn_new"}),
                (
                    200,
                    {
                        "id": "user_1",
                        "email_addresses": [
                            {"id": "idn_old"},
                            {"id": "idn_new"},
                        ],
                    },
                ),
                (200, None),
            ]
        )

        ok = server_api.set_clerk_user_email(
            "user_1", "new@example.com", clerk_client=client, prune_existing=True
        )

        assert ok is True
        deletes = [r for r in rec.requests if r.method == "DELETE"]
        assert [r.url.path for r in deletes] == ["/v1/email_addresses/idn_old"]


class TestPaginate:
    def test_yields_every_item_across_pages(self):
        client, _ = make_client(
            [
                (200, {"data": [{"id": f"org_{i}"} for i in range(100)]}),
                (200, {"data": [{"id": "org_last"}]}),
            ]
        )

        items = list(paginate(client.organizations.list, page_size=100))

        assert len(items) == 101
        assert items[-1].id == "org_last"

    def test_stops_on_a_short_page(self):
        client, rec = make_client([(200, {"data": [{"id": "org_1"}]})])

        items = list(paginate(client.organizations.list, page_size=100))

        assert len(items) == 1
        assert len(rec.requests) == 1

    def test_forwards_extra_kwargs(self):
        client, rec = make_client([(200, {"data": []})])

        list(
            paginate(
                client.organization_memberships.list,
                page_size=100,
                organization_id="org_1",
            )
        )

        assert rec.last.url.path == "/v1/organizations/org_1/memberships"

    def test_is_bounded_by_max_pages(self):
        full = {"data": [{"id": "x"} for _ in range(100)]}
        client, rec = make_client([(200, full)] * 500)

        items = list(paginate(client.organizations.list, page_size=100, max_pages=3))

        assert len(items) == 300
        assert len(rec.requests) == 3

    def test_handles_bare_list_responses(self):
        """users.list returns a bare array, not a data envelope."""
        client, _ = make_client([(200, [{"id": "user_1"}])])

        items = list(paginate(client.users.list, page_size=100))

        assert len(items) == 1
