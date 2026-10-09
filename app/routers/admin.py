import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas, security
from app.database import get_db
from app.phone import normalize_phone_number
from app.security import (
    get_admin_user,
    get_recent_admin_user,
    get_recent_super_admin_user,
)
from app.services.incidents import change_alert_status
from app.totp import encrypt_totp_secret, generate_totp_secret, provisioning_uri
from app.websocket_manager import manager

router = APIRouter(prefix="/api/admin", tags=["admin"])
INVITATION_TTL = timedelta(hours=48)


def _contains_filter(value: str):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _issue_invitation(user_id: str) -> tuple[str, datetime, models.AccountInvitation]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + INVITATION_TTL
    invitation = models.AccountInvitation(
        user_id=user_id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=expires_at,
    )
    return token, expires_at, invitation


async def _replace_invitation(
    db: AsyncSession,
    user_id: str,
) -> tuple[str, datetime]:
    now = datetime.utcnow()
    result = await db.execute(
        select(models.AccountInvitation).where(
            models.AccountInvitation.user_id == user_id,
            models.AccountInvitation.consumed_at.is_(None),
            models.AccountInvitation.revoked_at.is_(None),
        )
    )
    for invitation in result.scalars().all():
        invitation.revoked_at = now
    token, expires_at, invitation = _issue_invitation(user_id)
    db.add(invitation)
    return token, expires_at


def _record_admin_event(
    db: AsyncSession,
    request: Request,
    actor: models.User,
    action: str,
    *,
    target_user_id: str | None = None,
    target_device_id: str | None = None,
    details: str | None = None,
) -> None:
    db.add(
        models.AdminAuditEvent(
            actor_user_id=actor.id,
            action=action,
            target_user_id=target_user_id,
            target_device_id=target_device_id,
            details=details,
            ip_address=request.client.host if request.client else None,
        )
    )


async def _user_device_counts(db: AsyncSession) -> list[schemas.AdminUserResponse]:
    result = await db.execute(
        select(models.User, func.count(models.Device.id))
        .outerjoin(models.Device, models.Device.user_id == models.User.id)
        .group_by(models.User.id)
        .order_by(models.User.created_at.desc())
    )
    return [
        schemas.AdminUserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone_number=user.phone_number,
            phone_verified_at=user.phone_verified_at,
            role=user.role,
            account_status=user.account_status,
            device_count=device_count,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
        for user, device_count in result.all()
    ]


