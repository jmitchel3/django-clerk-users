"""
Tests for django-clerk-users webhooks.
"""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from django_clerk_users.webhooks.handlers import (
    is_duplicate_webhook,
    parse_clerk_timestamp,
    process_webhook_event,
)
from django_clerk_users.webhooks.signals import (
    clerk_user_created,
    clerk_user_deleted,
    clerk_user_updated,
    clerk_session_created,
    clerk_session_ended,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def clerk_user(db):
    """Create a test ClerkUser."""
    User = get_user_model()
    return User.objects.create_user(
        clerk_id="user_webhook123",
        email="webhook@example.com",
        first_name="Webhook",
        last_name="User",
    )


class TestParseClerkTimestamp:
    """Test timestamp parsing."""

    def test_parse_none(self):
        """Test parsing None returns None."""
        assert parse_clerk_timestamp(None) is None

    def test_parse_datetime_naive(self):
        """Test parsing naive datetime adds UTC."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = parse_clerk_timestamp(dt)
        assert result.tzinfo == dt_timezone.utc
        assert result.year == 2024

    def test_parse_datetime_aware(self):
        """Test parsing aware datetime preserves it."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        result = parse_clerk_timestamp(dt)
        assert result == dt

    def test_parse_unix_milliseconds(self):
        """Test parsing Unix milliseconds."""
        # 1704067200000 = 2024-01-01 00:00:00 UTC
        result = parse_clerk_timestamp(1704067200000)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_parse_iso_string(self):
        """Test parsing ISO string."""
        result = parse_clerk_timestamp("2024-01-15T10:30:00Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_iso_string_with_offset(self):
        """Test parsing ISO string with timezone offset."""
        result = parse_clerk_timestamp("2024-01-15T10:30:00+00:00")
        assert result.year == 2024

    def test_parse_invalid_string(self):
        """Test parsing invalid string returns None."""
        result = parse_clerk_timestamp("not-a-date")
        assert result is None


class TestDuplicateWebhook:
    """Test duplicate webhook detection."""

    def test_first_webhook_not_duplicate(self):
        """Test first webhook is not a duplicate."""
        result = is_duplicate_webhook("user.created", "inst_123")
        assert result is False

    def test_second_webhook_is_duplicate(self):
        """Test second identical webhook is a duplicate."""
        is_duplicate_webhook("user.created", "inst_456")
        result = is_duplicate_webhook("user.created", "inst_456")
        assert result is True

    def test_different_instance_not_duplicate(self):
        """Test different instance is not a duplicate."""
        is_duplicate_webhook("user.created", "inst_789")
        result = is_duplicate_webhook("user.created", "inst_999")
        assert result is False

    def test_different_event_not_duplicate(self):
        """Test different event type is not a duplicate."""
        is_duplicate_webhook("user.created", "inst_abc")
        result = is_duplicate_webhook("user.updated", "inst_abc")
        assert result is False


class TestWebhookSignals:
    """Test webhook signal emission."""

    def test_user_created_signal_defined(self):
        """Test clerk_user_created signal exists."""
        assert clerk_user_created is not None

    def test_user_updated_signal_defined(self):
        """Test clerk_user_updated signal exists."""
        assert clerk_user_updated is not None

    def test_user_deleted_signal_defined(self):
        """Test clerk_user_deleted signal exists."""
        assert clerk_user_deleted is not None

    def test_session_created_signal_defined(self):
        """Test clerk_session_created signal exists."""
        assert clerk_session_created is not None

    def test_session_ended_signal_defined(self):
        """Test clerk_session_ended signal exists."""
        assert clerk_session_ended is not None


class TestProcessWebhookEvent:
    """Test webhook event processing."""

    @patch("django_clerk_users.webhooks.handlers.handle_user_created")
    def test_process_user_created(self, mock_handler):
        """Test processing user.created event."""
        mock_handler.return_value = MagicMock()
        data = {"id": "user_123"}

        result = process_webhook_event("user.created", data)

        assert result is True
        mock_handler.assert_called_once_with(data)

    @patch("django_clerk_users.webhooks.handlers.handle_user_updated")
    def test_process_user_updated(self, mock_handler):
        """Test processing user.updated event."""
        mock_handler.return_value = MagicMock()
        data = {"id": "user_123"}

        result = process_webhook_event("user.updated", data)

        assert result is True
        mock_handler.assert_called_once_with(data)

    @patch("django_clerk_users.webhooks.handlers.handle_user_deleted")
    def test_process_user_deleted(self, mock_handler):
        """Test processing user.deleted event."""
        mock_handler.return_value = MagicMock()
        data = {"id": "user_123"}

        result = process_webhook_event("user.deleted", data)

        assert result is True
        mock_handler.assert_called_once_with(data)

    @patch("django_clerk_users.webhooks.handlers.handle_session_created")
    def test_process_session_created(self, mock_handler):
        """Test processing session.created event."""
        data = {"user_id": "user_123"}

        result = process_webhook_event("session.created", data)

        assert result is True
        mock_handler.assert_called_once_with(data)

    @patch("django_clerk_users.webhooks.handlers.handle_session_ended")
    def test_process_session_ended(self, mock_handler):
        """Test processing session.ended event."""
        data = {"user_id": "user_123"}

        result = process_webhook_event("session.ended", data)

        assert result is True
        mock_handler.assert_called_once_with(data)

    @patch("django_clerk_users.webhooks.handlers.handle_session_ended")
    def test_process_session_removed(self, mock_handler):
        """Test processing session.removed event (uses ended handler)."""
        data = {"user_id": "user_123"}

        result = process_webhook_event("session.removed", data)

        assert result is True
        mock_handler.assert_called_once()

    @patch("django_clerk_users.webhooks.handlers.handle_session_ended")
    def test_process_session_revoked(self, mock_handler):
        """Test processing session.revoked event (uses ended handler)."""
        data = {"user_id": "user_123"}

        result = process_webhook_event("session.revoked", data)

        assert result is True
        mock_handler.assert_called_once()

    def test_process_unknown_event(self):
        """Test processing unknown event type."""
        result = process_webhook_event("unknown.event", {})
        assert result is True  # Unknown events return True (acknowledged)

    def test_process_handler_exception(self):
        """Test processing when handler raises exception."""
        with patch(
            "django_clerk_users.webhooks.handlers.handle_user_created",
            side_effect=Exception("Handler error"),
        ):
            result = process_webhook_event("user.created", {"id": "user_123"})
            assert result is False


class TestHandleUserDeleted:
    """Test user deletion webhook handler."""

    def test_soft_delete_user(self, clerk_user):
        """Test that user deletion is a soft delete."""
        from django_clerk_users.webhooks.handlers import handle_user_deleted

        data = {"id": "user_webhook123"}
        result = handle_user_deleted(data)

        # Refresh from database
        clerk_user.refresh_from_db()

        assert result == clerk_user
        assert clerk_user.is_active is False

    def test_delete_nonexistent_user(self, db):
        """Test deleting nonexistent user."""
        from django_clerk_users.webhooks.handlers import handle_user_deleted

        data = {"id": "nonexistent_user"}
        result = handle_user_deleted(data)

        assert result is None

    def test_delete_missing_user_id(self, db):
        """Test deleting without user ID."""
        from django_clerk_users.webhooks.handlers import handle_user_deleted

        data = {}
        result = handle_user_deleted(data)

        assert result is None

    def test_delete_username_only_user(self, db):
        """Test deleting a username-only user."""
        from django_clerk_users.webhooks.handlers import handle_user_deleted

        User = get_user_model()
        user = User.objects.create_user(
            clerk_id="user_delete_username",
            username="deleteuser",
        )
        assert user.email is None

        data = {"id": "user_delete_username"}
        result = handle_user_deleted(data)

        user.refresh_from_db()
        assert result == user
        assert user.is_active is False


class TestHandleUserCreatedWithUsername:
    """Test user creation webhook handler with username support."""

    def test_user_created_with_username_only(self, db):
        """Test user.created webhook with username but no email."""
        from django_clerk_users.webhooks.handlers import handle_user_created

        mock_clerk_user = MagicMock()
        mock_clerk_user.first_name = "Username"
        mock_clerk_user.last_name = "Only"
        mock_clerk_user.image_url = ""
        mock_clerk_user.username = "usernameonly"
        mock_clerk_user.email_addresses = []
        mock_clerk_user.primary_email_address_id = None

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            data = {"id": "user_webhook_username"}
            result = handle_user_created(data)

        assert result is not None
        assert result.clerk_id == "user_webhook_username"
        assert result.email is None
        assert result.username == "usernameonly"

    def test_user_created_with_both_email_and_username(self, db):
        """Test user.created webhook with both email and username."""
        from django_clerk_users.webhooks.handlers import handle_user_created

        mock_clerk_user = MagicMock()
        mock_clerk_user.first_name = "Both"
        mock_clerk_user.last_name = "User"
        mock_clerk_user.image_url = ""
        mock_clerk_user.username = "bothuser"
        mock_clerk_user.primary_email_address_id = "email_123"
        email_obj = MagicMock()
        email_obj.id = "email_123"
        email_obj.email_address = "both@example.com"
        mock_clerk_user.email_addresses = [email_obj]

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            data = {"id": "user_webhook_both"}
            result = handle_user_created(data)

        assert result is not None
        assert result.email == "both@example.com"
        assert result.username == "bothuser"

    def test_user_created_with_clerk_id_only(self, db):
        """Test user.created webhook with only clerk_id (no email, no username)."""
        from django_clerk_users.webhooks.handlers import handle_user_created

        mock_clerk_user = MagicMock()
        mock_clerk_user.first_name = ""
        mock_clerk_user.last_name = ""
        mock_clerk_user.image_url = ""
        mock_clerk_user.username = None
        mock_clerk_user.email_addresses = []
        mock_clerk_user.primary_email_address_id = None

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            data = {"id": "user_webhook_clerk_only"}
            result = handle_user_created(data)

        assert result is not None
        assert result.clerk_id == "user_webhook_clerk_only"
        assert result.email is None
        assert result.username is None


class TestHandleUserUpdatedWithUsername:
    """Test user update webhook handler with username support."""

    def test_user_updated_adds_username(self, db):
        """Test user.updated webhook that adds username to existing user."""
        from django_clerk_users.webhooks.handlers import handle_user_updated

        User = get_user_model()
        existing_user = User.objects.create_user(
            clerk_id="user_update_add_username",
            email="addusername@example.com",
        )
        assert existing_user.username is None

        mock_clerk_user = MagicMock()
        mock_clerk_user.first_name = "Updated"
        mock_clerk_user.last_name = "User"
        mock_clerk_user.image_url = ""
        mock_clerk_user.username = "newusername"
        mock_clerk_user.primary_email_address_id = "email_123"
        email_obj = MagicMock()
        email_obj.id = "email_123"
        email_obj.email_address = "addusername@example.com"
        mock_clerk_user.email_addresses = [email_obj]

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            data = {"id": "user_update_add_username"}
            result = handle_user_updated(data)

        assert result is not None
        assert result.username == "newusername"

    def test_user_updated_changes_email_to_username(self, db):
        """Test user.updated webhook where email is removed, username added."""
        from django_clerk_users.webhooks.handlers import handle_user_updated

        User = get_user_model()
        User.objects.create_user(
            clerk_id="user_email_to_username",
            email="willchange@example.com",
        )

        mock_clerk_user = MagicMock()
        mock_clerk_user.first_name = "Changed"
        mock_clerk_user.last_name = "User"
        mock_clerk_user.image_url = ""
        mock_clerk_user.username = "nowusername"
        mock_clerk_user.email_addresses = []
        mock_clerk_user.primary_email_address_id = None

        mock_client = MagicMock()
        mock_client.users.get.return_value = mock_clerk_user

        with patch(
            "django_clerk_users.utils.get_clerk_client",
            return_value=mock_client,
        ):
            data = {"id": "user_email_to_username"}
            result = handle_user_updated(data)

        assert result is not None
        assert result.email is None
        assert result.username == "nowusername"


class TestHandleSessionCreated:
    """Test session creation webhook handler."""

    def test_updates_last_login(self, clerk_user):
        """Test that session.created updates last_login."""
        from django_clerk_users.webhooks.handlers import handle_session_created

        data = {
            "user_id": "user_webhook123",
            "created_at": 1704067200000,  # 2024-01-01 00:00:00 UTC
        }
        handle_session_created(data)

        clerk_user.refresh_from_db()
        assert clerk_user.last_login is not None
        assert clerk_user.last_login.year == 2024

    def test_missing_user_id(self, db):
        """Test handling missing user_id."""
        from django_clerk_users.webhooks.handlers import handle_session_created

        data = {"created_at": 1704067200000}
        # Should not raise, just log
        handle_session_created(data)


class TestHandleSessionEnded:
    """Test session ended webhook handler."""

    def test_updates_last_logout(self, clerk_user):
        """Test that session.ended updates last_logout."""
        from django_clerk_users.webhooks.handlers import handle_session_ended

        data = {
            "user_id": "user_webhook123",
            "abandoned_at": 1704067200000,
        }
        handle_session_ended(data)

        clerk_user.refresh_from_db()
        assert clerk_user.last_logout is not None

    def test_uses_updated_at_fallback(self, clerk_user):
        """Test fallback to updated_at when abandoned_at missing."""
        from django_clerk_users.webhooks.handlers import handle_session_ended

        data = {
            "user_id": "user_webhook123",
            "updated_at": 1704067200000,
        }
        handle_session_ended(data)

        clerk_user.refresh_from_db()
        assert clerk_user.last_logout is not None


class TestWebhookSecurity:
    """Test webhook security utilities."""

    @override_settings(CLERK_WEBHOOK_SIGNING_KEY=None)
    def test_verify_webhook_no_signing_key(self):
        """Test verification fails without signing key."""
        from django_clerk_users.webhooks.security import verify_clerk_webhook
        from django_clerk_users.exceptions import ClerkWebhookError

        request = RequestFactory().post("/")
        with pytest.raises(ClerkWebhookError, match="not configured"):
            verify_clerk_webhook(request)

    @override_settings(CLERK_OPTIONAL_WEBHOOK_SIGNING_KEY="")
    def test_verify_webhook_allow_missing_signing_key(self):
        """Test optional verification can skip when no endpoint key is configured."""
        from django_clerk_users.webhooks.security import verify_clerk_webhook

        request = RequestFactory().post("/")

        assert (
            verify_clerk_webhook(
                request,
                signing_key_setting="CLERK_OPTIONAL_WEBHOOK_SIGNING_KEY",
                allow_missing=True,
            )
            is None
        )

    @patch("django_clerk_users.webhooks.security.Webhook")
    def test_verify_webhook_uses_explicit_signing_key(self, mock_webhook):
        """Test verification can use an explicit endpoint signing key."""
        from django_clerk_users.webhooks.security import verify_clerk_webhook

        mock_instance = mock_webhook.return_value
        mock_instance.verify.return_value = {"type": "user.created"}
        request = RequestFactory().post(
            "/",
            data=b'{"type": "user.created"}',
            content_type="application/json",
            HTTP_SVIX_ID="msg_123",
            HTTP_SVIX_TIMESTAMP="1704067200",
            HTTP_SVIX_SIGNATURE="sig_123",
        )

        payload = verify_clerk_webhook(request, signing_key="whsec_endpoint")

        assert payload == {"type": "user.created"}
        mock_webhook.assert_called_once_with("whsec_endpoint")

    @override_settings(CLERK_ACTIVATION_WEBHOOK_SIGNING_KEY="whsec_activation")
    @patch("django_clerk_users.webhooks.security.Webhook")
    def test_verify_webhook_uses_endpoint_setting_name(self, mock_webhook):
        """Test verification can read an endpoint-specific setting name."""
        from django_clerk_users.webhooks.security import verify_clerk_webhook

        mock_instance = mock_webhook.return_value
        mock_instance.verify.return_value = {"type": "invitation.accepted"}
        request = RequestFactory().post("/")

        payload = verify_clerk_webhook(
            request,
            signing_key_setting="CLERK_ACTIVATION_WEBHOOK_SIGNING_KEY",
        )

        assert payload == {"type": "invitation.accepted"}
        mock_webhook.assert_called_once_with("whsec_activation")

    def test_clerk_webhook_required_rejects_get(self):
        """Test decorator rejects GET requests."""
        from django_clerk_users.webhooks.security import clerk_webhook_required

        @clerk_webhook_required
        def my_webhook(request):
            return HttpResponse("OK")

        request = RequestFactory().get("/webhook/")
        response = my_webhook(request)

        assert response.status_code == 400

    def test_clerk_webhook_required_preserves_name(self):
        """Test decorator preserves function name."""
        from django_clerk_users.webhooks.security import clerk_webhook_required

        @clerk_webhook_required
        def my_webhook_view(request):
            return HttpResponse("OK")

        assert my_webhook_view.__name__ == "my_webhook_view"

    @patch("django_clerk_users.webhooks.security.Webhook")
    def test_clerk_webhook_required_accepts_endpoint_signing_key(self, mock_webhook):
        """Test decorator supports endpoint-specific signing keys."""
        from django_clerk_users.webhooks.security import clerk_webhook_required

        mock_webhook.return_value.verify.return_value = {"type": "user.created"}

        @clerk_webhook_required(signing_key="whsec_endpoint")
        def my_webhook_view(request):
            assert request.clerk_webhook_data == {"type": "user.created"}
            return HttpResponse("OK")

        request = RequestFactory().post("/")
        response = my_webhook_view(request)

        assert response.status_code == 200
        mock_webhook.assert_called_once_with("whsec_endpoint")
