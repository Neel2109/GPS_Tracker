import asyncio
import base64
import hashlib
import hmac
import struct
import time

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app import security
from app.config import settings
from app.database import Base
from app.routers import auth
from app.schemas import LocalPinTotpConfirm, LocalPinUnlock, Token, TokenRefresh
from app.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    matching_totp_counter,
    provisioning_uri,
    verify_totp,
)


def _code_at(secret: str, timestamp: float) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int(timestamp // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _current_code(secret: str) -> str:
    return _code_at(secret, time.time())


def test_totp_rfc_vector_and_encrypted_secret_round_trip():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert verify_totp(secret, "287082", timestamp=59)
    assert not verify_totp(secret, "not-a-code", timestamp=59)

    generated = generate_totp_secret()
    assert matching_totp_counter(generated, _current_code(generated)) is not None
    encrypted = encrypt_totp_secret(generated)
    assert generated not in encrypted
    assert decrypt_totp_secret(encrypted) == generated
    assert provisioning_uri(generated, "owner@example.com").startswith(
        "otpauth://totp/TrackGuard%3Aowner%40example.com?"
    )


def test_pin_login_uses_only_configured_pin_and_rejects_old_tokens():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        old_pin = settings.local_pin
        client_ip = "127.0.0.91"
        auth._failed_pin_attempts.pop(client_ip, None)
        settings.local_pin = "123456"
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/api/auth/unlock",
            "headers": [],
            "client": (client_ip, 12345),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        })
        try:
            async with session_factory() as session:
                try:
                    await auth.unlock_with_pin(request, LocalPinUnlock(pin="000000"), session)
                except HTTPException as error:
                    assert error.status_code == 401
                    assert "LOCAL_PIN" in error.detail
                    assert "phone's unlock PIN" in error.detail
                else:
                    raise AssertionError("An incorrect PIN must be rejected.")

                signed_in = await auth.unlock_with_pin(
                    request,
                    LocalPinUnlock(pin="123456"),
                    session,
                )
                assert signed_in["access_token"]
                assert signed_in["refresh_token"]
                Token.model_validate(signed_in)

                user = await security.get_current_user(
                    HTTPAuthorizationCredentials(
                        scheme="Bearer",
                        credentials=signed_in["access_token"],
                    ),
                    session,
                )
                assert user.email == settings.local_user_email

                refreshed = await auth.refresh_token(
                    TokenRefresh(refresh_token=signed_in["refresh_token"]),
                    session,
                )
                Token.model_validate(refreshed)

                repeat_login = await auth.unlock_with_pin(
                    request,
                    LocalPinUnlock(pin="123456"),
                    session,
                )
                assert repeat_login["access_token"]

                legacy_checks = (
                    security.get_current_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer",
                            credentials=security.create_access_token({"sub": user.id}),
                        ),
                        session,
                    ),
                    auth.refresh_token(
                        TokenRefresh(refresh_token=security.create_refresh_token({"sub": user.id})),
                        session,
                    ),
                )
                for check in legacy_checks:
                    try:
                        await check
                    except HTTPException as error:
                        assert error.status_code == 401
                    else:
                        raise AssertionError("Tokens created without MFA must be rejected.")
        finally:
            settings.local_pin = old_pin
            auth._failed_pin_attempts.pop(client_ip, None)
            await engine.dispose()

    asyncio.run(run_flow())
