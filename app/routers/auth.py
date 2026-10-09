import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request
from sqlalchemy import and_, delete, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import set_committed_value
from app import models, schemas, security
from app.database import get_db
from app.config import settings
from app import sms
from app.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    matching_totp_counter,
    provisioning_uri,
)
from app.phone import normalize_phone_number

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_failed_pin_attempts: dict[str, deque[float]] = defaultdict(deque)
PIN_ATTEMPT_WINDOW_SECONDS = 60
PIN_MAX_ATTEMPTS = 5
PHONE_RECOVERY_CODE_TTL = timedelta(minutes=5)
PHONE_RECOVERY_RATE_WINDOW = timedelta(minutes=15)
PHONE_RECOVERY_RETENTION = timedelta(days=1)
PHONE_RECOVERY_MAX_ATTEMPTS = 5
PHONE_RECOVERY_MAX_PHONE_REQUESTS = 3
PHONE_RECOVERY_MAX_IP_REQUESTS = 10
PHONE_VERIFICATION_CODE_TTL = timedelta(minutes=5)
PHONE_VERIFICATION_MAX_ATTEMPTS = 5
PHONE_VERIFICATION_MAX_PHONE_REQUESTS = 3
PHONE_VERIFICATION_MAX_IP_REQUESTS = 10


def _check_attempt_limit(request: Request) -> tuple[str, deque[float]]:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _failed_pin_attempts[client_ip]
    while attempts and now - attempts[0] >= PIN_ATTEMPT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= PIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect sign-in attempts. Wait one minute and try again.",
        )
    return client_ip, attempts


def _record_failed_attempt(attempts: deque[float]) -> None:
    attempts.append(time.monotonic())


def _configured_super_admin_phone() -> str | None:
    configured_phone = settings.super_admin_phone.strip()
    if not configured_phone:
        return None
    owner_phone = settings.local_user_phone.strip()
    try:
        configured_phone = normalize_phone_number(configured_phone)
        owner_phone = normalize_phone_number(owner_phone)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set matching E.164 LOCAL_USER_PHONE and SUPER_ADMIN_PHONE values.",
        ) from error
    if configured_phone != owner_phone:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUPER_ADMIN_PHONE must match LOCAL_USER_PHONE.",
        )
    return configured_phone


async def _verify_pin(
    request: Request,
    pin: str,
) -> tuple[str, deque[float]]:
    configured_pin = settings.local_pin
    if not configured_pin or not configured_pin.isdigit() or not 6 <= len(configured_pin) <= 12:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set LOCAL_PIN to a 6–12 digit PIN in the server .env file",
        )

    client_ip, attempts = _check_attempt_limit(request)
    if not hmac.compare_digest(pin, configured_pin):
        _record_failed_attempt(attempts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Incorrect PIN. Enter the effective LOCAL_PIN configured for the API server; "
                "a process environment variable overrides the .env value. The phone's unlock "
                "PIN is not used."
            ),
        )
    return client_ip, attempts


async def _get_local_user(db: AsyncSession) -> models.User:
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

    configured_phone = settings.local_user_phone.strip()
    if configured_phone:
        try:
            configured_phone = normalize_phone_number(configured_phone)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LOCAL_USER_PHONE must use E.164 format, including the country code.",
            ) from error
        if user.phone_number and user.phone_number != configured_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="LOCAL_USER_PHONE does not match the selected TrackGuard account.",
            )
        phone_owner_result = await db.execute(
            select(models.User).where(
                models.User.phone_number == configured_phone,
                models.User.id != user.id,
            )
        )
        if phone_owner_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="LOCAL_USER_PHONE is already assigned to another account.",
            )
        user.phone_number = configured_phone

    configured_super_admin_phone = _configured_super_admin_phone()
    if configured_super_admin_phone:
        if user.phone_number != configured_super_admin_phone:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SUPER_ADMIN_PHONE does not match the selected local owner account.",
            )
        user.role = "SUPER_ADMIN"

    await db.commit()
    await db.refresh(user)
    return user


async def _create_auth_session(
    db: AsyncSession,
    user: models.User,
    request: Request,
) -> models.AuthSession:
    now = datetime.utcnow()
    auth_session = models.AuthSession(
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        auth_time=int(time.time()),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
    )
    db.add(auth_session)
    await db.flush()
    return auth_session


