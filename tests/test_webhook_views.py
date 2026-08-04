"""
Tests for Clerk webhook views.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import RequestFactory

from django_clerk_users.webhooks.views import clerk_webhook_view


def call_verified_webhook(payload, *, svix_id=""):
    """Call the undecorated webhook view with an already-verified payload."""
    request_kwargs = {"HTTP_SVIX_ID": svix_id} if svix_id else {}
    request = RequestFactory().post("/webhooks/clerk/", **request_kwargs)
    request.clerk_webhook_data = payload
    return clerk_webhook_view.__wrapped__.__wrapped__(request)


def response_json(response):
    """Decode a JSON response body."""
    return json.loads(response.content.decode())


def test_webhook_view_rejects_non_dict_payload():
    response = call_verified_webhook(["not", "a", "dict"])

    assert response.status_code == 400
    assert response_json(response) == {"error": "Invalid payload"}


def test_webhook_view_rejects_missing_event_type():
    response = call_verified_webhook({"data": {"id": "user_123"}})

    assert response.status_code == 400
    assert response_json(response) == {"error": "Missing event type"}


def test_webhook_view_rejects_non_string_event_type():
    response = call_verified_webhook({"type": 123, "data": {"id": "user_123"}})

    assert response.status_code == 400
    assert response_json(response) == {"error": "Invalid event type"}


def test_webhook_view_rejects_non_dict_event_data():
    response = call_verified_webhook({"type": "user.created", "data": "bad"})

    assert response.status_code == 400
    assert response_json(response) == {"error": "Invalid event data"}


def test_webhook_view_processes_none_event_data_as_empty_dict():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
            return_value=False,
        ) as is_duplicate,
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            return_value=True,
        ) as process,
    ):
        response = call_verified_webhook(
            {"id": "evt_123", "type": "session.created", "data": None}
        )

    assert response.status_code == 200
    assert response.content == b"OK"
    is_duplicate.assert_called_once_with("session.created", "evt_123")
    process.assert_called_once_with("session.created", {})


def test_webhook_view_uses_event_id_for_deduplication():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
            return_value=False,
        ) as is_duplicate,
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            return_value=True,
        ),
    ):
        response = call_verified_webhook(
            {
                "id": "evt_123",
                "type": "user.created",
                "data": {"id": "user_123"},
            }
        )

    assert response.status_code == 200
    is_duplicate.assert_called_once_with("user.created", "evt_123")


def test_webhook_view_falls_back_to_svix_id_for_deduplication():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
            return_value=False,
        ) as is_duplicate,
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            return_value=True,
        ),
    ):
        response = call_verified_webhook(
            {
                "id": None,
                "type": "user.created",
                "data": {"id": "user_123"},
            },
            svix_id="msg_123",
        )

    assert response.status_code == 200
    is_duplicate.assert_called_once_with("user.created", "msg_123")


def test_webhook_view_returns_duplicate_response():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
            return_value=True,
        ) as is_duplicate,
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
        ) as process,
    ):
        response = call_verified_webhook(
            {
                "id": "evt_123",
                "type": "user.created",
                "data": {"id": "user_123"},
            }
        )

    assert response.status_code == 200
    assert response.content == b"OK (duplicate)"
    is_duplicate.assert_called_once_with("user.created", "evt_123")
    process.assert_not_called()


def test_webhook_view_skips_deduplication_without_instance_id():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
        ) as is_duplicate,
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            return_value=True,
        ) as process,
    ):
        response = call_verified_webhook({"type": "user.created", "data": {}})

    assert response.status_code == 200
    assert response.content == b"OK"
    is_duplicate.assert_not_called()
    process.assert_called_once_with("user.created", {})


def test_webhook_view_skips_deduplication_with_only_entity_id():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
        ) as is_duplicate,
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            return_value=True,
        ) as process,
    ):
        response = call_verified_webhook(
            {"type": "user.updated", "data": {"id": "user_123"}}
        )

    assert response.status_code == 200
    assert response.content == b"OK"
    is_duplicate.assert_not_called()
    process.assert_called_once_with("user.updated", {"id": "user_123"})


def test_webhook_view_returns_200_for_processing_failure():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
            return_value=False,
        ),
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            return_value=False,
        ),
    ):
        response = call_verified_webhook(
            {
                "id": "evt_123",
                "type": "user.created",
                "data": {"id": "user_123"},
            }
        )

    assert response.status_code == 200
    assert response.content == b"OK (processing failed)"


def test_webhook_view_returns_200_when_processing_raises():
    with (
        patch(
            "django_clerk_users.webhooks.views.is_duplicate_webhook",
            return_value=False,
        ),
        patch(
            "django_clerk_users.webhooks.views.process_webhook_event",
            side_effect=RuntimeError("handler crashed"),
        ),
    ):
        response = call_verified_webhook(
            {
                "id": "evt_123",
                "type": "user.created",
                "data": {"id": "user_123"},
            }
        )

    assert response.status_code == 200
    assert response.content == b"OK (processing failed)"
