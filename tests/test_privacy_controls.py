import asyncio
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import models
from app.database import Base
from app.routers.privacy import delete_own_location_history, export_account_data


def test_export_and_deletion_are_limited_to_authenticated_owners_devices():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            owner = models.User(
                name="Owner",
                email="owner@example.com",
                password_hash="must-not-export",
                phone_number="+14155550123",
            )
            other_owner = models.User(
                name="Other",
                email="other@example.com",
                password_hash="also-secret",
            )
            session.add_all([owner, other_owner])
            await session.flush()
            owned_device = models.Device(id="owned-device", user_id=owner.id, name="Owner phone")
            other_device = models.Device(id="other-device", user_id=other_owner.id, name="Other phone")
            session.add_all([owned_device, other_device])
            await session.flush()
            own_point = models.Location(
                id="owner-point",
                device_id=owned_device.id,
                latitude=23.0,
                longitude=72.0,
                timestamp=datetime(2026, 1, 1),
            )
            other_point = models.Location(
                id="other-point",
                device_id=other_device.id,
                latitude=24.0,
                longitude=73.0,
                timestamp=datetime(2026, 1, 1),
            )
            session.add_all([own_point, other_point])
            await session.commit()

            export = await export_account_data(owner, session)
            assert [point["id"] for point in export["locations"]] == ["owner-point"]
            assert "password_hash" not in export["profile"]
            assert export["retention_policy"] == "Location history is retained until you delete it."

            try:
                await delete_own_location_history("wrong-confirmation", owner, session)
                raise AssertionError("A mismatched confirmation must not delete any history.")
            except HTTPException as error:
                assert error.status_code == 400

            result = await delete_own_location_history(
                "DELETE_MY_LOCATION_HISTORY",
                owner,
                session,
            )
            remaining = list((await session.scalars(select(models.Location))).all())
            assert result == {"deleted_locations": 1}
            assert [point.id for point in remaining] == ["other-point"]
        await engine.dispose()

    asyncio.run(run_flow())