def _make_token_response(
    user: models.User,
    auth_session: models.AuthSession,
    auth_method: str = "totp",
) -> dict:
    claims = {
        "sub": user.id,
        "mfa": auth_method == "totp",
        "auth_method": auth_method,
        "role": user.role,
        "sid": auth_session.id,
        "auth_time": auth_session.auth_time,
    }
    return {
        "access_token": security.create_access_token(data=claims),
        "refresh_token": security.create_refresh_token(data=claims),
        "token_type": "bearer",
        "user": user,
    }


async def _consume_totp_code(
    db: AsyncSession,
    credential: models.TotpCredential,
    code: str,
) -> bool:
    secret = decrypt_totp_secret(credential.encrypted_secret)
    counter = matching_totp_counter(secret, code)
    if counter is None:
        return False

    result = await db.execute(
        update(models.TotpCredential)
        .where(
            models.TotpCredential.user_id == credential.user_id,
            or_(
                models.TotpCredential.last_counter.is_(None),
                models.TotpCredential.last_counter < counter,
            ),
        )
        .values(last_counter=counter)
    )
    if result.rowcount != 1:
        return False
    set_committed_value(credential, "last_counter", counter)
    return True


def _require_phone_recovery_available() -> None:
    if not sms.twilio_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone authenticator recovery is unavailable because Twilio SMS is not configured.",
        )
    if len(settings.phone_recovery_hmac_key.strip().encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Phone authenticator recovery is unavailable because its hashing key "
                "is not configured with at least 32 characters."
            ),
        )


def _require_phone_verification_available() -> None:
    if not sms.twilio_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification is unavailable because Twilio SMS is not configured.",
        )
    if len(settings.phone_recovery_hmac_key.strip().encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Phone verification is unavailable because PHONE_RECOVERY_HMAC_KEY "
                "is not configured with at least 32 characters."
            ),
        )


