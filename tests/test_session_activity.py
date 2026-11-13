"""
Session webhooks must never move last_login / last_logout backward.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from django_clerk_users.webhooks import handlers
from django_clerk_users.webhooks.handlers import (
    _advance_activity_timestamp,
    handle_session_created,
    handle_session_ended,
)
from django_clerk_users.webhooks.signals import (
    clerk_session_created,
    clerk_session_ended,
)

CLERK_ID = "user_activity123"
OLDER = datetime(2025, 1, 1, tzinfo=timezone.utc)
NEWER = datetime(2025, 6, 1, tzinfo=timezone.utc)


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        clerk_id=CLERK_ID, email="activity@example.com"
    )


def stored(field: str):
    return get_user_model().objects.values_list(field, flat=True).get(clerk_id=CLERK_ID)


def created(ts):
    return handle_session_created({"user_id": CLERK_ID, "created_at": ts})


def ended(ts):
    return handle_session_ended({"user_id": CLERK_ID, "abandoned_at": ts})


CASES = [
    pytest.param(created, "last_login", id="last_login"),
    pytest.param(ended, "last_logout", id="last_logout"),
]


@pytest.mark.parametrize("deliver,field", CASES)
class TestMonotonicActivity:
    def test_initializes_null_value(self, user, deliver, field):
        assert stored(field) is None
        assert deliver(ms(OLDER)) is True
        assert stored(field) == OLDER

    def test_newer_then_older_keeps_newer(self, user, deliver, field):
        deliver(ms(NEWER))
        assert deliver(ms(OLDER)) is True
        assert stored(field) == NEWER

    def test_older_then_newer_advances(self, user, deliver, field):
        deliver(ms(OLDER))
        deliver(ms(NEWER))
        assert stored(field) == NEWER

    def test_replay_is_idempotent(self, user, deliver, field):
        deliver(ms(NEWER))
        updated_at = stored("updated_at")
        assert deliver(ms(NEWER)) is True
        assert stored(field) == NEWER
        assert stored("updated_at") == updated_at

    @pytest.mark.parametrize(
        "bad",
        [None, "not-a-timestamp", True, 10**20, {"nested": 1}],
        ids=["missing", "malformed-str", "bool", "overflow", "wrong-type"],
    )
    def test_missing_or_malformed_never_erases(self, user, deliver, field, bad):
        deliver(ms(NEWER))
        assert deliver(bad) is True
        assert stored(field) == NEWER

    def test_missing_on_null_stays_null(self, user, deliver, field):
        assert deliver(None) is True
        assert stored(field) is None

    def test_in_memory_user_reflects_stored_value(self, user, deliver, field):
        deliver(ms(NEWER))
        seen = []
        signal = clerk_session_created if field == "last_login" else clerk_session_ended

        def receiver(sender, user, **kwargs):
            seen.append(getattr(user, field))

        signal.connect(receiver)
        try:
            deliver(ms(OLDER))
        finally:
            signal.disconnect(receiver)
        assert seen == [NEWER]

    def test_concurrent_newer_write_is_not_regressed(self, user, deliver, field):
        """
        Another delivery commits a newer value after this handler loaded the
        user but before it writes. A read/modify/write would overwrite it.
        """
        deliver(ms(OLDER))
        real_parse = handlers.parse_clerk_timestamp

        def parse_after_concurrent_write(value):
            get_user_model().objects.filter(clerk_id=CLERK_ID).update(**{field: NEWER})
            return real_parse(value)

        middle = OLDER + timedelta(days=30)
        with patch.object(
            handlers, "parse_clerk_timestamp", parse_after_concurrent_write
        ):
            assert deliver(ms(middle)) is True
        assert stored(field) == NEWER


@pytest.mark.parametrize(
    "deliver,field,signal",
    [
        pytest.param(created, "last_login", clerk_session_created, id="created"),
        pytest.param(ended, "last_logout", clerk_session_ended, id="ended"),
    ],
)
def test_signal_sent_for_stale_events_with_flag(user, deliver, field, signal):
    calls = []

    def receiver(sender, user, clerk_data, activity_advanced, **kwargs):
        calls.append(activity_advanced)

    signal.connect(receiver)
    try:
        deliver(ms(NEWER))
        deliver(ms(OLDER))
        deliver(None)
    finally:
        signal.disconnect(receiver)
    assert calls == [True, False, False]


def test_session_ended_updated_at_fallback_is_monotonic(user):
    handle_session_ended({"user_id": CLERK_ID, "updated_at": ms(NEWER)})
    handle_session_ended({"user_id": CLERK_ID, "updated_at": ms(OLDER)})
    assert stored("last_logout") == NEWER


def test_fields_are_independent(user):
    created(ms(NEWER))
    ended(ms(OLDER))
    assert stored("last_login") == NEWER
    assert stored("last_logout") == OLDER


def test_advance_helper_with_stale_instance(user):
    stale = get_user_model().objects.get(pk=user.pk)
    get_user_model().objects.filter(pk=user.pk).update(last_login=NEWER)
    assert _advance_activity_timestamp(stale, "last_login", OLDER) is False
    assert stale.last_login == NEWER
    assert stored("last_login") == NEWER


class ActivityShardRouter:
    """Reads select a shard; writes use Django's instance-database fallback."""

    def db_for_read(self, model, **hints):
        if model is get_user_model():
            return "activity_primary"
        return None


