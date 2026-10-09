import asyncio
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import models, schemas
from app.database import Base
from app.routers.tracking import update_alert_status
from app.services.incidents import synchronize_device_incidents


def test_device_incidents_persist_acknowledge_resolve_and_recur():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            owner = models.User(
                name="Incident Owner",
                email="incident-owner@example.com",
                password_hash="test",
            )
            other_owner = models.User(
                name="Other Owner",
                email="other-incident-owner@example.com",
                password_hash="test",
            )
            session.add_all([owner, other_owner])
            await session.flush()
            device = models.Device(
                id="incident-device",
                user_id=owner.id,
                name="Test Phone",
                battery_level=15,
            )
            session.add(device)
            await session.commit()

            created = await synchronize_device_incidents(
                session,
                device,
                connected=True,
            )
            assert [alert.type for alert in created] == ["LOW_BATTERY"]
            await session.commit()
            alert = created[0]
            await session.refresh(alert)
            assert alert.status == "OPEN"

            assert await synchronize_device_incidents(
                session,
                device,
                connected=True,
            ) == []

            acknowledged = await update_alert_status(
                alert.id,
                schemas.AlertStatusUpdate(status="ACKNOWLEDGED"),
                owner,
                session,
            )
            assert acknowledged.status == "ACKNOWLEDGED"
            assert acknowledged.acknowledged_at is not None

            try:
                await update_alert_status(
                    alert.id,
                    schemas.AlertStatusUpdate(status="RESOLVED"),
                    other_owner,
                    session,
                )
            except HTTPException as error:
                assert error.status_code == 404
            else:
                raise AssertionError("An account must not mutate another owner's incident.")

            device.battery_level = 35
            recovered = await synchronize_device_incidents(
                session,
                device,
                connected=True,
            )
            assert recovered == [alert]
            assert alert.status == "RESOLVED"
            assert alert.resolved_at is not None
            await session.commit()

            status_events = await session.scalar(
                select(func.count(models.AlertStatusEvent.id)).where(
                    models.AlertStatusEvent.alert_id == alert.id
                )
            )
            assert status_events == 2

            device.battery_level = 10
            recurring = await synchronize_device_incidents(
                session,
                device,
                connected=True,
                now=datetime.utcnow(),
            )
            assert len(recurring) == 1
            assert recurring[0].id != alert.id
            assert recurring[0].status == "OPEN"

            disconnected = await synchronize_device_incidents(
                session,
                device,
                connected=False,
            )
            assert [item.type for item in disconnected] == ["DEVICE_OFFLINE"]
            reconnected = await synchronize_device_incidents(
                session,
                device,
                connected=True,
            )
            assert len(reconnected) == 1
            assert reconnected[0].type == "DEVICE_OFFLINE"
            assert reconnected[0].status == "RESOLVED"

        await engine.dispose()

    asyncio.run(run_flow())