def _phone_recovery_hash(value: str, purpose: str) -> str:
    key = settings.phone_recovery_hmac_key.strip().encode("utf-8")
    return hmac.new(
        key,
        f"{purpose}:{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@router.post(
    "/phone/verification/request",
    response_model=schemas.PhoneRecoveryRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_phone_verification(
    request: Request,
    credentials: schemas.PhoneVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    _require_phone_verification_available()
    phone_number = normalize_phone_number(credentials.phone_number)
    client_ip = request.client.host if request.client else "unknown"
    phone_hash = _phone_recovery_hash(phone_number, "phone")
    ip_hash = _phone_recovery_hash(client_ip, "ip")
    now = datetime.utcnow()
    cutoff = now - PHONE_RECOVERY_RATE_WINDOW

    await db.execute(
        delete(models.PhoneVerificationChallenge).where(
            models.PhoneVerificationChallenge.created_at < now - PHONE_RECOVERY_RETENTION
        )
    )
    phone_requests = await db.scalar(
        select(func.count(models.PhoneVerificationChallenge.id)).where(
            and_(
                models.PhoneVerificationChallenge.phone_hash == phone_hash,
                models.PhoneVerificationChallenge.created_at >= cutoff,
            )
        )
    ) or 0
    ip_requests = await db.scalar(
        select(func.count(models.PhoneVerificationChallenge.id)).where(
            and_(
                models.PhoneVerificationChallenge.ip_hash == ip_hash,
                models.PhoneVerificationChallenge.created_at >= cutoff,
            )
        )
    ) or 0
    if (
        phone_requests >= PHONE_VERIFICATION_MAX_PHONE_REQUESTS
        or ip_requests >= PHONE_VERIFICATION_MAX_IP_REQUESTS
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification requests. Try again later.",
        )

    user = await db.scalar(
        select(models.User).where(models.User.phone_number == phone_number)
    )
    credential = None
    if user is not None and user.account_status == "ACTIVE":
        credential = await db.scalar(
            select(models.TotpCredential).where(
                models.TotpCredential.user_id == user.id
            )
        )
    eligible_user = (
        user
        if credential is not None and user is not None
        else None
    )

    await db.execute(
        update(models.PhoneVerificationChallenge)
        .where(
            and_(
                models.PhoneVerificationChallenge.phone_hash == phone_hash,
                models.PhoneVerificationChallenge.consumed_at.is_(None),
            )
        )
        .values(consumed_at=now)
    )
    challenge_id = models.generate_uuid()
    code = f"{secrets.randbelow(1_000_000):06d}" if eligible_user is not None else None
    challenge = models.PhoneVerificationChallenge(
        id=challenge_id,
        user_id=eligible_user.id if eligible_user is not None else None,
        phone_hash=phone_hash,
        ip_hash=ip_hash,
        code_hash=(
            _phone_recovery_hash(f"{challenge_id}:{code}", "verification-code")
            if code is not None
            else None
        ),
        created_at=now,
        expires_at=now + PHONE_VERIFICATION_CODE_TTL,
    )
    db.add(challenge)
    await db.commit()

    if eligible_user is not None and code is not None:
        try:
            await sms.send_phone_verification_code(phone_number, code)
        except sms.SMSProviderUnavailable:
            challenge.code_hash = None
            challenge.consumed_at = datetime.utcnow()
            await db.commit()
            logger.warning("Twilio phone-verification SMS delivery failed.")
        else:
            challenge.sent_at = datetime.utcnow()
            await db.commit()

    return schemas.PhoneRecoveryRequestResponse(
        message=(
            "If this phone number belongs to an eligible TrackGuard account, "
            "a verification code may be sent. This response does not confirm "
            "account existence or message delivery."
        )
    )


@router.post(
    "/phone/verification/confirm",
    response_model=schemas.PhoneRecoveryRequestResponse,
)
async def confirm_phone_verification(
    credentials: schemas.PhoneVerificationConfirm,
    db: AsyncSession = Depends(get_db),
):
    _require_phone_verification_available()
    phone_number = normalize_phone_number(credentials.phone_number)
    phone_hash = _phone_recovery_hash(phone_number, "phone")
    now = datetime.utcnow()
    challenge = await db.scalar(
        select(models.PhoneVerificationChallenge)
        .where(models.PhoneVerificationChallenge.phone_hash == phone_hash)
        .order_by(models.PhoneVerificationChallenge.created_at.desc())
        .limit(1)
    )
    if (
        challenge is None
        or challenge.user_id is None
        or challenge.code_hash is None
        or challenge.sent_at is None
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.attempt_count >= PHONE_VERIFICATION_MAX_ATTEMPTS
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code is invalid or expired.",
        )

    provided_hash = _phone_recovery_hash(
        f"{challenge.id}:{credentials.otp_code}",
        "verification-code",
    )
    if not hmac.compare_digest(challenge.code_hash, provided_hash):
        challenge.attempt_count += 1
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code is invalid or expired.",
        )

    user = await db.get(models.User, challenge.user_id)
    if user is None or user.phone_number != phone_number or user.account_status != "ACTIVE":
        challenge.consumed_at = now
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code is invalid or expired.",
        )

    user.phone_verified_at = now
    challenge.consumed_at = now
    await db.commit()
    return schemas.PhoneRecoveryRequestResponse(message="Phone number verified.")


async def _check_phone_recovery_request_limit(
    db: AsyncSession,
    phone_hash: str,
    ip_hash: str,
    now: datetime,
) -> None:
    cutoff = now - PHONE_RECOVERY_RATE_WINDOW
    await db.execute(
        delete(models.PhoneRecoveryChallenge).where(
            models.PhoneRecoveryChallenge.created_at < now - PHONE_RECOVERY_RETENTION
        )
    )
    phone_requests = await db.scalar(
        select(func.count(models.PhoneRecoveryChallenge.id)).where(
            and_(
                models.PhoneRecoveryChallenge.phone_hash == phone_hash,
                models.PhoneRecoveryChallenge.created_at >= cutoff,
            )
        )
    ) or 0
    ip_requests = await db.scalar(
        select(func.count(models.PhoneRecoveryChallenge.id)).where(
            and_(
                models.PhoneRecoveryChallenge.ip_hash == ip_hash,
                models.PhoneRecoveryChallenge.created_at >= cutoff,
            )
        )
    ) or 0
    if (
        phone_requests >= PHONE_RECOVERY_MAX_PHONE_REQUESTS
        or ip_requests >= PHONE_RECOVERY_MAX_IP_REQUESTS
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many recovery requests. Try again later.",
        )


