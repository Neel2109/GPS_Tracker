import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def record_geofence_transitions(
    db: AsyncSession,
    device: models.Device,
    points: list[models.Location],
) -> list[models.Alert]:
    if not points:
        return []

    result = await db.execute(
        select(models.Geofence).where(
            models.Geofence.user_id == device.user_id,
            models.Geofence.enabled.is_(True),
        )
    )
    geofences = result.scalars().all()
    if not geofences:
        return []

    states_result = await db.execute(
        select(models.GeofenceState).where(
            models.GeofenceState.device_id == device.id,
            models.GeofenceState.geofence_id.in_([fence.id for fence in geofences]),
        )
    )
    states = {state.geofence_id: state for state in states_result.scalars().all()}
    alerts: list[models.Alert] = []

    for point in sorted(points, key=lambda item: item.timestamp):
        for geofence in geofences:
            state = states.get(geofence.id)
            distance = _distance_meters(
                point.latitude,
                point.longitude,
                geofence.latitude,
                geofence.longitude,
            )
            uncertainty = min(max(point.accuracy or 0, 0), 50)
            if state is None:
                state = models.GeofenceState(
                    geofence_id=geofence.id,
                    device_id=device.id,
                    inside=distance <= geofence.radius,
                    updated_at=point.timestamp,
                )
                states[geofence.id] = state
                db.add(state)
                continue

            if point.timestamp <= state.updated_at:
                continue

            is_inside = distance + uncertainty < geofence.radius if not state.inside else distance - uncertainty <= geofence.radius
            if is_inside == state.inside:
                continue

            state.inside = is_inside
            state.updated_at = point.timestamp
            event_type = "GEOFENCE_ENTER" if is_inside else "GEOFENCE_EXIT"
            verb = "entered" if is_inside else "exited"
            alert = models.Alert(
                user_id=device.user_id,
                device_id=device.id,
                type=event_type,
                title=f"{device.name} {verb} {geofence.name}",
                message=f"{device.name} {verb} the {geofence.name} geofence.",
                created_at=datetime.utcnow(),
            )
            db.add(alert)
            alerts.append(alert)

    return alerts


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return earth_radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))
