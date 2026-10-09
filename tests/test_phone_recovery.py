import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app import models
from app.config import settings
from app.database import Base
from app.routers import auth
from app.schemas import PhoneRecoveryConfirm, PhoneRecoveryRequest
from app.sms import SMSProviderUnavailable, send_recovery_code
from app.totp import decrypt_totp_secret, encrypt_totp_secret, generate_totp_secret


PHONE_NUMBER = "+14155550123"
HMAC_KEY = "test-only-hmac-key-with-at-least-32-bytes"


def _request(path: str = "/api/auth/phone/recovery/request") -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.41", 12345),
        "server": ("test", 80),
    })


async def _create_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_phone_recovery_resets_authenticator_with_single_use_sms_code():
    async def run_flow():
        engine, session_factory = await _create_database()
        try:
            with patch.object(settings, "twilio_account_sid", "AC-test-account"), \
                 patch.object(settings, "twilio_auth_token", "test-auth-token"), \
                 patch.object(settings, "twilio_from_number", "+14155550999"), \
                 patch.object(settings, "phone_recovery_hmac_key", HMAC_KEY), \
                 patch("app.routers.auth.sms.send_recovery_code", new_callable=AsyncMock) as send_sms:
                async with session_factory() as session:
                    old_secret = generate_totp_secret()
                    user = models.User(
                        name="Recovery User",
                        email="recovery@example.com",
                        phone_number=PHONE_NUMBER,
                        password_hash="not-used",
                    )
                    session.add(user)
                    await session.flush()
                    credential = models.TotpCredential(
                        user_id=user.id,
                        encrypted_secret=encrypt_totp_secret(old_secret),
                        enabled=True,
                        last_counter=123,
                    )
                    session.add(credential)
                    await session.commit()

                    response = await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                        session,
                    )
                    assert response.message == (
                        "If this phone number is linked to an active account, recovery "
                        "instructions may be sent. This response does not confirm account "
                        "existence or message delivery."
                    )
                    send_sms.assert_awaited_once()
                    sent_phone, sms_code = send_sms.await_args.args
                    assert sent_phone == PHONE_NUMBER
                    assert len(sms_code) == 6

                    challenge = await session.scalar(
                        select(models.PhoneRecoveryChallenge)
                    )
                    assert challenge is not None
                    assert challenge.code_hash != sms_code
                    assert len(challenge.code_hash) == 64
                    assert challenge.sent_at is not None
                    assert challenge.expires_at <= challenge.created_at + timedelta(minutes=5)

                    reset = await auth.confirm_phone_recovery(
                        PhoneRecoveryConfirm(
                            phone_number=PHONE_NUMBER,
                            otp_code=sms_code,
                        ),
                        session,
                    )
                    assert reset.secret != old_secret
                    assert reset.provisioning_uri.startswith("otpauth://totp/")
                    assert decrypt_totp_secret(credential.encrypted_secret) == reset.secret
                    assert credential.enabled is False
                    assert credential.last_counter is None
                    assert challenge.consumed_at is not None

                    try:
                        await auth.confirm_phone_recovery(
                            PhoneRecoveryConfirm(
                                phone_number=PHONE_NUMBER,
                                otp_code=sms_code,
                            ),
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 400
                        assert error.detail == "Recovery code is invalid or expired."
                    else:
                        raise AssertionError("A recovery SMS code must be single-use.")
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_phone_recovery_expiry_and_attempt_limit():
    async def run_flow():
        engine, session_factory = await _create_database()
        try:
            with patch.object(settings, "twilio_account_sid", "AC-test-account"), \
                 patch.object(settings, "twilio_auth_token", "test-auth-token"), \
                 patch.object(settings, "twilio_from_number", "+14155550999"), \
                 patch.object(settings, "phone_recovery_hmac_key", HMAC_KEY), \
                 patch("app.routers.auth.sms.send_recovery_code", new_callable=AsyncMock) as send_sms:
                async with session_factory() as session:
                    user = models.User(
                        name="Recovery User",
                        email="recovery@example.com",
                        phone_number=PHONE_NUMBER,
                        password_hash="not-used",
                    )
                    session.add(user)
                    await session.flush()
                    session.add(models.TotpCredential(
                        user_id=user.id,
                        encrypted_secret=encrypt_totp_secret(generate_totp_secret()),
                        enabled=True,
                    ))
                    await session.commit()

                    await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                        session,
                    )
                    _, sms_code = send_sms.await_args.args
                    challenge = await session.scalar(
                        select(models.PhoneRecoveryChallenge)
                    )
                    challenge.expires_at = datetime.utcnow() - timedelta(seconds=1)
                    await session.commit()
                    try:
                        await auth.confirm_phone_recovery(
                            PhoneRecoveryConfirm(
                                phone_number=PHONE_NUMBER,
                                otp_code=sms_code,
                            ),
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 400
                    else:
                        raise AssertionError("An expired recovery code must be rejected.")

                    await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                        session,
                    )
                    _, sms_code = send_sms.await_args.args
                    for _ in range(auth.PHONE_RECOVERY_MAX_ATTEMPTS):
                        try:
                            await auth.confirm_phone_recovery(
                                PhoneRecoveryConfirm(
                                    phone_number=PHONE_NUMBER,
                                    otp_code="000000" if sms_code != "000000" else "000001",
                                ),
                                session,
                            )
                        except HTTPException as error:
                            assert error.status_code == 400
                        else:
                            raise AssertionError("An incorrect recovery code must be rejected.")
                    challenge = await session.scalar(
                        select(models.PhoneRecoveryChallenge)
                        .where(models.PhoneRecoveryChallenge.code_hash.is_not(None))
                        .order_by(models.PhoneRecoveryChallenge.created_at.desc())
                    )
                    assert challenge.attempt_count == auth.PHONE_RECOVERY_MAX_ATTEMPTS
                    try:
                        await auth.confirm_phone_recovery(
                            PhoneRecoveryConfirm(
                                phone_number=PHONE_NUMBER,
                                otp_code=sms_code,
                            ),
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 400
                    else:
                        raise AssertionError("Codes must lock after the attempt limit.")
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_phone_recovery_hides_unknown_numbers_and_rate_limits_requests():
    async def run_flow():
        engine, session_factory = await _create_database()
        try:
            with patch.object(settings, "twilio_account_sid", "AC-test-account"), \
                 patch.object(settings, "twilio_auth_token", "test-auth-token"), \
                 patch.object(settings, "twilio_from_number", "+14155550999"), \
                 patch.object(settings, "phone_recovery_hmac_key", HMAC_KEY), \
                 patch("app.routers.auth.sms.send_recovery_code", new_callable=AsyncMock) as send_sms:
                async with session_factory() as session:
                    user = models.User(
                        name="Recovery User",
                        email="recovery@example.com",
                        phone_number=PHONE_NUMBER,
                        password_hash="not-used",
                    )
                    session.add(user)
                    await session.flush()
                    session.add(models.TotpCredential(
                        user_id=user.id,
                        encrypted_secret=encrypt_totp_secret(generate_totp_secret()),
                        enabled=True,
                    ))
                    await session.commit()

                    known = await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                        session,
                    )
                    unknown = await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number="+14155550124"),
                        session,
                    )
                    assert known == unknown
                    send_sms.assert_awaited_once()

                    for _ in range(
                        auth.PHONE_RECOVERY_MAX_PHONE_REQUESTS - 1
                    ):
                        await auth.request_phone_recovery(
                            _request(),
                            PhoneRecoveryRequest(phone_number="+14155550124"),
                            session,
                        )
                    try:
                        await auth.request_phone_recovery(
                            _request(),
                            PhoneRecoveryRequest(phone_number="+14155550124"),
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 429
                    else:
                        raise AssertionError("Recovery SMS requests must be rate-limited.")
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_phone_recovery_is_unavailable_without_twilio_and_does_not_fake_send():
    async def run_flow():
        engine, session_factory = await _create_database()
        try:
            with patch.object(settings, "twilio_account_sid", ""), \
                 patch.object(settings, "twilio_auth_token", ""), \
                 patch.object(settings, "twilio_from_number", ""), \
                 patch.object(settings, "phone_recovery_hmac_key", HMAC_KEY), \
                 patch("app.routers.auth.sms.send_recovery_code", new_callable=AsyncMock) as send_sms:
                async with session_factory() as session:
                    try:
                        await auth.request_phone_recovery(
                            _request(),
                            PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 503
                        assert "Twilio SMS is not configured" in error.detail
                    else:
                        raise AssertionError("Recovery must be unavailable without Twilio.")
                    send_sms.assert_not_awaited()
                    challenge_count = await session.scalar(
                        select(models.PhoneRecoveryChallenge.id)
                    )
                    assert challenge_count is None
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_phone_recovery_sms_delivery_failure_does_not_reveal_account():
    async def run_flow():
        engine, session_factory = await _create_database()
        try:
            with patch.object(settings, "twilio_account_sid", "AC-test-account"), \
                 patch.object(settings, "twilio_auth_token", "test-auth-token"), \
                 patch.object(settings, "twilio_from_number", "+14155550999"), \
                 patch.object(settings, "phone_recovery_hmac_key", HMAC_KEY), \
                 patch(
                     "app.routers.auth.sms.send_recovery_code",
                     new_callable=AsyncMock,
                     side_effect=SMSProviderUnavailable(),
                 ):
                async with session_factory() as session:
                    user = models.User(
                        name="Recovery User",
                        email="recovery@example.com",
                        phone_number=PHONE_NUMBER,
                        password_hash="not-used",
                    )
                    session.add(user)
                    await session.flush()
                    session.add(models.TotpCredential(
                        user_id=user.id,
                        encrypted_secret=encrypt_totp_secret(generate_totp_secret()),
                        enabled=True,
                    ))
                    await session.commit()

                    known = await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                        session,
                    )
                    unknown = await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number="+14155550124"),
                        session,
                    )
                    assert known == unknown
                    challenge = await session.scalar(
                        select(models.PhoneRecoveryChallenge)
                        .where(models.PhoneRecoveryChallenge.phone_hash
                               == auth._phone_recovery_hash(PHONE_NUMBER, "phone"))
                    )
                    assert challenge.code_hash is None
                    assert challenge.sent_at is None
                    assert challenge.consumed_at is not None
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_recovery_cannot_reset_authenticator_after_account_phone_changes():
    async def run_flow():
        engine, session_factory = await _create_database()
        try:
            with patch.object(settings, "twilio_account_sid", "AC-test-account"), \
                 patch.object(settings, "twilio_auth_token", "test-auth-token"), \
                 patch.object(settings, "twilio_from_number", "+14155550999"), \
                 patch.object(settings, "phone_recovery_hmac_key", HMAC_KEY), \
                 patch("app.routers.auth.sms.send_recovery_code", new_callable=AsyncMock) as send_sms:
                async with session_factory() as session:
                    old_secret = generate_totp_secret()
                    user = models.User(
                        name="Recovery User",
                        email="recovery@example.com",
                        phone_number=PHONE_NUMBER,
                        password_hash="not-used",
                    )
                    session.add(user)
                    await session.flush()
                    credential = models.TotpCredential(
                        user_id=user.id,
                        encrypted_secret=encrypt_totp_secret(old_secret),
                        enabled=True,
                    )
                    session.add(credential)
                    await session.commit()

                    await auth.request_phone_recovery(
                        _request(),
                        PhoneRecoveryRequest(phone_number=PHONE_NUMBER),
                        session,
                    )
                    _, sms_code = send_sms.await_args.args
                    user.phone_number = "+14155550124"
                    await session.commit()
                    try:
                        await auth.confirm_phone_recovery(
                            PhoneRecoveryConfirm(
                                phone_number=PHONE_NUMBER,
                                otp_code=sms_code,
                            ),
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 400
                    else:
                        raise AssertionError(
                            "A recovery SMS must not reset an account with a changed phone."
                        )
                    assert decrypt_totp_secret(credential.encrypted_secret) == old_secret
                    assert credential.enabled is True
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_twilio_delivery_uses_environment_configured_credentials():
    async def run_flow():
        response = Mock()
        response.raise_for_status = Mock()
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post.return_value = response
        with patch.object(settings, "twilio_account_sid", "AC-environment-account"), \
             patch.object(settings, "twilio_auth_token", "environment-auth-token"), \
             patch.object(settings, "twilio_from_number", "+14155550999"), \
             patch("app.sms.httpx.AsyncClient", return_value=client):
            await send_recovery_code(PHONE_NUMBER, "083917")

        client.post.assert_awaited_once()
        url, = client.post.await_args.args
        kwargs = client.post.await_args.kwargs
        assert "AC-environment-account" in url
        assert kwargs["auth"] == ("AC-environment-account", "environment-auth-token")
        assert kwargs["data"]["From"] == "+14155550999"
        assert kwargs["data"]["To"] == PHONE_NUMBER
        assert "083917" in kwargs["data"]["Body"]

    asyncio.run(run_flow())