def _invalid_phone_recovery_code() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Recovery code is invalid or expired.",
    )


@router.post(
    "/phone/recovery/request",
    response_model=schemas.PhoneRecoveryRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_phone_recovery(
    request: Request,
    credentials: schemas.PhoneRecoveryRequest,
    db: AsyncSession = Depends(get_db),
):
    _require_phone_recovery_available()
    phone_number = normalize_phone_number(credentials.phone_number)
    client_ip = request.client.host if request.client else "unknown"
    phone_hash = _phone_recovery_hash(phone_number, "phone")
    ip_hash = _phone_recovery_hash(client_ip, "ip")
    now = datetime.utcnow()

    await _check_phone_recovery_request_limit(db, phone_hash, ip_hash, now)

    user = await db.scalar(
        select(models.User).where(models.User.phone_number == phone_number)
    )
    credential = None
    if user is not None and user.account_status == "ACTIVE":
        credential = await db.scalar(
            select(models.TotpCredential).where(
                models.TotpCredential.user_id == user.id
            )
        )
    eligible_user = (
        user
        if user is not None
        and user.account_status == "ACTIVE"
        and credential is not None
        and credential.enabled
        else None
    )

    await db.execute(
        update(models.PhoneRecoveryChallenge)
        .where(
            and_(
                models.PhoneRecoveryChallenge.phone_hash == phone_hash,
                models.PhoneRecoveryChallenge.consumed_at.is_(None),
            )
        )
        .values(consumed_at=now)
    )
    challenge_id = models.generate_uuid()
    code = f"{secrets.randbelow(1_000_000):06d}" if eligible_user is not None else None
    challenge = models.PhoneRecoveryChallenge(
        id=challenge_id,
        user_id=eligible_user.id if eligible_user is not None else None,
        phone_hash=phone_hash,
        ip_hash=ip_hash,
        code_hash=(
            _phone_recovery_hash(f"{challenge_id}:{code}", "code")
            if code is not None
            else None
        ),
        attempt_count=0,
        created_at=now,
        expires_at=now + PHONE_RECOVERY_CODE_TTL,
    )
    db.add(challenge)
    await db.commit()

    if eligible_user is not None and code is not None:
        try:
            await sms.send_recovery_code(phone_number, code)
        except sms.SMSProviderUnavailable:
            challenge.code_hash = None
            challenge.consumed_at = datetime.utcnow()
            await db.commit()
            logger.warning("Twilio recovery SMS delivery failed.")
        else:
            challenge.sent_at = datetime.utcnow()
            await db.commit()

    return schemas.PhoneRecoveryRequestResponse(
        message=(
            "If this phone number is linked to an active account, recovery "
            "instructions may be sent. This response does not confirm account "
            "existence or message delivery."
        )
    )


@router.post(
    "/phone/recovery/confirm",
    response_model=schemas.TotpSetupResponse,
)
async def confirm_phone_recovery(
    credentials: schemas.PhoneRecoveryConfirm,
    db: AsyncSession = Depends(get_db),
):
    _require_phone_recovery_available()
    phone_number = normalize_phone_number(credentials.phone_number)
    phone_hash = _phone_recovery_hash(phone_number, "phone")
    now = datetime.utcnow()
    challenge = await db.scalar(
        select(models.PhoneRecoveryChallenge)
        .where(models.PhoneRecoveryChallenge.phone_hash == phone_hash)
        .order_by(models.PhoneRecoveryChallenge.created_at.desc())
        .limit(1)
    )
    if (
        challenge is None
        or challenge.user_id is None
        or challenge.code_hash is None
        or challenge.sent_at is None
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.attempt_count >= PHONE_RECOVERY_MAX_ATTEMPTS
    ):
        raise _invalid_phone_recovery_code()

    provided_hash = _phone_recovery_hash(
        f"{challenge.id}:{credentials.otp_code}",
        "code",
    )
    if not hmac.compare_digest(challenge.code_hash, provided_hash):
        await db.execute(
            update(models.PhoneRecoveryChallenge)
            .where(
                and_(
                    models.PhoneRecoveryChallenge.id == challenge.id,
                    models.PhoneRecoveryChallenge.consumed_at.is_(None),
                    models.PhoneRecoveryChallenge.expires_at > now,
                    models.PhoneRecoveryChallenge.attempt_count
                    < PHONE_RECOVERY_MAX_ATTEMPTS,
                )
            )
            .values(
                attempt_count=models.PhoneRecoveryChallenge.attempt_count + 1
            )
        )
        await db.commit()
        raise _invalid_phone_recovery_code()

    user = await db.get(models.User, challenge.user_id)
    totp_credential = (
        await db.get(models.TotpCredential, challenge.user_id)
        if user is not None
        else None
    )
    if (
        user is None
        or user.account_status != "ACTIVE"
        or user.phone_number != phone_number
        or totp_credential is None
        or not totp_credential.enabled
    ):
        await db.execute(
            update(models.PhoneRecoveryChallenge)
            .where(
                and_(
                    models.PhoneRecoveryChallenge.id == challenge.id,
                    models.PhoneRecoveryChallenge.consumed_at.is_(None),
                )
            )
            .values(consumed_at=now)
        )
        await db.commit()
        raise _invalid_phone_recovery_code()

    consumed = await db.execute(
        update(models.PhoneRecoveryChallenge)
        .where(
            and_(
                models.PhoneRecoveryChallenge.id == challenge.id,
                models.PhoneRecoveryChallenge.user_id == user.id,
                models.PhoneRecoveryChallenge.phone_hash == phone_hash,
                models.PhoneRecoveryChallenge.code_hash == provided_hash,
                models.PhoneRecoveryChallenge.sent_at.is_not(None),
                models.PhoneRecoveryChallenge.consumed_at.is_(None),
                models.PhoneRecoveryChallenge.expires_at > now,
                models.PhoneRecoveryChallenge.attempt_count
                < PHONE_RECOVERY_MAX_ATTEMPTS,
            )
        )
        .values(consumed_at=now)
    )
    if consumed.rowcount != 1:
        raise _invalid_phone_recovery_code()

    secret = generate_totp_secret()
    totp_credential.encrypted_secret = encrypt_totp_secret(secret)
    totp_credential.enabled = False
    totp_credential.last_counter = None
    user.phone_verified_at = now
    await db.commit()
    return schemas.TotpSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, phone_number),
    )