@router.get("/overview", response_model=schemas.AdminOverview)
async def get_admin_overview(
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_users = await db.scalar(select(func.count(models.User.id))) or 0
    active_users = await db.scalar(
        select(func.count(models.User.id)).where(models.User.account_status == "ACTIVE")
    ) or 0
    admin_users = await db.scalar(
        select(func.count(models.User.id)).where(
            models.User.role.in_(("ADMIN", "SUPER_ADMIN"))
        )
    ) or 0
    total_devices = await db.scalar(select(func.count(models.Device.id))) or 0
    online_devices = await db.scalar(
        select(func.count(models.Device.id)).where(models.Device.status == "online")
    ) or 0

    _record_admin_event(db, request, actor, "ADMIN_OVERVIEW_VIEWED")
    await db.commit()
    return schemas.AdminOverview(
        total_users=total_users,
        active_users=active_users,
        admins=admin_users,
        total_devices=total_devices,
        online_devices=online_devices,
    )


@router.get("/users", response_model=list[schemas.AdminUserResponse])
async def list_admin_users(
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    users = await _user_device_counts(db)
    _record_admin_event(db, request, actor, "ADMIN_USER_LIST_VIEWED")
    await db.commit()
    return users


@router.get("/users/page", response_model=schemas.AdminUserPage)
async def list_admin_users_page(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    search: str = Query(default="", max_length=120),
    role: str = Query(default="ALL", pattern="^(ALL|USER|ADMIN|SUPER_ADMIN)$"),
    account_status: str = Query(default="ALL", alias="status", pattern="^(ALL|ACTIVE|SUSPENDED)$"),
    sort_by: str = Query(default="created_at", pattern="^(created_at|name|last_login_at)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if search:
        pattern = _contains_filter(search)
        filters.append(
            models.User.name.ilike(pattern, escape="\\")
            | models.User.email.ilike(pattern, escape="\\")
            | models.User.phone_number.ilike(pattern, escape="\\")
            | models.User.id.ilike(pattern, escape="\\")
        )
    if role != "ALL":
        filters.append(models.User.role == role)
    if account_status != "ALL":
        filters.append(models.User.account_status == account_status)

    total = await db.scalar(
        select(func.count(models.User.id)).where(*filters)
    ) or 0
    sort_column = {
        "created_at": models.User.created_at,
        "name": models.User.name,
        "last_login_at": models.User.last_login_at,
    }[sort_by]
    ordering = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    result = await db.execute(
        select(models.User, func.count(models.Device.id))
        .outerjoin(models.Device, models.Device.user_id == models.User.id)
        .where(*filters)
        .group_by(models.User.id)
        .order_by(ordering, models.User.id.asc())
        .offset(offset)
        .limit(limit)
    )
    items = [
        schemas.AdminUserResponse(
            id=account.id,
            name=account.name,
            email=account.email,
            phone_number=account.phone_number,
            phone_verified_at=account.phone_verified_at,
            role=account.role,
            account_status=account.account_status,
            device_count=device_count,
            created_at=account.created_at,
            last_login_at=account.last_login_at,
        )
        for account, device_count in result.all()
    ]
    _record_admin_event(db, request, actor, "ADMIN_USER_PAGE_VIEWED")
    await db.commit()
    return schemas.AdminUserPage(items=items, total=total, offset=offset, limit=limit)


@router.post("/users", response_model=schemas.AdminUserProvisioned, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: schemas.AdminUserCreate,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Account holder name cannot be blank.")
    if payload.role == "ADMIN" and actor.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Only a super-administrator can create administrators.")

    try:
        phone_number = normalize_phone_number(payload.phone_number)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    existing = await db.scalar(
        select(models.User.id).where(models.User.phone_number == phone_number)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account already uses this phone number.")

    email_local_part = phone_number[1:]
    user = models.User(
        name=payload.name.strip(),
        email=f"phone-{email_local_part}@phone.trackguard.local",
        phone_number=phone_number,
        role=payload.role,
        account_status="ACTIVE",
        password_hash=security.get_password_hash(secrets.token_urlsafe(32)),
    )
    db.add(user)
    await db.flush()
    invitation_token, invitation_expires_at, invitation = _issue_invitation(user.id)
    db.add(invitation)
    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_USER_CREATED",
        target_user_id=user.id,
        details=f"role={payload.role}; invitation_expires_at={invitation_expires_at.isoformat()}",
    )
    await db.commit()
    await db.refresh(user)

    return schemas.AdminUserProvisioned(
        id=user.id,
        name=user.name,
        email=user.email,
        phone_number=user.phone_number,
        phone_verified_at=user.phone_verified_at,
        role=user.role,
        account_status=user.account_status,
        device_count=0,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        invitation_token=invitation_token,
        invitation_expires_at=invitation_expires_at,
    )


@router.patch("/users/{user_id}", response_model=schemas.AdminUserResponse)
async def update_admin_user(
    user_id: str,
    payload: schemas.AdminUserUpdate,
    request: Request,
    actor: models.User = Depends(get_recent_admin_user),
    db: AsyncSession = Depends(get_db),
):
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide a role or account status to update.")
    if updates.get("role") == "SUPER_ADMIN" and actor.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Only a super-administrator can grant this role.")

    user = await db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role == "SUPER_ADMIN" and actor.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Only a super-administrator can manage this account.")

    next_role = updates.get("role", user.role)
    next_status = updates.get("account_status", user.account_status)
    if user.role == "SUPER_ADMIN" and (next_role != "SUPER_ADMIN" or next_status != "ACTIVE"):
        remaining_admins = await db.scalar(
            select(func.count(models.User.id)).where(
                models.User.role == "SUPER_ADMIN",
                models.User.account_status == "ACTIVE",
                models.User.id != user.id,
            )
        ) or 0
        if remaining_admins == 0:
            raise HTTPException(
                status_code=409,
                detail="The last active super-administrator cannot be demoted or suspended.",
            )
    if user.id == actor.id and next_status != "ACTIVE":
        raise HTTPException(status_code=409, detail="You cannot suspend your own account.")

    for field, value in updates.items():
        setattr(user, field, value)
    if next_status == "SUSPENDED":
        await db.execute(
            models.AuthSession.__table__.update()
            .where(
                models.AuthSession.user_id == user.id,
                models.AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.utcnow())
        )
    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_USER_UPDATED",
        target_user_id=user.id,
        details=", ".join(f"{field}={value}" for field, value in sorted(updates.items())),
    )
    await db.commit()
    await db.refresh(user)
    device_count = await db.scalar(
        select(func.count(models.Device.id)).where(models.Device.user_id == user.id)
    ) or 0
    return schemas.AdminUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        phone_number=user.phone_number,
        phone_verified_at=user.phone_verified_at,
        role=user.role,
        account_status=user.account_status,
        device_count=device_count,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/devices", response_model=list[schemas.AdminDeviceResponse])
async def list_admin_devices(
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.Device, models.User)
        .join(models.User, models.Device.user_id == models.User.id)
        .order_by(models.Device.created_at.desc())
    )
    devices = [
        schemas.AdminDeviceResponse(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            platform=device.platform,
            model=device.model,
            status=device.status,
            is_lost_mode=device.is_lost_mode,
            battery_level=device.battery_level,
            last_seen=device.last_seen,
            owner_user_id=owner.id,
            owner_name=owner.name,
            owner_phone_number=owner.phone_number,
            created_at=device.created_at,
        )
        for device, owner in result.all()
    ]
    _record_admin_event(db, request, actor, "ADMIN_DEVICE_LIST_VIEWED")
    await db.commit()
    return devices


@router.get("/devices/page", response_model=schemas.AdminDevicePage)
async def list_admin_devices_page(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    search: str = Query(default="", max_length=120),
    owner_user_id: str | None = Query(default=None, max_length=100),
    status_filter: str = Query(default="ALL", alias="status", max_length=30),
    device_type: str = Query(default="ALL", max_length=40),
    lost_mode: str = Query(default="ALL", pattern="^(ALL|LOST|NORMAL)$"),
    sort_by: str = Query(default="created_at", pattern="^(created_at|name|last_seen)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if search:
        pattern = _contains_filter(search)
        filters.append(
            models.Device.name.ilike(pattern, escape="\\")
            | models.Device.model.ilike(pattern, escape="\\")
            | models.Device.id.ilike(pattern, escape="\\")
            | models.User.name.ilike(pattern, escape="\\")
            | models.User.phone_number.ilike(pattern, escape="\\")
        )
    if owner_user_id:
        filters.append(models.Device.user_id == owner_user_id)
    if status_filter != "ALL":
        filters.append(models.Device.status == status_filter)
    if device_type != "ALL":
        filters.append(models.Device.device_type == device_type)
    if lost_mode != "ALL":
        filters.append(models.Device.is_lost_mode.is_(lost_mode == "LOST"))

    total = await db.scalar(
        select(func.count(models.Device.id))
        .join(models.User, models.Device.user_id == models.User.id)
        .where(*filters)
    ) or 0
    sort_column = {
        "created_at": models.Device.created_at,
        "name": models.Device.name,
        "last_seen": models.Device.last_seen,
    }[sort_by]
    ordering = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    result = await db.execute(
        select(models.Device, models.User)
        .join(models.User, models.Device.user_id == models.User.id)
        .where(*filters)
        .order_by(ordering, models.Device.id.asc())
        .offset(offset)
        .limit(limit)
    )
    items = [
        schemas.AdminDeviceResponse(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            platform=device.platform,
            model=device.model,
            status=device.status,
            is_lost_mode=device.is_lost_mode,
            battery_level=device.battery_level,
            last_seen=device.last_seen,
            owner_user_id=owner.id,
            owner_name=owner.name,
            owner_phone_number=owner.phone_number,
            created_at=device.created_at,
        )
        for device, owner in result.all()
    ]
    _record_admin_event(db, request, actor, "ADMIN_DEVICE_PAGE_VIEWED")
    await db.commit()
    return schemas.AdminDevicePage(items=items, total=total, offset=offset, limit=limit)


@router.get("/audit", response_model=list[schemas.AdminAuditEventResponse])
async def list_admin_audit_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    _record_admin_event(db, request, actor, "ADMIN_AUDIT_LOG_VIEWED")
    await db.commit()
    result = await db.execute(
        select(models.AdminAuditEvent)
        .order_by(models.AdminAuditEvent.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/audit/page", response_model=schemas.AdminAuditEventPage)
async def list_admin_audit_page(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    search: str = Query(default="", max_length=120),
    action: str = Query(default="ALL", max_length=80),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if search:
        pattern = _contains_filter(search)
        filters.append(
            models.AdminAuditEvent.action.ilike(pattern, escape="\\")
            | models.AdminAuditEvent.details.ilike(pattern, escape="\\")
            | models.AdminAuditEvent.actor_user_id.ilike(pattern, escape="\\")
            | models.AdminAuditEvent.target_user_id.ilike(pattern, escape="\\")
            | models.AdminAuditEvent.target_device_id.ilike(pattern, escape="\\")
            | models.AdminAuditEvent.ip_address.ilike(pattern, escape="\\")
        )
    if action != "ALL":
        filters.append(models.AdminAuditEvent.action == action)
    total = await db.scalar(
        select(func.count(models.AdminAuditEvent.id)).where(*filters)
    ) or 0
    ordering = (
        models.AdminAuditEvent.created_at.asc()
        if sort_direction == "asc"
        else models.AdminAuditEvent.created_at.desc()
    )
    result = await db.execute(
        select(models.AdminAuditEvent)
        .where(*filters)
        .order_by(ordering, models.AdminAuditEvent.id.asc())
        .offset(offset)
        .limit(limit)
    )
    items = [
        schemas.AdminAuditEventResponse.model_validate(event, from_attributes=True)
        for event in result.scalars().all()
    ]
    _record_admin_event(db, request, actor, "ADMIN_AUDIT_PAGE_VIEWED")
    await db.commit()
    return schemas.AdminAuditEventPage(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/users/{user_id}/reset-authenticator", response_model=schemas.TotpSetupResponse)
async def reset_user_authenticator(
    user_id: str,
    request: Request,
    actor: models.User = Depends(get_recent_super_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == actor.id:
        raise HTTPException(status_code=409, detail="Use the account's own recovery process to reset your authenticator.")

    result = await db.execute(
        select(models.TotpCredential).where(models.TotpCredential.user_id == user.id)
    )
    credential = result.scalar_one_or_none()
    secret = generate_totp_secret()
    if credential is None:
        credential = models.TotpCredential(
            user_id=user.id,
            encrypted_secret=encrypt_totp_secret(secret),
            enabled=False,
        )
        db.add(credential)
    else:
        credential.encrypted_secret = encrypt_totp_secret(secret)
        credential.enabled = False
        credential.last_counter = None
    await db.execute(
        models.AuthSession.__table__.update()
        .where(
            models.AuthSession.user_id == user.id,
            models.AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.utcnow())
    )

    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_AUTHENTICATOR_RESET",
        target_user_id=user.id,
    )
    await db.commit()
    return schemas.TotpSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, user.phone_number or user.email),
    )


@router.post(
    "/users/{user_id}/invitation",
    response_model=schemas.AccountInvitationResponse,
)
async def create_user_invitation(
    user_id: str,
    request: Request,
    actor: models.User = Depends(get_recent_admin_user),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.account_status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Reactivate the account before issuing an invitation.")
    if not target.phone_number:
        raise HTTPException(status_code=409, detail="Add a phone number before issuing an invitation.")
    credential = await db.get(models.TotpCredential, target.id)
    if credential is not None and credential.enabled:
        raise HTTPException(
            status_code=409,
            detail="The account already has an active authenticator. Reset it before issuing a new invitation.",
        )

    token, expires_at = await _replace_invitation(db, target.id)
    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_ACCOUNT_INVITATION_ISSUED",
        target_user_id=target.id,
        details=f"expires_at={expires_at.isoformat()}",
    )
    await db.commit()
    return schemas.AccountInvitationResponse(
        invitation_token=token,
        invitation_expires_at=expires_at,
    )


@router.get(
    "/users/{user_id}/sessions",
    response_model=list[schemas.AdminSessionResponse],
)
async def list_user_sessions(
    user_id: str,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    _record_admin_event(
        db, request, actor, "ADMIN_USER_SESSIONS_VIEWED", target_user_id=target.id,
    )
    await db.commit()
    result = await db.execute(
        select(models.AuthSession)
        .where(models.AuthSession.user_id == target.id)
        .order_by(models.AuthSession.created_at.desc())
        .limit(100)
    )
    return [
        schemas.AdminSessionResponse.model_validate(session, from_attributes=True)
        for session in result.scalars().all()
    ]


@router.post(
    "/users/{user_id}/sessions/{session_id}/revoke",
    response_model=schemas.AdminSessionResponse,
)
async def revoke_user_session(
    user_id: str,
    session_id: str,
    request: Request,
    actor: models.User = Depends(get_recent_admin_user),
    db: AsyncSession = Depends(get_db),
):
    auth_session = await db.scalar(
        select(models.AuthSession).where(
            models.AuthSession.id == session_id,
            models.AuthSession.user_id == user_id,
        )
    )
    if auth_session is None:
        raise HTTPException(status_code=404, detail="Session not found for this account.")
    if auth_session.user_id == actor.id and auth_session.id == getattr(actor, "_trackguard_session_id", None):
        raise HTTPException(status_code=409, detail="You cannot revoke the session used for this action.")
    if auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.utcnow()
        _record_admin_event(
            db,
            request,
            actor,
            "ADMIN_USER_SESSION_REVOKED",
            target_user_id=user_id,
            details=f"session_id={session_id}",
        )
        await db.commit()
        await db.refresh(auth_session)
    return schemas.AdminSessionResponse.model_validate(auth_session, from_attributes=True)


@router.get("/incidents", response_model=list[schemas.AdminIncidentResponse])
async def list_admin_incidents(
    request: Request,
    status_filter: str = Query(default="OPEN", alias="status", pattern="^(ALL|OPEN|ACKNOWLEDGED|RESOLVED)$"),
    limit: int = Query(default=100, ge=1, le=500),
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(models.Alert, models.User.name, models.Device.name)
        .join(models.User, models.Alert.user_id == models.User.id)
        .outerjoin(models.Device, models.Alert.device_id == models.Device.id)
    )
    if status_filter != "ALL":
        query = query.where(models.Alert.status == status_filter)
    result = await db.execute(
        query.order_by(models.Alert.created_at.desc()).limit(limit)
    )
    _record_admin_event(db, request, actor, "ADMIN_INCIDENTS_VIEWED")
    await db.commit()
    return [
        schemas.AdminIncidentResponse(
            id=alert.id,
            user_id=alert.user_id,
            user_name=user_name,
            device_id=alert.device_id,
            device_name=device_name,
            type=alert.type,
            title=alert.title,
            message=alert.message,
            status=alert.status,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
            resolved_at=alert.resolved_at,
        )
        for alert, user_name, device_name in result.all()
    ]


@router.patch("/incidents/{incident_id}", response_model=schemas.AdminIncidentResponse)
async def update_admin_incident(
    incident_id: str,
    payload: schemas.AlertStatusUpdate,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(models.Alert, incident_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if alert.status == "RESOLVED" and payload.status != "RESOLVED":
        raise HTTPException(status_code=409, detail="Resolved incidents cannot be reopened.")
    change_alert_status(db, alert, payload.status, actor_user_id=actor.id)
    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_INCIDENT_STATUS_UPDATED",
        target_user_id=alert.user_id,
        target_device_id=alert.device_id,
        details=f"incident_id={alert.id}; status={payload.status}",
    )
    await db.commit()
    await db.refresh(alert)
    user = await db.get(models.User, alert.user_id)
    device = await db.get(models.Device, alert.device_id) if alert.device_id else None
    return schemas.AdminIncidentResponse(
        id=alert.id,
        user_id=alert.user_id,
        user_name=user.name if user else "Deleted account",
        device_id=alert.device_id,
        device_name=device.name if device else None,
        type=alert.type,
        title=alert.title,
        message=alert.message,
        status=alert.status,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
    )


async def _require_active_location_grant(
    request_id: str,
    actor: models.User,
    db: AsyncSession,
    *,
    scope: str = "LOCATION_READ",
) -> models.AdminLocationAccessRequest:
    access_request = await db.scalar(
        select(models.AdminLocationAccessRequest).where(
            models.AdminLocationAccessRequest.id == request_id,
            models.AdminLocationAccessRequest.requester_user_id == actor.id,
            models.AdminLocationAccessRequest.scope == scope,
        )
    )
    if access_request is None:
        raise HTTPException(status_code=404, detail="Approved access grant not found.")
    if access_request.status != "APPROVED" or access_request.expires_at is None:
        raise HTTPException(status_code=403, detail="Access has not been approved.")

    now = datetime.utcnow()
    target = await db.get(models.User, access_request.target_user_id)
    if access_request.expires_at <= now or target is None or target.account_status != "ACTIVE":
        expired = access_request.expires_at <= now
        access_request.status = "EXPIRED" if expired else "REVOKED"
        access_request.decided_at = now
        db.add(
            models.AdminAuditEvent(
                actor_user_id=actor.id,
                action=(
                    "ADMIN_DEVICE_CONTROL_EXPIRED"
                    if expired and access_request.scope == "DEVICE_CONTROL"
                    else "ADMIN_LOCATION_ACCESS_EXPIRED"
                    if expired
                    else "ADMIN_ACCESS_TERMINATED"
                ),
                target_user_id=access_request.target_user_id,
                target_device_id=access_request.target_device_id,
                details=f"request_id={access_request.id}; reason={access_request.reason}",
            )
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Access has expired or is no longer available.")
    return access_request


async def _location_access_response(
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


@router.post(
    "/access-requests",
    response_model=schemas.LocationAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location_access_request(
    payload: schemas.LocationAccessRequestCreate,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    reason = payload.reason.strip()
    if len(reason) < 10:
        raise HTTPException(status_code=422, detail="Provide a specific access reason of at least 10 characters.")
    if payload.target_user_id == actor.id:
        raise HTTPException(status_code=422, detail="Use your personal dashboard to view your own device locations.")
    if payload.scope == "DEVICE_CONTROL":
        if payload.duration_minutes != 15:
            raise HTTPException(status_code=422, detail="Device-control approval is limited to 15 minutes.")
        if not payload.target_device_id:
            raise HTTPException(status_code=422, detail="Choose a specific device for control approval.")
    elif payload.target_device_id:
        raise HTTPException(status_code=422, detail="A target device is only used for device-control requests.")
    target = await db.get(models.User, payload.target_user_id)
    if target is None or target.account_status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Active target account not found.")
    target_device = None
    if payload.target_device_id:
        target_device = await db.scalar(
            select(models.Device).where(
                models.Device.id == payload.target_device_id,
                models.Device.user_id == target.id,
            )
        )
        if target_device is None:
            raise HTTPException(status_code=404, detail="Device not found for this account.")
    device_context = f" on {target_device.name}" if target_device else ""

    now = datetime.utcnow()
    existing = await db.scalar(
        select(models.AdminLocationAccessRequest.id).where(
            models.AdminLocationAccessRequest.requester_user_id == actor.id,
            models.AdminLocationAccessRequest.target_user_id == target.id,
            models.AdminLocationAccessRequest.scope == payload.scope,
            models.AdminLocationAccessRequest.target_device_id == payload.target_device_id,
            (
                (models.AdminLocationAccessRequest.status == "PENDING")
                | (
                    (models.AdminLocationAccessRequest.status == "APPROVED")
                    & (models.AdminLocationAccessRequest.expires_at > now)
                )
            ),
        ).limit(1)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="A pending or active request already exists for this scope.")

    access_request = models.AdminLocationAccessRequest(
        requester_user_id=actor.id,
        target_user_id=target.id,
        target_device_id=payload.target_device_id,
        scope=payload.scope,
        status="PENDING",
        reason=reason,
        duration_minutes=payload.duration_minutes,
    )
    db.add(access_request)
    await db.flush()
    db.add(
        models.Alert(
            user_id=target.id,
            type="ADMIN_ACCESS_REQUEST",
            title=(
                "Location access requested"
                if payload.scope == "LOCATION_READ"
                else "Device-control access requested"
            ),
            message=(
                f"{actor.name} requested {payload.scope.lower().replace('_', ' ')} "
                f"{device_context} for {payload.duration_minutes} minutes: {reason}"
            ),
        )
    )
    _record_admin_event(
        db,
        request,
        actor,
        (
            "ADMIN_LOCATION_ACCESS_REQUESTED"
            if payload.scope == "LOCATION_READ"
            else "ADMIN_DEVICE_CONTROL_REQUESTED"
        ),
        target_user_id=target.id,
        target_device_id=payload.target_device_id,
        details=f"request_id={access_request.id}; duration_minutes={payload.duration_minutes}; reason={reason}",
    )
    await db.commit()
    await db.refresh(access_request)
    return await _location_access_response(db, access_request)


@router.get("/access-requests", response_model=list[schemas.LocationAccessRequestResponse])
async def list_own_location_access_requests(
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.AdminLocationAccessRequest)
        .where(models.AdminLocationAccessRequest.requester_user_id == actor.id)
        .order_by(models.AdminLocationAccessRequest.created_at.desc())
        .limit(100)
    )
    access_requests = list(result.scalars().all())
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
                    actor_user_id=actor.id,
                    action=(
                        "ADMIN_DEVICE_CONTROL_EXPIRED"
                        if access_request.scope == "DEVICE_CONTROL"
                        else "ADMIN_LOCATION_ACCESS_EXPIRED"
                    ),
                    target_user_id=access_request.target_user_id,
                    target_device_id=access_request.target_device_id,
                    details=f"request_id={access_request.id}; reason={access_request.reason}",
                )
            )
        await db.commit()
    return [
        await _location_access_response(db, access_request)
        for access_request in access_requests
    ]


@router.post("/access-requests/{request_id}/revoke", response_model=schemas.LocationAccessRequestResponse)
async def revoke_own_location_access_request(
    request_id: str,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    access_request = await db.scalar(
        select(models.AdminLocationAccessRequest).where(
            models.AdminLocationAccessRequest.id == request_id,
            models.AdminLocationAccessRequest.requester_user_id == actor.id,
        )
    )
    if access_request is None:
        raise HTTPException(status_code=404, detail="Access request not found.")
    if access_request.status not in {"PENDING", "APPROVED"}:
        raise HTTPException(status_code=409, detail="This access request is no longer active.")

    access_request.status = "REVOKED"
    access_request.decided_at = datetime.utcnow()
    _record_admin_event(
        db,
        request,
        actor,
        (
            "ADMIN_LOCATION_ACCESS_REVOKED"
            if access_request.scope == "LOCATION_READ"
            else "ADMIN_DEVICE_CONTROL_REVOKED"
        ),
        target_user_id=access_request.target_user_id,
        target_device_id=access_request.target_device_id,
        details=f"request_id={access_request.id}",
    )
    await db.commit()
    await db.refresh(access_request)
    return await _location_access_response(db, access_request)


@router.get(
    "/access-requests/{request_id}/devices",
    response_model=list[schemas.AdminGrantedDeviceLocation],
)
async def list_granted_device_locations(
    request_id: str,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    access_request = await _require_active_location_grant(request_id, actor, db)
    result = await db.execute(
        select(models.Device).where(models.Device.user_id == access_request.target_user_id)
        .order_by(models.Device.created_at.desc())
    )
    devices = list(result.scalars().all())
    owner = await db.get(models.User, access_request.target_user_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="The account for this access grant no longer exists.")
    for device in devices:
        _record_admin_event(
            db,
            request,
            actor,
            "ADMIN_GRANTED_LOCATION_VIEWED",
            target_user_id=access_request.target_user_id,
            target_device_id=device.id,
            details=f"request_id={access_request.id}; reason={access_request.reason}",
        )
    if not devices:
        _record_admin_event(
            db,
            request,
            actor,
            "ADMIN_GRANTED_LOCATION_VIEWED",
            target_user_id=access_request.target_user_id,
            details=f"request_id={access_request.id}; no devices; reason={access_request.reason}",
        )
    await db.commit()
    return [
        schemas.AdminGrantedDeviceLocation(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            status=device.status,
            access_request_id=access_request.id,
            owner_user_id=access_request.target_user_id,
            owner_name=owner.name,
            owner_role=owner.role,
            platform=device.platform,
            model=device.model,
            is_lost_mode=device.is_lost_mode,
            battery_level=device.battery_level,
            is_charging=device.is_charging,
            network_type=device.network_type,
            last_latitude=device.last_latitude,
            last_longitude=device.last_longitude,
            last_accuracy=device.last_accuracy,
            last_location_source=device.last_location_source,
            last_location_time=device.last_location_time,
            last_seen=device.last_seen,
            last_speed=device.last_speed,
            movement_state=device.last_movement_state,
        )
        for device in devices
    ]


@router.get(
    "/access-requests/{request_id}/devices/{device_id}/locations",
    response_model=list[schemas.LocationResponse],
)
async def list_granted_location_history(
    request_id: str,
    device_id: str,
    request: Request,
    period: str = Query(default="7days", pattern=r"^(today|yesterday|7days|30days)$"),
    limit: int = Query(default=500, ge=1, le=5000),
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    access_request = await _require_active_location_grant(request_id, actor, db)
    device = await db.scalar(
        select(models.Device).where(
            models.Device.id == device_id,
            models.Device.user_id == access_request.target_user_id,
        )
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found for this approved account.")

    now = datetime.utcnow()
    query = select(models.Location).where(models.Location.device_id == device.id)
    if period == "today":
        query = query.where(models.Location.timestamp >= now.replace(hour=0, minute=0, second=0, microsecond=0))
    elif period == "yesterday":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(
            models.Location.timestamp >= end - timedelta(days=1),
            models.Location.timestamp < end,
        )
    else:
        days = 7 if period == "7days" else 30
        query = query.where(models.Location.timestamp >= now - timedelta(days=days))

    result = await db.execute(
        query.order_by(models.Location.timestamp.desc()).limit(limit)
    )
    locations = list(result.scalars().all())
    locations.reverse()
    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_GRANTED_LOCATION_HISTORY_VIEWED",
        target_user_id=access_request.target_user_id,
        target_device_id=device.id,
        details=f"request_id={access_request.id}; period={period}; reason={access_request.reason}",
    )
    await db.commit()
    return locations


@router.post(
    "/access-requests/{request_id}/devices/{device_id}/commands",
    response_model=schemas.CommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_approved_device_command(
    request_id: str,
    device_id: str,
    payload: schemas.AdminDeviceCommand,
    request: Request,
    actor: models.User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    access_request = await _require_active_location_grant(
        request_id,
        actor,
        db,
        scope="DEVICE_CONTROL",
    )
    device = await db.scalar(
        select(models.Device).where(
            models.Device.id == device_id,
            models.Device.user_id == access_request.target_user_id,
        )
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found for this approved account.")
    if access_request.target_device_id != device.id:
        raise HTTPException(status_code=403, detail="This grant does not authorize control of that device.")
    if payload.confirmation.strip() != device.name:
        raise HTTPException(
            status_code=422,
            detail="Type the device name exactly to confirm this command.",
        )
    is_windows_agent = (
        device.device_type in {"laptop", "desktop"}
        and (device.platform or "").casefold().startswith("windows")
    )
    supports_lost_mode = device.device_type == "android" or is_windows_agent
    if payload.command in {"LOCK", "SLEEP", "RESTART", "SHUTDOWN"} and not is_windows_agent:
        raise HTTPException(status_code=422, detail="This command is supported only by an online Windows agent.")
    if payload.command in {"ENABLE_LOST_MODE", "DISABLE_LOST_MODE"} and not supports_lost_mode:
        raise HTTPException(status_code=422, detail="Lost Mode is not supported by this device type.")

    if device_id not in manager.device_connections:
        _record_admin_event(
            db,
            request,
            actor,
            "ADMIN_DEVICE_COMMAND_REJECTED_OFFLINE",
            target_user_id=device.user_id,
            target_device_id=device.id,
            details=f"command={payload.command}; request_id={access_request.id}",
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="The device is offline; no command was sent.")

    command = models.Command(
        device_id=device.id,
        user_id=actor.id,
        command=payload.command,
    )
    db.add(command)
    _record_admin_event(
        db,
        request,
        actor,
        "ADMIN_DEVICE_COMMAND_REQUESTED",
        target_user_id=device.user_id,
        target_device_id=device.id,
        details=f"command={payload.command}; request_id={access_request.id}; reason={access_request.reason}",
    )
    await db.commit()
    await db.refresh(command)
    sent = await manager.send_to_device(
        device.id,
        {
            "type": "COMMAND",
            "command_id": command.id,
            "command": payload.command,
        },
    )
    if not sent:
        command.status = "failed"
        command.result = "Device connection was lost before command delivery."
        command.executed_at = datetime.utcnow()
        _record_admin_event(
            db,
            request,
            actor,
            "ADMIN_DEVICE_COMMAND_DELIVERY_FAILED",
            target_user_id=device.user_id,
            target_device_id=device.id,
            details=f"command={payload.command}; request_id={access_request.id}",
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="The device disconnected; no command was delivered.")

    if payload.command == "ENABLE_LOST_MODE":
        device.is_lost_mode = True
    elif payload.command == "DISABLE_LOST_MODE":
        device.is_lost_mode = False
    db.add(
        models.AuditLog(
            device_id=device.id,
            action=f"ADMIN_COMMAND_{payload.command}",
            details=f"Authorized by {actor.id}; request_id={access_request.id}",
        )
    )
    await db.commit()
    await db.refresh(command)
    return command
