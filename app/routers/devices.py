import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import get_db
from app.services.proximity import build_proximity_snapshot

router = APIRouter(prefix="/api/devices", tags=["devices"])

def generate_pairing_code():
    return secrets.token_urlsafe(32)

@router.get("", response_model=List[schemas.DeviceResponse])
async def list_devices(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(models.Device.user_id == current_user.id))
    return result.scalars().all()

@router.get("/proximity", response_model=schemas.DeviceProximitySnapshot)
async def get_device_proximity(
    threshold_meters: int = Query(default=250, ge=25, le=5000),
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.Device)
        .where(models.Device.user_id == current_user.id)
        .order_by(models.Device.name, models.Device.id)
    )
    return build_proximity_snapshot(
        list(result.scalars().all()),
        now=datetime.now(timezone.utc),
        threshold_meters=threshold_meters,
    )

@router.post("/pair/generate", response_model=schemas.PairingCodeResponse)
async def generate_code(
    device_info: schemas.DeviceBase,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    code = generate_pairing_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    db_code = models.PairingCode(
        code=code,
        user_id=current_user.id,
        device_name=device_info.name,
        device_type=device_info.device_type,
        expires_at=expires
    )
    db.add(db_code)
    await db.commit()
    await db.refresh(db_code)
    return db_code

@router.post("/pair/activate", response_model=schemas.DevicePairingResponse)
async def activate_device(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    # Find active pairing code
    result = await db.execute(select(models.PairingCode).where(
        models.PairingCode.code == code,
        models.PairingCode.expires_at > datetime.utcnow()
    ))
    pairing = result.scalar_one_or_none()
    
    if not pairing:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
        
    # Create the device
    device_id = str(uuid.uuid4())
    db_device = models.Device(
        id=device_id,
        user_id=pairing.user_id,
        name=pairing.device_name,
        device_type=pairing.device_type,
        status="offline"
    )
    db.add(db_device)
    
    # Remove the pairing code so it can't be used again
    await db.delete(pairing)
    await db.commit()
    
    # Create device token
    # We use a special token format for devices to distinguish them from users
    access_token = security.create_access_token(data={"sub": device_id, "is_device": True}, expires_delta=timedelta(days=3650))
    
    # The agent stores these credentials for its authenticated WebSocket connection.
    return {
        "id": device_id,
        "device_token": access_token,
        "name": db_device.name,
    }

@router.get("/{device_id}", response_model=schemas.DeviceResponse)
async def get_device(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    await db.delete(device)
    await db.commit()
    return {"message": "Device deleted"}

@router.post("/{device_id}/lost-mode/enable")
async def enable_lost_mode(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    device.is_lost_mode = True
    await db.commit()
    
    from app.websocket_manager import manager
    await manager.send_to_dashboard(current_user.id, {"type": "LOST_MODE_ENABLED", "device_id": device_id})
    await manager.send_to_device(device_id, {"type": "ENABLE_LOST_MODE", "data": {"interval": 10}})
    
    return {"message": "Lost mode enabled", "is_lost_mode": True}

@router.post("/{device_id}/lost-mode/disable")
async def disable_lost_mode(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    device.is_lost_mode = False
    await db.commit()
    
    from app.websocket_manager import manager
    await manager.send_to_dashboard(current_user.id, {"type": "LOST_MODE_DISABLED", "device_id": device_id})
    await manager.send_to_device(device_id, {"type": "DISABLE_LOST_MODE"})
    
    return {"message": "Lost mode disabled", "is_lost_mode": False}