@router.post("/unlock", response_model=schemas.Token)
async def unlock_with_pin(
    request: Request,
    credentials: schemas.LocalPinUnlock,
    db: AsyncSession = Depends(get_db),
):
    client_ip, attempts = await _verify_pin(request, credentials.pin)
    user = await _get_local_user(db)
    if user.account_status != "ACTIVE":
        raise HTTPException(status_code=403, detail="This account is suspended.")
    user.last_login_at = datetime.utcnow()
    auth_session = await _create_auth_session(db, user, request)
    await db.commit()
    _failed_pin_attempts.pop(client_ip, None)
    return _make_token_response(user, auth_session, auth_method="pin")


@router.post("/phone/login", response_model=schemas.Token)
async def login_with_phone(
    request: Request,
    credentials: schemas.PhoneTotpLogin,
    db: AsyncSession = Depends(get_db),
):
    client_ip, attempts = _check_attempt_limit(request)
    configured_super_admin_phone = _configured_super_admin_phone()
    result = await db.execute(
        select(models.User).where(models.User.phone_number == credentials.phone_number)
    )
    user = result.scalar_one_or_none()
    if user is None and credentials.phone_number == configured_super_admin_phone:
        user = await _get_local_user(db)
    if user is None or user.account_status != "ACTIVE":
        _record_failed_attempt(attempts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or authenticator code.",
        )

    totp_result = await db.execute(
        select(models.TotpCredential).where(models.TotpCredential.user_id == user.id)
    )
    credential = totp_result.scalar_one_or_none()
    if (
        credential is None
        or not credential.enabled
        or not await _consume_totp_code(db, credential, credentials.otp_code)
    ):
        _record_failed_attempt(attempts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or authenticator code.",
        )

    if user.phone_number and user.phone_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify phone ownership by SMS before signing in.",
        )

    if credentials.phone_number == configured_super_admin_phone:
        user.role = "SUPER_ADMIN"
    user.last_login_at = datetime.utcnow()
    auth_session = await _create_auth_session(db, user, request)
    await db.commit()
    _failed_pin_attempts.pop(client_ip, None)
    return _make_token_response(user, auth_session)


