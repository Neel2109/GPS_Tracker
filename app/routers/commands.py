from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import get_db
from app.websocket_manager import manager

router = APIRouter(prefix="/api/devices", tags=["commands"])

async def queue_command(device_id: str, command_type: str, current_user: models.User, db: AsyncSession):
    # Verify ownership
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    db_cmd = models.Command(
        device_id=device_id,
        user_id=current_user.id,
        command=command_type
    )
    db.add(db_cmd)
    
    # Audit log
    audit = models.AuditLog(
        device_id=device_id,
        action=f"COMMAND_{command_type}",
        details=f"Command initiated by user {current_user.email}"
    )
    db.add(audit)
    
    await db.commit()
    await db.refresh(db_cmd)
    
    # Send via WebSocket if online
    sent = await manager.send_to_device(device_id, {
        "type": "COMMAND",
        "command_id": db_cmd.id,
        "command": command_type
    })
    
    return db_cmd

@router.post("/{device_id}/commands/lock", response_model=schemas.CommandResponse)
async def lock_device(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "LOCK", current_user, db)

@router.post("/{device_id}/commands/sleep", response_model=schemas.CommandResponse)
async def sleep_device(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "SLEEP", current_user, db)

@router.post("/{device_id}/commands/restart", response_model=schemas.CommandResponse)
async def restart_device(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "RESTART", current_user, db)

@router.post("/{device_id}/commands/shutdown", response_model=schemas.CommandResponse)
async def shutdown_device(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "SHUTDOWN", current_user, db)

@router.post("/{device_id}/commands/status", response_model=schemas.CommandResponse)
async def request_status(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "GET_STATUS", current_user, db)

@router.post("/{device_id}/commands/location", response_model=schemas.CommandResponse)
async def request_location(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "GET_LOCATION", current_user, db)

@router.post("/{device_id}/commands/ping", response_model=schemas.CommandResponse)
async def ping_device(device_id: str, current_user: models.User = Depends(security.get_current_user), db: AsyncSession = Depends(get_db)):
    return await queue_command(device_id, "PING", current_user, db)

@router.get("/{device_id}/commands", response_model=List[schemas.CommandResponse])
async def get_commands(
    device_id: str,
    limit: int = Query(50),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify ownership
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")
        
    cmd_result = await db.execute(
        select(models.Command)
        .where(models.Command.device_id == device_id)
        .order_by(models.Command.created_at.desc())
        .limit(limit)
    )
    return cmd_result.scalars().all()

@router.get("/{device_id}/audit", response_model=List[schemas.AuditLogResponse])
async def get_audit_logs(
    device_id: str,
    limit: int = Query(50),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")
        
    log_result = await db.execute(
        select(models.AuditLog)
        .where(models.AuditLog.device_id == device_id)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(limit)
    )
    return log_result.scalars().all()
