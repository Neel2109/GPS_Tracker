from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import get_db

router = APIRouter(prefix="/api/devices", tags=["locations"])

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
