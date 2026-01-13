"""
Tests for django-clerk-users webhooks.
"""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory

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

    def test_verify_webhook_no_signing_key(self):
        """Test verification fails without signing key."""
        from django_clerk_users.webhooks.security import verify_clerk_webhook
        from django_clerk_users.exceptions import ClerkWebhookError

        with patch("django_clerk_users.webhooks.security.CLERK_WEBHOOK_SIGNING_KEY", None):
            request = RequestFactory().post("/")
            with pytest.raises(ClerkWebhookError, match="not configured"):
                verify_clerk_webhook(request)

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
