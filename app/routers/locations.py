from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import get_db
from app.services.admin_live import queue_authorized_admin_location_updates
from app.services.geofences import record_geofence_transitions
from app.services.incidents import synchronize_device_incidents
from app.websocket_manager import manager

router = APIRouter(prefix="/api/devices", tags=["locations"])
device_bearer = HTTPBearer()


async def authenticate_tracking_device(
    device_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(device_bearer),
    db: AsyncSession = Depends(get_db),
) -> models.Device:
    try:
        payload = security.jwt.decode(
            credentials.credentials,
            security.settings.jwt_secret,
            algorithms=[security.settings.jwt_algorithm],
        )
    except security.jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token") from error

    if payload.get("sub") != device_id or payload.get("is_device") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")

    result = await db.execute(select(models.Device).where(models.Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.post("/{device_id}/locations/batch")
async def upload_location_batch(
    device_id: str,
    batch: schemas.DeviceLocationBatch,
    device: models.Device = Depends(authenticate_tracking_device),
    db: AsyncSession = Depends(get_db),
):
    accepted = 0
    duplicates = 0
    now = datetime.utcnow()
    new_points: list[models.Location] = []

    for point in batch.locations:
        timestamp = point.timestamp or now
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

        existing_result = await db.execute(
            select(models.Location.id).where(
                models.Location.device_id == device_id,
                models.Location.timestamp == timestamp,
                models.Location.latitude == point.latitude,
                models.Location.longitude == point.longitude,
            ).limit(1)
        )
        if existing_result.scalar_one_or_none() is not None:
            duplicates += 1
            continue

        speed = point.speed
        movement_state = point.movement_state
        if movement_state == "STATIONARY" and speed is not None and speed > 2:
            movement_state = "DRIVING" if speed > 30 else "CYCLING" if speed > 8 else "WALKING"

        location = models.Location(
            device_id=device_id,
            latitude=point.latitude,
            longitude=point.longitude,
            accuracy=point.accuracy,
            altitude=point.altitude,
            speed=speed,
            heading=point.heading,
            source=point.source or "gps",
            movement_state=movement_state,
            timestamp=timestamp,
        )
        db.add(location)
        new_points.append(location)
        accepted += 1

        if device.last_location_time is None or timestamp >= device.last_location_time:
            device.last_latitude = point.latitude
            device.last_longitude = point.longitude
            device.last_accuracy = point.accuracy
            device.last_location_source = point.source or "gps"
            device.last_location_time = timestamp
            device.last_speed = speed
            device.last_heading = point.heading
            device.last_movement_state = movement_state

    device.last_seen = now
    device.status = "online"
    device.connection_state = "online"
    if device.last_online is None:
        device.last_online = now
    alerts = await record_geofence_transitions(db, device, new_points)
    alerts.extend(
        await synchronize_device_incidents(
            db,
            device,
            connected=True,
            now=now,
        )
    )
    admin_live_updates = []
    if accepted and device.last_latitude is not None and device.last_longitude is not None:
        admin_live_updates = await queue_authorized_admin_location_updates(
            db,
            device,
            {
                "latitude": device.last_latitude,
                "longitude": device.last_longitude,
                "accuracy": device.last_accuracy,
                "source": device.last_location_source,
                "timestamp": device.last_location_time.isoformat() if device.last_location_time else None,
                "movement_state": device.last_movement_state,
                "speed": device.last_speed,
            },
        )
    await db.commit()
    for admin_user_id, live_update in admin_live_updates:
        await manager.send_to_dashboard(admin_user_id, live_update)
    for alert in alerts:
        await db.refresh(alert)
        await manager.send_to_dashboard(device.user_id, {
            "type": "ALERT_CREATED" if alert.status == "OPEN" else "ALERT_UPDATED",
            "device_id": alert.device_id,
            "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
        })
    return {"accepted": accepted, "duplicates": duplicates}

@router.get("/{device_id}/location", response_model=Optional[schemas.LocationResponse])
async def get_current_location(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify ownership
    device_result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    if not device_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")
        
    result = await db.execute(
        select(models.Location)
        .where(models.Location.device_id == device_id)
        .order_by(models.Location.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()

@router.get("/{device_id}/locations", response_model=List[schemas.LocationResponse])
async def get_location_history(
    device_id: str,
    period: str = Query("today", description="Time period filter (today, yesterday, 7days, 30days)"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(500, le=10000),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify ownership
    device_result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    if not device_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")
        
    query = select(models.Location).where(models.Location.device_id == device_id)
    
    if start_date and end_date:
        query = query.where(models.Location.timestamp >= start_date, models.Location.timestamp <= end_date)
    else:
        now = datetime.utcnow()
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.where(models.Location.timestamp >= start)
        elif period == "yesterday":
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=1)
            query = query.where(models.Location.timestamp >= start, models.Location.timestamp < end)
        elif period == "7days":
            start = now - timedelta(days=7)
            query = query.where(models.Location.timestamp >= start)
        elif period == "30days":
            start = now - timedelta(days=30)
            query = query.where(models.Location.timestamp >= start)
            
    query = query.order_by(models.Location.timestamp.desc()).limit(limit)
    result = await db.execute(query)
    
    locations = list(result.scalars().all())
    locations.reverse()  # chronological order
    return locations
