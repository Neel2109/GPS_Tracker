import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import models
from app.database import Base
from app.routers.tracking import _distance_meters, _split_trips, _trip_summary
from app.services.geofences import record_geofence_transitions


def _location(location_id: str, timestamp: datetime, latitude: float, longitude: float, speed: float = 0):
    return models.Location(
        id=location_id,
        device_id="device-1",
        latitude=latitude,
        longitude=longitude,
        accuracy=3,
        speed=speed,
        timestamp=timestamp,
    )


def test_trip_segments_break_at_long_gaps_and_summarize_reported_points():
    start = datetime(2026, 1, 1, 10)
    points = [
        _location("a", start, 23.0, 72.0, 2),
        _location("b", start + timedelta(minutes=5), 23.001, 72.0, 4),
        _location("c", start + timedelta(minutes=50), 23.002, 72.0, 6),
        _location("d", start + timedelta(minutes=55), 23.003, 72.0, 8),
    ]

    trips = _split_trips(points)

    assert [[point.id for point in trip] for trip in trips] == [["a", "b"], ["c", "d"]]
    summary = _trip_summary("device-1", trips[0])
    assert summary["point_count"] == 2
    assert summary["duration_seconds"] == 300
    assert summary["average_speed"] == 3
    assert summary["maximum_speed"] == 4
    assert 100 < summary["distance_meters"] < 120
    assert _distance_meters(23.0, 72.0, 23.0, 72.0) == 0


def test_trip_summary_reports_only_stationary_periods_of_five_minutes_or_more():
    start = datetime(2026, 1, 1, 10)
    points = [
        _location("moving-start", start, 23.0, 72.0),
        _location("stop-start", start + timedelta(minutes=5), 23.001, 72.0),
        _location("stop-end", start + timedelta(minutes=12), 23.001, 72.0),
        _location("moving-end", start + timedelta(minutes=20), 23.002, 72.0),
    ]
    points[0].movement_state = "WALKING"
    points[1].movement_state = "STATIONARY"
    points[2].movement_state = "STATIONARY"
    points[3].movement_state = "WALKING"

    summary = _trip_summary("device-1", points)

    assert summary["stop_count"] == 1
    assert summary["active_duration_seconds"] == 780


def test_geofence_transition_creates_alerts_only_after_initial_state():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            user = models.User(name="Owner", email="owner@example.com", password_hash="test")
            session.add(user)
            await session.flush()
            device = models.Device(id="device-1", user_id=user.id, name="Phone", device_type="android")
            fence = models.Geofence(
                user_id=user.id,
                name="Home",
                latitude=23.0,
                longitude=72.0,
                radius=100,
            )
            session.add_all([device, fence])
            await session.flush()

            first_fix = _location("inside", datetime(2026, 1, 1, 10), 23.0, 72.0)
            assert await record_geofence_transitions(session, device, [first_fix]) == []
            await session.commit()

            outside_fix = _location("outside", datetime(2026, 1, 1, 10, 5), 23.002, 72.0)
            alerts = await record_geofence_transitions(session, device, [outside_fix])
            assert len(alerts) == 1
            assert alerts[0].type == "GEOFENCE_EXIT"
            assert alerts[0].device_id == device.id
            await session.commit()

            stale_inside_fix = _location("stale-inside", datetime(2026, 1, 1, 10, 2), 23.0, 72.0)
            assert await record_geofence_transitions(session, device, [stale_inside_fix]) == []

            inside_fix = _location("inside-again", datetime(2026, 1, 1, 10, 6), 23.0, 72.0)
            enter_alerts = await record_geofence_transitions(session, device, [inside_fix])
            assert len(enter_alerts) == 1
            assert enter_alerts[0].type == "GEOFENCE_ENTER"
            await session.commit()
        await engine.dispose()

    asyncio.run(run_flow())
