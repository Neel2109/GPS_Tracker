from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.websocket_manager import manager


async def queue_authorized_admin_location_updates(
    db: AsyncSession,
    device: models.Device,
    location_data: dict,
) -> list[tuple[str, dict]]:
    result = await db.execute(
        select(models.AdminLocationAccessRequest, models.User)
        .join(
            models.User,
            models.User.id == models.AdminLocationAccessRequest.requester_user_id,
        )
        .where(
            models.AdminLocationAccessRequest.target_user_id == device.user_id,
            models.AdminLocationAccessRequest.scope == "LOCATION_READ",
            models.AdminLocationAccessRequest.status == "APPROVED",
            models.AdminLocationAccessRequest.expires_at > datetime.utcnow(),
            models.User.role.in_(("ADMIN", "SUPER_ADMIN")),
            models.User.account_status == "ACTIVE",
        )
    )
    owner = await db.get(models.User, device.user_id)
    updates: list[tuple[str, dict]] = []
    for access_request, admin_user in result.all():
        if admin_user.id not in manager.dashboard_connections:
            continue
        db.add(models.AdminAuditEvent(
            actor_user_id=admin_user.id,
            action="ADMIN_LIVE_LOCATION_STREAM_READ",
            target_user_id=device.user_id,
            target_device_id=device.id,
            details=f"request_id={access_request.id}; reason={access_request.reason}",
        ))
        updates.append((
            admin_user.id,
            {
                "type": "ADMIN_LIVE_LOCATION_UPDATE",
                "device_id": device.id,
                "access_request_id": access_request.id,
                "owner_user_id": device.user_id,
                "owner_name": owner.name if owner else None,
                "owner_role": owner.role if owner else None,
                "data": location_data,
            },
        ))
    return updates
