import hmac
import secrets
import time
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

_failed_pin_attempts: dict[str, deque[float]] = defaultdict(deque)
PIN_ATTEMPT_WINDOW_SECONDS = 60
PIN_MAX_ATTEMPTS = 5

@router.post("/unlock", response_model=schemas.Token)
async def unlock_with_pin(
    request: Request,
    credentials: schemas.LocalPinUnlock,
    db: AsyncSession = Depends(get_db),
):
    configured_pin = settings.local_pin
    if not configured_pin or not configured_pin.isdigit() or not 6 <= len(configured_pin) <= 12:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set LOCAL_PIN to a 6–12 digit PIN in the server .env file",
        )

    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _failed_pin_attempts[client_ip]
    while attempts and now - attempts[0] >= PIN_ATTEMPT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= PIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect PIN attempts. Wait one minute and try again.",
        )
    if not hmac.compare_digest(credentials.pin, configured_pin):
        attempts.append(now)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect PIN")
    _failed_pin_attempts.pop(client_ip, None)

    result = await db.execute(select(models.User).order_by(models.User.created_at))
    users = list(result.scalars().all())
    user = next((item for item in users if item.email == settings.local_user_email), None)
    if user is None and len(users) == 1:
        user = users[0]
    elif user is None and len(users) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Set LOCAL_USER_EMAIL in the server .env to choose the TrackGuard account",
        )

    if user is None:
        user = models.User(
            name=settings.local_user_name,
            email=settings.local_user_email,
            password_hash=security.get_password_hash(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = security.create_access_token(data={"sub": user.id})
    refresh_token = security.create_refresh_token(data={"sub": user.id})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }

@router.post("/refresh", response_model=schemas.Token)
async def refresh_token(token_data: schemas.TokenRefresh, db: AsyncSession = Depends(get_db)):
    try:
        import jwt
        payload = jwt.decode(token_data.refresh_token, security.settings.jwt_secret, algorithms=[security.settings.jwt_algorithm])
        user_id = payload.get("sub")
        if payload.get("type") != "refresh" or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    access_token = security.create_access_token(data={"sub": user.id})
    refresh_token = security.create_refresh_token(data={"sub": user.id})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "user": user}

@router.post("/logout")
async def logout(current_user: models.User = Depends(security.get_current_user)):
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=schemas.UserResponse)
async def get_me(current_user: models.User = Depends(security.get_current_user)):
    return current_user
