"""
Tests for the thin Clerk HTTP client core.

The point of these tests is not the wire shape on its own. The client exists to
be consumed by call sites that were written against the official SDK's pydantic
models, so the suite drives real helpers from ``server_api``, ``utils``, and the
sync management commands against decoded responses. A dict-only client would
pass a wire-shape test and still break every one of those call sites, because
``getattr`` on a dict returns the default.
"""

from __future__ import annotations

import json

import httpx
import pytest

from django_clerk_users.clerk_api import (
    ClerkObject,
    ClerkTransport,
    clerk_value,
    to_plain_data,
)
from django_clerk_users.exceptions import ClerkAPIError

SECRET_KEY = "sk_test_thin_client"


def make_transport(handler, **kwargs) -> ClerkTransport:
    return ClerkTransport(
        SECRET_KEY,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def json_handler(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return handler


USER_PAYLOAD = {
    "id": "user_123",
    "username": "ada",
    "primary_email_address_id": "idn_primary",
    "email_addresses": [
        {"id": "idn_other", "email_address": "old@example.com"},
        {"id": "idn_primary", "email_address": "ada@example.com"},
    ],
}


class TestClerkObject:
    def test_clerk_value_preserves_objects_and_scalars(self):
        existing = ClerkObject({"id": "user_123"})

        assert clerk_value(existing) is existing
        assert clerk_value("plain") == "plain"
        assert clerk_value(({"id": "user_123"}, "plain")) == [
            existing,
            "plain",
        ]

    def test_attribute_access_reaches_nested_entries(self):
        user = clerk_value(USER_PAYLOAD)

        assert user.id == "user_123"
        assert user.email_addresses[1].email_address == "ada@example.com"
        assert user.email_addresses[1].id == "idn_primary"

    def test_mapping_access_returns_the_same_values(self):
        user = clerk_value(USER_PAYLOAD)

        assert user["id"] == "user_123"
        assert user["email_addresses"][1]["email_address"] == "ada@example.com"
        assert "username" in user
        assert sorted(user.keys()) == sorted(USER_PAYLOAD.keys())

    def test_missing_attribute_raises_so_getattr_default_applies(self):
        user = clerk_value(USER_PAYLOAD)

        with pytest.raises(AttributeError):
            user.does_not_exist

        assert getattr(user, "does_not_exist", "fallback") == "fallback"

    def test_is_a_mapping_so_existing_helpers_branch_correctly(self):
        from collections.abc import Mapping

        assert isinstance(clerk_value(USER_PAYLOAD), Mapping)

    def test_to_dict_returns_plain_python(self):
        user = clerk_value(USER_PAYLOAD)
        plain = user.to_dict()

        assert plain == USER_PAYLOAD
        assert type(plain) is dict
        assert type(plain["email_addresses"][0]) is dict

    def test_is_read_only(self):
        user = clerk_value(USER_PAYLOAD)

        with pytest.raises(AttributeError):
            user.id = "user_other"

        with pytest.raises(AttributeError):
            del user.id

    def test_dir_repr_and_iteration_reflect_underlying_data(self):
        user = ClerkObject({"z": 1, "a": 2})

        assert list(user) == ["z", "a"]
        assert "z" in dir(user)
        assert repr(user) == "ClerkObject({'z': 1, 'a': 2})"

    def test_model_dump_can_recursively_exclude_none(self):
        value = ClerkObject(
            {
                "keep": 1,
                "drop": None,
                "nested": {"keep": 2, "drop": None},
                "items": [{"keep": 3, "drop": None}, None, "scalar"],
            }
        )

        assert value.model_dump() == {
            "keep": 1,
            "drop": None,
            "nested": {"keep": 2, "drop": None},
            "items": [{"keep": 3, "drop": None}, None, "scalar"],
        }
        assert value.model_dump(exclude_none=True) == {
            "keep": 1,
            "nested": {"keep": 2},
            "items": [{"keep": 3}, None, "scalar"],
        }

    def test_plain_data_recurses_through_tuples_and_scalars(self):
        assert to_plain_data((ClerkObject({"id": 1}), "scalar")) == [
            {"id": 1},
            "scalar",
        ]

    def test_empty_object_is_falsey_and_has_no_keys(self):
        empty = ClerkObject()

        assert len(empty) == 0
        assert not empty


class TestRealCallSitesAgainstDecodedResponses:
    """Drive the actual helpers this client has to keep working."""

    def test_server_api_list_data_and_get_value(self):
        from django_clerk_users import server_api

        response = clerk_value({"data": [USER_PAYLOAD], "total_count": 1})
        users = server_api._list_data(response)

        assert len(users) == 1
        assert server_api._get_value(users[0], "id") == "user_123"

    def test_server_api_plain_data_round_trips(self):
        from django_clerk_users import server_api

        assert server_api._plain_data(clerk_value(USER_PAYLOAD)) == USER_PAYLOAD

    def test_utils_primary_email_extraction(self):
        """The exact getattr chain from utils.update_or_create_clerk_user."""
        clerk_user = clerk_value(USER_PAYLOAD)

        primary_email = None
        email_addresses = getattr(clerk_user, "email_addresses", []) or []
        for email_obj in email_addresses:
            email_id = getattr(clerk_user, "primary_email_address_id", None)
            if email_id and getattr(email_obj, "id", None) == email_id:
                primary_email = getattr(email_obj, "email_address", None)
                break

        assert primary_email == "ada@example.com"

    def test_sync_clerk_users_email_extraction(self):
        """The getattr chain from the sync_clerk_users command."""
        clerk_user = clerk_value(USER_PAYLOAD)

        email_addresses = getattr(clerk_user, "email_addresses", []) or []
        assert email_addresses
        assert getattr(email_addresses[0], "email_address", None) == "old@example.com"

    def test_sync_clerk_organizations_public_user_data(self):
        """public_user_data must be attribute-accessible, not a bare dict."""
        membership = clerk_value(
            {
                "id": "orgmem_1",
                "role": "admin",
                "public_user_data": {"user_id": "user_123"},
            }
        )

        user_data = getattr(membership, "public_user_data", None)
        assert user_data is not None
        assert getattr(user_data, "user_id", None) == "user_123"

    def test_public_user_data_as_plain_dict_would_have_failed(self):
        """Pins why ClerkObject exists rather than decoding to dicts."""
        membership = {"public_user_data": {"user_id": "user_123"}}

        user_data = membership.get("public_user_data")
        assert getattr(user_data, "user_id", None) is None


class TestErrorType:
    def test_existing_clerk_objects_are_normalized_only_when_needed(self):
        with_errors = ClerkObject({"errors": [{"code": "bad"}]})
        without_errors = ClerkObject({"detail": "bad"})

        preserved = ClerkAPIError("boom", data=with_errors)
        normalized = ClerkAPIError("boom", data=without_errors)

        assert preserved.data is with_errors
        assert normalized.data.detail == "bad"
        assert normalized.errors == []

    def test_duplicate_identifier_detection_still_works(self):
        """server_api duplicate detection must work without SDK types."""
        from django_clerk_users import server_api

        body = {
            "errors": [
                {
                    "code": "form_identifier_exists",
                    "message": "already exists",
                    "meta": {"param_names": ["email_address"]},
                }
            ]
        }
        exc = ClerkAPIError("boom", status_code=422, data=body)

        assert server_api._has_duplicate_identifier_error(exc) is True
        assert server_api._duplicate_error_params(exc) == {"email_address"}

    def test_status_code_and_structured_data(self):
        body = {"errors": [{"code": "not_found", "meta": {"param_names": []}}]}
        exc = ClerkAPIError("boom", status_code=404, data=body)

        assert exc.status_code == 404
        assert exc.data.errors[0].code == "not_found"
        assert exc.data.errors[0].meta.param_names == []
        assert exc.errors[0]["code"] == "not_found"

    def test_message_only_construction_still_supported(self):
        """utils.py raises ClerkAPIError with just a message."""
        exc = ClerkAPIError("Failed to fetch user from Clerk: boom")

        assert exc.status_code is None
        assert exc.errors == []
        assert "Failed to fetch user" in str(exc)

    def test_non_json_body_still_exposes_errors(self):
        exc = ClerkAPIError("boom", status_code=502, data="<html>bad gateway</html>")

        assert exc.errors == []
        assert exc.data.raw == "<html>bad gateway</html>"

    def test_log_clerk_error_reads_status_code(self, caplog):
        from django_clerk_users import server_api

        exc = ClerkAPIError("boom", status_code=429, data={"errors": []})
        with caplog.at_level("ERROR"):
            server_api._log_clerk_error("test op", exc)

        assert "status=429" in caplog.text


class TestTransport:
    def test_get_returns_attribute_accessible_object(self):
        transport = make_transport(json_handler(USER_PAYLOAD))

        user = transport.get("/users/user_123")

        assert user.email_addresses[1].email_address == "ada@example.com"

    def test_authorization_header_and_url(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"id": "user_123"})

        make_transport(handler).get("/users/user_123")

        assert seen["url"] == "https://api.clerk.com/v1/users/user_123"
        assert seen["auth"] == f"Bearer {SECRET_KEY}"

    def test_json_body_is_sent(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "user_123"})

        make_transport(handler).post("/users", json={"email_address": ["a@b.com"]})

        assert seen["body"] == {"email_address": ["a@b.com"]}

    def test_none_params_are_dropped(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=[])

        make_transport(handler).get(
            "/sessions", params={"user_id": "u1", "status": None}
        )

        assert "user_id=u1" in seen["url"]
        assert "status" not in seen["url"]

    def test_list_response_returns_list_of_objects(self):
        transport = make_transport(json_handler([USER_PAYLOAD]))

        users = transport.get("/users")

        assert isinstance(users, list)
        assert users[0].email_addresses[0].id == "idn_other"

    def test_empty_body_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(204)

        assert make_transport(handler).delete("/sessions/sess_1") is None

    def test_error_response_raises_with_status_and_data(self):
        body = {
            "errors": [
                {
                    "code": "form_identifier_exists",
                    "long_message": "That email is taken.",
                    "meta": {"param_names": ["email_address"]},
                }
            ]
        }
        transport = make_transport(json_handler(body, status_code=422))

        with pytest.raises(ClerkAPIError) as excinfo:
            transport.post("/users", json={})

        exc = excinfo.value
        assert exc.status_code == 422
        assert exc.data.errors[0].code == "form_identifier_exists"
        assert exc.data.errors[0].meta.param_names == ["email_address"]
        assert "That email is taken." in str(exc)

    def test_non_json_error_body_does_not_mask_the_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, text="bad gateway")

        with pytest.raises(ClerkAPIError) as excinfo:
            make_transport(handler).get("/users")

        assert excinfo.value.status_code == 502
        assert "bad gateway" in str(excinfo.value)

    def test_timeout_is_honoured_from_argument(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={})

        make_transport(handler).get("/users", timeout_ms=250)

        assert seen["timeout"]["read"] == pytest.approx(0.25)

    def test_timeout_falls_back_to_setting(self, settings):
        settings.CLERK_API_TIMEOUT_MS = 3000
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={})

        make_transport(handler).get("/users")

        assert seen["timeout"]["read"] == pytest.approx(3.0)

    def test_invalid_timeout_setting_falls_back_to_default(self, settings):
        settings.CLERK_API_TIMEOUT_MS = "not-an-int"
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={})

        make_transport(handler).get("/users")

        assert seen["timeout"]["read"] == pytest.approx(10.0)

    def test_timeout_exception_becomes_clerk_api_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        with pytest.raises(ClerkAPIError, match="timed out"):
            make_transport(handler).get("/users")

    def test_transport_error_becomes_clerk_api_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        with pytest.raises(ClerkAPIError, match="Clerk request failed"):
            make_transport(handler).get("/users")

    def test_base_url_override(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={})

        make_transport(handler, base_url="https://example.test/v1/").get("/users")

        assert seen["url"] == "https://example.test/v1/users"
