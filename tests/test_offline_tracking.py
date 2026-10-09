from datetime import datetime, timedelta

from app.models import resolve_device_status


def test_online_status_uses_live_tracking():
    now = datetime.utcnow()
    state = resolve_device_status(
        status="online",
        last_seen=now,
        last_online=now,
        last_offline=None,
        offline_since=None,
        last_location_time=now,
        last_latitude=23.0225,
        last_longitude=72.5714,
    )
    assert state == "online"


def test_offline_status_uses_last_known_location_after_disconnect():
    now = datetime.utcnow()
    state = resolve_device_status(
        status="offline",
        last_seen=now - timedelta(minutes=12),
        last_online=now - timedelta(minutes=20),
        last_offline=now - timedelta(minutes=12),
        offline_since=now - timedelta(minutes=12),
        last_location_time=now - timedelta(minutes=3),
        last_latitude=23.0225,
        last_longitude=72.5714,
    )
    assert state == "offline"


def test_recently_offline_stage_is_reported_before_older_disconnects():
    now = datetime.utcnow()
    state = resolve_device_status(
        status="offline",
        last_seen=now - timedelta(minutes=4),
        last_online=now - timedelta(minutes=10),
        last_offline=now - timedelta(minutes=4),
        offline_since=now - timedelta(minutes=4),
        last_location_time=now - timedelta(minutes=5),
        last_latitude=23.0225,
        last_longitude=72.5714,
    )
    assert state == "recently_offline"
