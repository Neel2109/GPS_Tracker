import asyncio
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import models, schemas, security
from app.database import Base, get_db
from app.main import app
from app.routers.devices import get_device_proximity


def test_proximity_is_owner_scoped_and_labels_uncertainty_and_possible_separation():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with session_factory() as session:
            owner = models.User(name="Owner", email="owner@example.com", password_hash="test")
            other_owner = models.User(name="Other", email="other@example.com", password_hash="test")
            session.add_all([owner, other_owner])
            await session.flush()

            phone = models.Device(
                id="phone",
                user_id=owner.id,
                name="Phone",
                last_latitude=23.0,
                last_longitude=72.0,
                last_accuracy=5,
                last_location_time=now,
                last_movement_state="WALKING",
            )
            laptop = models.Device(
                id="laptop",
                user_id=owner.id,
                name="Laptop",
                last_latitude=23.01,
                last_longitude=72.0,
                last_accuracy=5,
                last_location_time=now,
                last_movement_state="STATIONARY",
            )
            stale_watch = models.Device(
                id="watch",
                user_id=owner.id,
                name="Watch",
                last_latitude=23.0,
                last_longitude=72.0,
                last_accuracy=4,
                last_location_time=now - timedelta(minutes=20),
            )
            tablet = models.Device(
                id="tablet",
                user_id=owner.id,
                name="Tablet",
                last_latitude=23.0,
                last_longitude=72.0,
                last_accuracy=5,
                last_location_time=now,
                last_movement_state="STATIONARY",
            )
            foreign_device = models.Device(
                id="foreign",
                user_id=other_owner.id,
                name="Other owner's phone",
                last_latitude=23.0,
                last_longitude=72.0,
                last_accuracy=1,
                last_location_time=now,
            )
            session.add_all([phone, laptop, stale_watch, tablet, foreign_device])
            await session.commit()

            snapshot = await get_device_proximity(
                threshold_meters=250,
                current_user=owner,
                db=session,
            )

            schemas.DeviceProximitySnapshot.model_validate(snapshot)
            pairs = snapshot["pairs"]
            assert len(pairs) == 6
            assert all(
                "Other owner's phone" not in {pair["first_device_name"], pair["second_device_name"]}
                for pair in pairs
            )
            phone_laptop = next(
                pair for pair in pairs
                if {pair["first_device_id"], pair["second_device_id"]} == {"phone", "laptop"}
            )
            assert phone_laptop["status"] == "SEPARATED"
            assert phone_laptop["possible_left_behind_device_name"] == "Laptop"

            phone_tablet = next(
                pair for pair in pairs
                if {pair["first_device_id"], pair["second_device_id"]} == {"phone", "tablet"}
            )
            assert phone_tablet["status"] == "NEAR"

            phone_watch = next(
                pair for pair in pairs
                if {pair["first_device_id"], pair["second_device_id"]} == {"phone", "watch"}
            )
            assert phone_watch["status"] == "UNKNOWN"
            assert phone_watch["last_known_distance_meters"] == 0
        await engine.dispose()

    asyncio.run(run_flow())


def test_proximity_static_route_precedes_dynamic_device_route():
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert paths.index("/api/devices/proximity") < paths.index("/api/devices/{device_id}")


def test_proximity_http_endpoint_uses_signed_in_owner_scope():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            owner = models.User(name="Owner", email="http-owner@example.com", password_hash="test")
            other_owner = models.User(name="Other", email="http-other@example.com", password_hash="test")
            session.add_all([owner, other_owner])
            await session.flush()
            session.add_all([
                models.Device(
                    id="http-owner-a",
                    user_id=owner.id,
                    name="Owner A",
                    last_latitude=23.0,
                    last_longitude=72.0,
                    last_accuracy=5,
                    last_location_time=datetime.now(timezone.utc),
                ),
                models.Device(
                    id="http-owner-b",
                    user_id=owner.id,
                    name="Owner B",
                    last_latitude=23.0001,
                    last_longitude=72.0,
                    last_accuracy=5,
                    last_location_time=datetime.now(timezone.utc),
                ),
                models.Device(
                    id="http-foreign",
                    user_id=other_owner.id,
                    name="Foreign",
                    last_latitude=23.0,
                    last_longitude=72.0,
                    last_accuracy=1,
                    last_location_time=datetime.now(timezone.utc),
                ),
            ])
            await session.commit()

            async def override_get_db():
                yield session

            previous_overrides = app.dependency_overrides.copy()
            app.dependency_overrides[security.get_current_user] = lambda: owner
            app.dependency_overrides[get_db] = override_get_db
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    response = await client.get("/api/devices/proximity?threshold_meters=250")
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(previous_overrides)

            assert response.status_code == 200
            payload = response.json()
            assert payload["threshold_meters"] == 250
            assert len(payload["pairs"]) == 1
            assert {payload["pairs"][0]["first_device_id"], payload["pairs"][0]["second_device_id"]} == {
                "http-owner-a",
                "http-owner-b",
            }
        await engine.dispose()

    asyncio.run(run_flow())


def test_proximity_uses_accuracy_bounds_and_freshness():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)

        async with session_factory() as session:
            owner = models.User(name="Owner", email="owner@example.com", password_hash="test")
            session.add(owner)
            await session.flush()
            session.add_all([
                models.Device(
                    id="a",
                    user_id=owner.id,
                    name="A",
                    last_latitude=23.0,
                    last_longitude=72.0,
                    last_accuracy=25,
                    last_location_time=now,
                ),
                models.Device(
                    id="b",
                    user_id=owner.id,
                    name="B",
                    last_latitude=23.0005,
                    last_longitude=72.0,
                    last_accuracy=25,
                    last_location_time=now,
                ),
                models.Device(
                    id="c",
                    user_id=owner.id,
                    name="C",
                    last_latitude=23.0,
                    last_longitude=72.0,
                    last_accuracy=5,
                    last_location_time=now - timedelta(minutes=6),
                ),
            ])
            await session.commit()
            snapshot = await get_device_proximity(threshold_meters=100, current_user=owner, db=session)
            pairs = snapshot["pairs"]
            near_time_pair = next(
                pair for pair in pairs
                if {pair["first_device_id"], pair["second_device_id"]} == {"a", "b"}
            )
            skewed_pair = next(
                pair for pair in pairs
                if {pair["first_device_id"], pair["second_device_id"]} == {"a", "c"}
            )
            assert near_time_pair["status"] == "UNCERTAIN"
            assert skewed_pair["status"] == "UNKNOWN"
            assert snapshot["threshold_meters"] == 100
        await engine.dispose()

    asyncio.run(run_flow())
