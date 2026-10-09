from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas, security
from app.database import get_db

router = APIRouter(prefix="/api/account", tags=["account privacy"])


@router.get("/export")
async def export_account_data(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    devices_result = await db.execute(
        select(models.Device)
        .where(models.Device.user_id == current_user.id)
        .order_by(models.Device.created_at.asc())
    )
    devices = list(devices_result.scalars().all())
    device_ids = [device.id for device in devices]

    locations = []
    if device_ids:
        locations_result = await db.execute(
            select(models.Location)
            .where(models.Location.device_id.in_(device_ids))
            .order_by(models.Location.timestamp.asc())
        )
        locations = list(locations_result.scalars().all())

    geofences_result = await db.execute(
        select(models.Geofence)
        .where(models.Geofence.user_id == current_user.id)
        .order_by(models.Geofence.created_at.asc())
    )
    alerts_result = await db.execute(
        select(models.Alert)
        .where(models.Alert.user_id == current_user.id)
        .order_by(models.Alert.created_at.asc())
    )
    access_requests_result = await db.execute(
        select(models.AdminLocationAccessRequest)
        .where(
            (models.AdminLocationAccessRequest.requester_user_id == current_user.id)
            | (models.AdminLocationAccessRequest.target_user_id == current_user.id)
        )
        .order_by(models.AdminLocationAccessRequest.created_at.asc())
    )

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "retention_policy": "Location history is retained until you delete it.",
        "profile": schemas.UserResponse.model_validate(current_user).model_dump(mode="json"),
        "devices": [
            schemas.DeviceResponse.model_validate(device).model_dump(mode="json")
            for device in devices
        ],
        "locations": [
            schemas.LocationResponse.model_validate(location).model_dump(mode="json")
            for location in locations
        ],
        "geofences": [
            schemas.GeofenceResponse.model_validate(geofence).model_dump(mode="json")
            for geofence in geofences_result.scalars().all()
        ],
        "alerts": [
            schemas.AlertResponse.model_validate(alert).model_dump(mode="json")
            for alert in alerts_result.scalars().all()
        ],
        "access_requests": [
            {
                "id": access_request.id,
                "requester_user_id": access_request.requester_user_id,
                "target_user_id": access_request.target_user_id,
                "target_device_id": access_request.target_device_id,
                "scope": access_request.scope,
                "status": access_request.status,
                "reason": access_request.reason,
                "duration_minutes": access_request.duration_minutes,
                "created_at": access_request.created_at.isoformat(),
                "decided_at": access_request.decided_at.isoformat() if access_request.decided_at else None,
                "expires_at": access_request.expires_at.isoformat() if access_request.expires_at else None,
            }
            for access_request in access_requests_result.scalars().all()
        ],
    }


@router.delete("/location-history")
async def delete_own_location_history(
    confirmation: str = Query(..., min_length=1, max_length=64),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if confirmation != "DELETE_MY_LOCATION_HISTORY":
        raise HTTPException(
            status_code=400,
            detail="Confirmation must be DELETE_MY_LOCATION_HISTORY.",
        )

    owned_devices = await db.execute(
        select(models.Device.id).where(models.Device.user_id == current_user.id)
    )
    device_ids = list(owned_devices.scalars().all())
    if not device_ids:
        return {"deleted_locations": 0}

    result = await db.execute(
        delete(models.Location).where(models.Location.device_id.in_(device_ids))
    )
    await db.commit()
    return {"deleted_locations": result.rowcount or 0}