@router.post("/phone/activate", response_model=schemas.Token)
async def activate_phone_account(
    request: Request,
    credentials: schemas.PhoneTotpActivation,
    db: AsyncSession = Depends(get_db),
):
    client_ip, attempts = _check_attempt_limit(request)
    result = await db.execute(
        select(models.User).where(models.User.phone_number == credentials.phone_number)
    )
    user = result.scalar_one_or_none()
    credential = None
    if user is not None:
        totp_result = await db.execute(
            select(models.TotpCredential).where(models.TotpCredential.user_id == user.id)
        )
        credential = totp_result.scalar_one_or_none()
    if (
        user is None
        or user.account_status != "ACTIVE"
        or user.phone_verified_at is None
        or credential is None
        or credential.enabled
        or not await _consume_totp_code(db, credential, credentials.otp_code)
    ):
        _record_failed_attempt(attempts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account activation failed. Check your phone number and authenticator setup key.",
        )

    credential.enabled = True
    user.last_login_at = datetime.utcnow()
    auth_session = await _create_auth_session(db, user, request)
    await db.commit()
    _failed_pin_attempts.pop(client_ip, None)
    return _make_token_response(user, auth_session)


@router.post("/phone/invitation/setup", response_model=schemas.TotpSetupResponse)
async def claim_account_invitation(
    credentials: schemas.PhoneInvitationClaim,
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(
        select(models.User).where(models.User.phone_number == credentials.phone_number)
    )
    if (
        user is None
        or user.account_status != "ACTIVE"
        or user.phone_verified_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify the invited phone number before setting up the authenticator.",
        )

    token_hash = hashlib.sha256(credentials.invitation_token.encode("utf-8")).hexdigest()
    now = datetime.utcnow()
    invitation = await db.scalar(
        select(models.AccountInvitation).where(
            models.AccountInvitation.user_id == user.id,
            models.AccountInvitation.token_hash == token_hash,
            models.AccountInvitation.consumed_at.is_(None),
            models.AccountInvitation.revoked_at.is_(None),
            models.AccountInvitation.expires_at > now,
        )
    )
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is invalid, expired, or already used. Ask an administrator for a new invitation.",
        )

    consumed = await db.execute(
        update(models.AccountInvitation)
        .where(
            models.AccountInvitation.id == invitation.id,
            models.AccountInvitation.consumed_at.is_(None),
            models.AccountInvitation.revoked_at.is_(None),
            models.AccountInvitation.expires_at > now,
        )
        .values(consumed_at=now)
    )
    if consumed.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invitation has already been used or revoked.",
        )

    secret = generate_totp_secret()
    credential = await db.get(models.TotpCredential, user.id)
    if credential is None:
        credential = models.TotpCredential(
            user_id=user.id,
            encrypted_secret=encrypt_totp_secret(secret),
            enabled=False,
        )
        db.add(credential)
    elif credential.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An authenticator is already active for this account. Use account recovery instead.",
        )
    else:
        credential.encrypted_secret = encrypt_totp_secret(secret)
        credential.last_counter = None
    await db.commit()
    return schemas.TotpSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, credentials.phone_number),
    )


