from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import models, schemas, security
from app.database import get_db

router = APIRouter(prefix="/api/access-requests", tags=["access requests"])


async def _request_response(
    db: AsyncSession,
    access_request: models.AdminLocationAccessRequest,
) -> schemas.LocationAccessRequestResponse:
    requester = await db.get(models.User, access_request.requester_user_id)
    target = await db.get(models.User, access_request.target_user_id)
    if requester is None or target is None:
        raise HTTPException(status_code=404, detail="The account for this access request no longer exists.")
    target_device = (
        await db.get(models.Device, access_request.target_device_id)
        if access_request.target_device_id
        else None
    )
    return schemas.LocationAccessRequestResponse(
        id=access_request.id,
        requester_user_id=requester.id,
        requester_name=requester.name,
        target_user_id=target.id,
        target_name=target.name,
        target_device_id=access_request.target_device_id,
        target_device_name=target_device.name if target_device else None,
        target_device_type=target_device.device_type if target_device else None,
        scope=access_request.scope,
        status=access_request.status,
        reason=access_request.reason,
        duration_minutes=access_request.duration_minutes,
        created_at=access_request.created_at,
        decided_at=access_request.decided_at,
        expires_at=access_request.expires_at,
    )


@router.get("", response_model=list[schemas.LocationAccessRequestResponse])
async def list_incoming_access_requests(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    requester = aliased(models.User)
    target = aliased(models.User)
    result = await db.execute(
        select(models.AdminLocationAccessRequest, requester, target)
        .join(requester, requester.id == models.AdminLocationAccessRequest.requester_user_id)
        .join(target, target.id == models.AdminLocationAccessRequest.target_user_id)
        .where(models.AdminLocationAccessRequest.target_user_id == current_user.id)
        .order_by(models.AdminLocationAccessRequest.created_at.desc())
        .limit(100)
    )
    rows = result.all()
    access_requests = [row[0] for row in rows]
    now = datetime.utcnow()
    expired = [
        access_request
        for access_request in access_requests
        if access_request.status == "APPROVED"
        and access_request.expires_at is not None
        and access_request.expires_at <= now
    ]
    if expired:
        for access_request in expired:
            access_request.status = "EXPIRED"
            db.add(
                models.AdminAuditEvent(
                    actor_user_id=current_user.id,
                    action=(
                        "OWNER_ADMIN_DEVICE_CONTROL_EXPIRED"
                        if access_request.scope == "DEVICE_CONTROL"
                        else "OWNER_ADMIN_LOCATION_ACCESS_EXPIRED"
                    ),
                    target_user_id=current_user.id,
                    target_device_id=access_request.target_device_id,
                    details=f"request_id={access_request.id}; reason={access_request.reason}",
                )
            )
        await db.commit()
    responses = []
    for access_request, from_user, to_user in rows:
        target_device = (
            await db.get(models.Device, access_request.target_device_id)
            if access_request.target_device_id
            else None
        )
        responses.append(schemas.LocationAccessRequestResponse(
            id=access_request.id,
            requester_user_id=from_user.id,
            requester_name=from_user.name,
            target_user_id=to_user.id,
            target_name=to_user.name,
            target_device_id=access_request.target_device_id,
            target_device_name=target_device.name if target_device else None,
            target_device_type=target_device.device_type if target_device else None,
            scope=access_request.scope,
            status=access_request.status,
            reason=access_request.reason,
            duration_minutes=access_request.duration_minutes,
            created_at=access_request.created_at,
            decided_at=access_request.decided_at,
            expires_at=access_request.expires_at,
        ))
    return responses


@router.post("/{request_id}/decision", response_model=schemas.LocationAccessRequestResponse)
async def decide_access_request(
    request_id: str,
    decision: schemas.LocationAccessRequestDecision,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access_request = await db.scalar(
        select(models.AdminLocationAccessRequest).where(
            models.AdminLocationAccessRequest.id == request_id,
            models.AdminLocationAccessRequest.target_user_id == current_user.id,
        )
    )
    if access_request is None:
        raise HTTPException(status_code=404, detail="Access request not found.")

    now = datetime.utcnow()
    if decision.action in {"APPROVE", "DENY"}:
        if access_request.status != "PENDING":
            raise HTTPException(status_code=409, detail="This request has already been decided.")
        access_request.status = {
            "APPROVE": "APPROVED",
            "DENY": "DENIED",
        }[decision.action]
        access_request.decided_at = now
        if decision.action == "APPROVE":
            access_request.expires_at = now + timedelta(minutes=access_request.duration_minutes)
    elif decision.action == "REVOKE":
        if access_request.status != "APPROVED" or access_request.expires_at is None:
            raise HTTPException(status_code=409, detail="There is no active approved grant to revoke.")
        if access_request.expires_at <= now:
            access_request.status = "EXPIRED"
            db.add(
                models.AdminAuditEvent(
                    actor_user_id=current_user.id,
                    action=(
                        "OWNER_EXPIRED_ADMIN_DEVICE_CONTROL"
                        if access_request.scope == "DEVICE_CONTROL"
                        else "OWNER_EXPIRED_ADMIN_LOCATION_ACCESS"
                    ),
                    target_user_id=access_request.target_user_id,
                    target_device_id=access_request.target_device_id,
                    details=f"request_id={access_request.id}; reason={access_request.reason}",
                )
            )
            await db.commit()
            raise HTTPException(status_code=409, detail="This access grant has expired.")
        access_request.status = "REVOKED"
        access_request.decided_at = now

    scope_label = (
        "ADMIN_LOCATION_ACCESS"
        if access_request.scope == "LOCATION_READ"
        else "ADMIN_DEVICE_CONTROL"
    )
    db.add(
        models.AdminAuditEvent(
            actor_user_id=current_user.id,
            action=f"OWNER_{decision.action}_{scope_label}",
            target_user_id=access_request.target_user_id,
            target_device_id=access_request.target_device_id,
            details=f"request_id={access_request.id}; reason={access_request.reason}",
        )
    )
    await db.commit()
    await db.refresh(access_request)
    return await _request_response(db, access_request)