class ActivityReplicaRouter:
    """A loaded user supplies the context needed to select its primary."""

    def db_for_read(self, model, **hints):
        if model is get_user_model():
            return "activity_replica"
        return None

    def db_for_write(self, model, **hints):
        if model is get_user_model() and hints.get("instance") is not None:
            return "activity_primary"
        return None


@pytest.mark.django_db(databases=["default", "activity_primary", "activity_replica"])
@pytest.mark.parametrize("deliver,field", CASES)
class TestActivityDatabaseRouting:
    def test_shard_update_does_not_touch_same_pk_on_default(self, deliver, field):
        User = get_user_model()
        unrelated = User.objects.db_manager("default").create_user(
            pk=42, clerk_id="user_other", email="other@example.com", **{field: OLDER}
        )
        target = User.objects.db_manager("activity_primary").create_user(
            pk=42, clerk_id=CLERK_ID, email="activity@example.com"
        )

        with override_settings(DATABASE_ROUTERS=[ActivityShardRouter()]):
            assert deliver(ms(NEWER)) is True

        unrelated.refresh_from_db(using="default")
        target.refresh_from_db(using="activity_primary")
        assert getattr(unrelated, field) == OLDER
        assert getattr(target, field) == NEWER

    def test_primary_write_and_refresh_bypass_stale_replica(self, deliver, field):
        User = get_user_model()
        unrelated = User.objects.db_manager("default").create_user(
            pk=42, clerk_id="user_other", email="other@example.com", **{field: OLDER}
        )
        for alias in ("activity_primary", "activity_replica"):
            User.objects.db_manager(alias).create_user(
                pk=42,
                clerk_id=CLERK_ID,
                email="activity@example.com",
                **{field: OLDER},
            )
        seen = []
        signal = clerk_session_created if field == "last_login" else clerk_session_ended

        def receiver(sender, user, activity_advanced, **kwargs):
            seen.append((getattr(user, field), activity_advanced, user._state.db))

        signal.connect(receiver)
        try:
            with override_settings(DATABASE_ROUTERS=[ActivityReplicaRouter()]):
                assert deliver(ms(NEWER)) is True
                assert deliver(ms(OLDER)) is True
        finally:
            signal.disconnect(receiver)

        unrelated.refresh_from_db(using="default")
        assert getattr(unrelated, field) == OLDER
        assert (
            User.objects.using("activity_primary").values_list(field, flat=True).get()
            == NEWER
        )
        assert (
            User.objects.using("activity_replica").values_list(field, flat=True).get()
            == OLDER
        )
        assert seen == [
            (NEWER, True, "activity_primary"),
            (NEWER, False, "activity_primary"),
        ]