@router.post("/totp/setup", response_model=schemas.TotpSetupResponse)
async def setup_totp(
    request: Request,
    credentials: schemas.LocalPinUnlock,
    db: AsyncSession = Depends(get_db),
):
    await _verify_pin(request, credentials.pin)
    user = await _get_local_user(db)
    if user.account_status != "ACTIVE":
        raise HTTPException(status_code=403, detail="This account is suspended.")
    if credentials.phone_number:
        try:
            requested_phone = normalize_phone_number(credentials.phone_number)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        configured_phone = settings.local_user_phone.strip()
        if configured_phone and requested_phone != normalize_phone_number(configured_phone):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The phone number must match LOCAL_USER_PHONE configured by the server.",
            )
        if user.phone_number and user.phone_number != requested_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This account is already assigned to a different phone number.",
            )
        existing_phone_owner = await db.scalar(
            select(models.User.id).where(
                models.User.phone_number == requested_phone,
                models.User.id != user.id,
            )
        )
        if existing_phone_owner is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That phone number is already assigned to another account.",
            )
        user.phone_number = requested_phone
        await db.commit()
        await db.refresh(user)
    result = await db.execute(
        select(models.TotpCredential).where(models.TotpCredential.user_id == user.id)
    )
    totp_credential = result.scalar_one_or_none()
    if totp_credential is not None and totp_credential.enabled:
        detail = (
            "Phone number linked. This account's authenticator is already enabled; sign in with your phone number."
            if credentials.phone_number
            else "Authenticator is already enabled."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    if totp_credential is None:
        secret = generate_totp_secret()
        totp_credential = models.TotpCredential(
            user_id=user.id,
            encrypted_secret=encrypt_totp_secret(secret),
            enabled=False,
        )
        db.add(totp_credential)
        await db.commit()
    else:
        secret = decrypt_totp_secret(totp_credential.encrypted_secret)

    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(secret, user.phone_number or user.email),
    }


@router.post("/totp/confirm", response_model=schemas.Token)
async def confirm_totp(
    request: Request,
    credentials: schemas.LocalPinTotpConfirm,
    db: AsyncSession = Depends(get_db),
):
    client_ip, attempts = await _verify_pin(request, credentials.pin)
    user = await _get_local_user(db)
    if user.account_status != "ACTIVE":
        raise HTTPException(status_code=403, detail="This account is suspended.")
    if user.phone_number and user.phone_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify phone ownership by SMS before enabling sign-in.",
        )
    result = await db.execute(
        select(models.TotpCredential).where(models.TotpCredential.user_id == user.id)
    )
    totp_credential = result.scalar_one_or_none()
    if totp_credential is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Start authenticator setup first.")
    if not await _consume_totp_code(db, totp_credential, credentials.otp_code):
        _record_failed_attempt(attempts)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect or already-used authenticator code.")
    if not totp_credential.enabled:
        totp_credential.enabled = True
    user.last_login_at = datetime.utcnow()
    auth_session = await _create_auth_session(db, user, request)
    await db.commit()

    _failed_pin_attempts.pop(client_ip, None)
    return _make_token_response(user, auth_session)

@router.post("/refresh", response_model=schemas.Token)
async def refresh_token(token_data: schemas.TokenRefresh, db: AsyncSession = Depends(get_db)):
    try:
        import jwt
        payload = jwt.decode(token_data.refresh_token, security.settings.jwt_secret, algorithms=[security.settings.jwt_algorithm])
        user_id = payload.get("sub")
        if payload.get("type") != "refresh" or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.account_status != "ACTIVE":
        raise HTTPException(status_code=401, detail="User not found")

    totp_result = await db.execute(
        select(models.TotpCredential).where(models.TotpCredential.user_id == user.id)
    )
    credential = totp_result.scalar_one_or_none()
    if payload.get("auth_method") != "pin" and (
        credential is None or not credential.enabled or payload.get("mfa") is not True
    ):
        raise HTTPException(status_code=401, detail="Sign in with your authenticator code.")

    session_id = payload.get("sid")
    auth_session = await db.get(models.AuthSession, session_id) if isinstance(session_id, str) else None
    if (
        auth_session is None
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(status_code=401, detail="This session has expired or was revoked. Sign in again.")
    auth_session.last_seen_at = datetime.utcnow()
    await db.commit()
    auth_method = "pin" if payload.get("auth_method") == "pin" else "totp"
    return _make_token_response(user, auth_session, auth_method=auth_method)

@router.post("/logout")
async def logout(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_id = getattr(current_user, "_trackguard_session_id", None)
    auth_session = await db.get(models.AuthSession, session_id) if isinstance(session_id, str) else None
    if auth_session is None or auth_session.user_id != current_user.id:
        raise HTTPException(status_code=401, detail="Sign in again before logging out.")
    auth_session.revoked_at = datetime.utcnow()
    await db.commit()
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=schemas.UserResponse)
async def get_me(current_user: models.User = Depends(security.get_current_user)):
    return current_user
