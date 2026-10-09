from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


def change_alert_status(
    db: AsyncSession,
    alert: models.Alert,
    new_status: str,
    *,
    actor_user_id: str | None,
    now: datetime | None = None,
) -> bool:
    if alert.status == new_status:
        return False

    timestamp = now or datetime.utcnow()
    old_status = alert.status
    alert.status = new_status
    if new_status in {"ACKNOWLEDGED", "RESOLVED"}:
        alert.read = True
        alert.acknowledged_at = alert.acknowledged_at or timestamp
    if new_status == "RESOLVED":
        alert.resolved_at = timestamp
    db.add(models.AlertStatusEvent(
        alert_id=alert.id,
        actor_user_id=actor_user_id,
        old_status=old_status,
        new_status=new_status,
        created_at=timestamp,
    ))
    return True


async def synchronize_device_incidents(
    db: AsyncSession,
    device: models.Device,
    *,
    connected: bool,
    now: datetime | None = None,
) -> list[models.Alert]:
    timestamp = now or datetime.utcnow()
    conditions = {
        "DEVICE_OFFLINE": (
            not connected,
            "Device connection lost",
            f"{device.name} is no longer connected to TrackGuard.",
        ),
        "LOW_BATTERY": (
            device.battery_level is not None and device.battery_level <= 20,
            "Device battery is low",
            f"{device.name} battery is at {device.battery_level}%.",
        ),
    }
    changed: list[models.Alert] = []

    for incident_type, (is_active, title, message) in conditions.items():
        result = await db.execute(
            select(models.Alert).where(
                models.Alert.device_id == device.id,
                models.Alert.type == incident_type,
                models.Alert.status != "RESOLVED",
            )
        )
        active_alerts = list(result.scalars().all())
        if is_active and not active_alerts:
            alert = models.Alert(
                user_id=device.user_id,
                device_id=device.id,
                type=incident_type,
                title=title,
                message=message,
                status="OPEN",
            )
            db.add(alert)
            changed.append(alert)
        elif not is_active:
            for alert in active_alerts:
                change_alert_status(
                    db,
                    alert,
                    "RESOLVED",
                    actor_user_id=None,
                    now=timestamp,
                )
                changed.append(alert)

    return changed
