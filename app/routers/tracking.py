import hashlib
import math
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas, security
from app.database import get_db
from app.services.incidents import change_alert_status, synchronize_device_incidents
from app.websocket_manager import manager

router = APIRouter(tags=["tracking"])


@router.get("/api/geofences", response_model=List[schemas.GeofenceResponse])
async def list_geofences(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.Geofence)
        .where(models.Geofence.user_id == current_user.id)
        .order_by(models.Geofence.created_at.desc())
    )
    return result.scalars().all()


@router.post("/api/geofences", response_model=schemas.GeofenceResponse, status_code=201)
async def create_geofence(
    payload: schemas.GeofenceCreate,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    geofence = models.Geofence(user_id=current_user.id, **payload.model_dump())
    db.add(geofence)
    await db.commit()
    await db.refresh(geofence)
    return geofence


@router.patch("/api/geofences/{geofence_id}", response_model=schemas.GeofenceResponse)
async def update_geofence(
    geofence_id: str,
    payload: schemas.GeofenceUpdate,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    geofence = await _owned_geofence(geofence_id, current_user.id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(geofence, field, value)
    await db.commit()
    await db.refresh(geofence)
    return geofence


@router.delete("/api/geofences/{geofence_id}", status_code=204)
async def delete_geofence(
    geofence_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    geofence = await _owned_geofence(geofence_id, current_user.id, db)
    await db.execute(
        delete(models.GeofenceState).where(models.GeofenceState.geofence_id == geofence.id)
    )
    await db.delete(geofence)
    await db.commit()


@router.get("/api/alerts", response_model=List[schemas.AlertResponse])
async def list_alerts(
    unread_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(models.Alert).where(models.Alert.user_id == current_user.id)
    if unread_only:
        query = query.where(models.Alert.read.is_(False))
    result = await db.execute(query.order_by(models.Alert.created_at.desc()).limit(limit))
    return result.scalars().all()


@router.post("/api/alerts/{alert_id}/read", response_model=schemas.AlertResponse)
async def mark_alert_read(
    alert_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _owned_alert(alert_id, current_user.id, db)
    if alert.status == "OPEN":
        change_alert_status(
            db,
            alert,
            "ACKNOWLEDGED",
            actor_user_id=current_user.id,
        )
    await db.commit()
    await db.refresh(alert)
    await manager.send_to_dashboard(current_user.id, {
        "type": "ALERT_UPDATED",
        "device_id": alert.device_id,
        "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
    })
    return alert


@router.post("/api/alerts/{alert_id}/status", response_model=schemas.AlertResponse)
async def update_alert_status(
    alert_id: str,
    payload: schemas.AlertStatusUpdate,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _owned_alert(alert_id, current_user.id, db)
    if alert.status == "RESOLVED" and payload.status != "RESOLVED":
        raise HTTPException(
            status_code=409,
            detail="Resolved alerts cannot be reopened; a new event will create a new alert.",
        )
    change_alert_status(
        db,
        alert,
        payload.status,
        actor_user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(alert)
    await manager.send_to_dashboard(current_user.id, {
        "type": "ALERT_UPDATED",
        "device_id": alert.device_id,
        "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
    })
    return alert


@router.post("/api/alerts/read-all", status_code=204)
async def mark_all_alerts_read(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.Alert).where(
            models.Alert.user_id == current_user.id,
            models.Alert.read.is_(False),
        )
    )
    for alert in result.scalars().all():
        if alert.status == "OPEN":
            change_alert_status(
                db,
                alert,
                "ACKNOWLEDGED",
                actor_user_id=current_user.id,
            )
    await db.commit()
    await manager.send_to_dashboard(current_user.id, {"type": "ALERT_UPDATED"})


@router.post("/api/alerts/sos", response_model=schemas.AlertResponse, status_code=201)
async def create_sos_alert(
    payload: schemas.SosCreate,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="SOS message cannot be blank")

    device = None
    if payload.device_id:
        device_result = await db.execute(
            select(models.Device).where(
                models.Device.id == payload.device_id,
                models.Device.user_id == current_user.id,
            )
        )
        device = device_result.scalar_one_or_none()
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

    alert = models.Alert(
        user_id=current_user.id,
        device_id=device.id if device else None,
        type="SOS",
        title="SOS assistance requested",
        message=message,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    await manager.send_to_dashboard(current_user.id, {
        "type": "ALERT_CREATED",
        "device_id": alert.device_id,
        "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
    })
    return alert


@router.get("/api/devices/{device_id}/trips", response_model=List[schemas.TripResponse])
async def list_device_trips(
    device_id: str,
    period: str = Query(default="30days", pattern="^(today|7days|30days|all)$"),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_device(device_id, current_user.id, db)
    points = await _trip_points(device_id, period, db)
    return [_trip_summary(device_id, segment) for segment in _split_trips(points)]


@router.get(
    "/api/devices/{device_id}/trips/{trip_id}/locations",
    response_model=List[schemas.LocationResponse],
)
async def get_trip_locations(
    device_id: str,
    trip_id: str,
    period: str = Query(default="30days", pattern="^(today|7days|30days|all)$"),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_device(device_id, current_user.id, db)
    segments = _split_trips(await _trip_points(device_id, period, db))
    for segment in segments:
        if _trip_id(device_id, segment[0]) == trip_id:
            return segment
    raise HTTPException(status_code=404, detail="Trip not found in the selected period")


async def _owned_geofence(geofence_id: str, user_id: str, db: AsyncSession) -> models.Geofence:
    result = await db.execute(
        select(models.Geofence).where(
            models.Geofence.id == geofence_id,
            models.Geofence.user_id == user_id,
        )
    )
    geofence = result.scalar_one_or_none()
    if geofence is None:
        raise HTTPException(status_code=404, detail="Geofence not found")
    return geofence


async def _owned_alert(alert_id: str, user_id: str, db: AsyncSession) -> models.Alert:
    result = await db.execute(
        select(models.Alert).where(
            models.Alert.id == alert_id,
            models.Alert.user_id == user_id,
        )
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


async def _owned_device(device_id: str, user_id: str, db: AsyncSession) -> models.Device:
    result = await db.execute(
        select(models.Device).where(
            models.Device.id == device_id,
            models.Device.user_id == user_id,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


async def _trip_points(device_id: str, period: str, db: AsyncSession) -> list[models.Location]:
    query = select(models.Location).where(models.Location.device_id == device_id)
    now = datetime.utcnow()
    if period == "today":
        query = query.where(models.Location.timestamp >= now.replace(hour=0, minute=0, second=0, microsecond=0))
    elif period == "7days":
        query = query.where(models.Location.timestamp >= now - timedelta(days=7))
    elif period == "30days":
        query = query.where(models.Location.timestamp >= now - timedelta(days=30))
    result = await db.execute(
        query.order_by(models.Location.timestamp.desc()).limit(10000)
    )
    points = list(result.scalars().all())
    points.reverse()
    return points


def _split_trips(points: list[models.Location]) -> list[list[models.Location]]:
    if not points:
        return []
    segments: list[list[models.Location]] = []
    current = [points[0]]
    for point in points[1:]:
        if point.timestamp - current[-1].timestamp > timedelta(minutes=30):
            if len(current) >= 2:
                segments.append(current)
            current = []
        current.append(point)
    if len(current) >= 2:
        segments.append(current)
    return segments


def _trip_id(device_id: str, first: models.Location) -> str:
    return hashlib.sha256(f"{device_id}:{first.id}".encode()).hexdigest()[:32]


def _trip_summary(device_id: str, points: list[models.Location]) -> dict:
    distance = sum(
        _distance_meters(a.latitude, a.longitude, b.latitude, b.longitude)
        for a, b in zip(points, points[1:])
    )
    duration = max(0.0, (points[-1].timestamp - points[0].timestamp).total_seconds())
    speeds = [point.speed for point in points if point.speed is not None and point.speed >= 0]
    stop_durations = []
    stop_started_at = None
    last_stationary_at = None
    for point in points:
        if (point.movement_state or "").upper() == "STATIONARY":
            if stop_started_at is None:
                stop_started_at = point.timestamp
            last_stationary_at = point.timestamp
        elif stop_started_at is not None and last_stationary_at is not None:
            stopped_seconds = (last_stationary_at - stop_started_at).total_seconds()
            if stopped_seconds >= 300:
                stop_durations.append(stopped_seconds)
            stop_started_at = None
            last_stationary_at = None
    if stop_started_at is not None and last_stationary_at is not None:
        stopped_seconds = (last_stationary_at - stop_started_at).total_seconds()
        if stopped_seconds >= 300:
            stop_durations.append(stopped_seconds)
    return {
        "id": _trip_id(device_id, points[0]),
        "device_id": device_id,
        "start_time": points[0].timestamp,
        "end_time": points[-1].timestamp,
        "start_latitude": points[0].latitude,
        "start_longitude": points[0].longitude,
        "end_latitude": points[-1].latitude,
        "end_longitude": points[-1].longitude,
        "distance_meters": distance,
        "duration_seconds": duration,
        "average_speed": sum(speeds) / len(speeds) if speeds else None,
        "maximum_speed": max(speeds) if speeds else None,
        "point_count": len(points),
        "stop_count": len(stop_durations),
        "active_duration_seconds": max(0.0, duration - sum(stop_durations)),
    }


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return earth_radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))
