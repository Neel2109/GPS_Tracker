import asyncio
import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app import models, security
from app.config import settings
from app.database import Base, _migrate_legacy_users
from app.routers import access_requests, admin, auth, locations
from app.totp import encrypt_totp_secret, generate_totp_secret
from app.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminDeviceCommand,
    LocationAccessRequestCreate,
    LocationAccessRequestDecision,
    PhoneInvitationClaim,
    PhoneTotpActivation,
    PhoneTotpLogin,
    PhoneVerificationConfirm,
    PhoneVerificationRequest,
)


def _request(path: str = "/api/admin/test") -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.88", 12345),
        "server": ("test", 80),
    })


def _code_at(secret: str, timestamp: float) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int(timestamp // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def test_existing_users_table_gets_role_phone_and_status_columns():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, "
            "email VARCHAR NOT NULL, password_hash VARCHAR NOT NULL, created_at TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, name, email, password_hash) "
            "VALUES ('existing', 'Existing', 'existing@example.com', 'hash')"
        ))
        connection.execute(text(
            "CREATE TABLE admin_location_access_requests ("
            "id VARCHAR PRIMARY KEY, target_user_id VARCHAR, scope VARCHAR, status VARCHAR, decided_at TIMESTAMP)"
        ))
        connection.execute(text(
            "CREATE TABLE alerts ("
            "id VARCHAR PRIMARY KEY, user_id VARCHAR, device_id VARCHAR, type VARCHAR, "
            "title VARCHAR, message VARCHAR, read BOOLEAN NOT NULL DEFAULT 0, created_at TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO alerts (id, read) VALUES ('legacy-read-alert', 1)"
        ))
        connection.execute(text(
            "INSERT INTO admin_location_access_requests (id, scope, status) "
            "VALUES ('legacy-control', 'DEVICE_CONTROL', 'APPROVED')"
        ))

        _migrate_legacy_users(connection)

        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        assert {
            "phone_number",
            "phone_verified_at",
            "role",
            "account_status",
            "last_login_at",
        } <= columns
        row = connection.execute(
            text("SELECT phone_number, role, account_status FROM users WHERE id='existing'")
        ).one()
        assert row == (None, "USER", "ACTIVE")
        indexes = {index["name"] for index in inspect(connection).get_indexes("users")}
        assert "uq_users_phone_number" in indexes
        access_columns = {
            column["name"]
            for column in inspect(connection).get_columns("admin_location_access_requests")
        }
        assert "target_device_id" in access_columns
        access_indexes = {
            index["name"]
            for index in inspect(connection).get_indexes("admin_location_access_requests")
        }
        assert "ix_admin_location_access_requests_target_device_id" in access_indexes
        legacy_grant = connection.execute(
            text("SELECT status, decided_at FROM admin_location_access_requests WHERE id='legacy-control'")
        ).one()
        assert legacy_grant.status == "REVOKED"
        assert legacy_grant.decided_at is not None
        alert_columns = {column["name"] for column in inspect(connection).get_columns("alerts")}
        assert {"status", "acknowledged_at", "resolved_at"} <= alert_columns
        assert connection.execute(
            text("SELECT status FROM alerts WHERE id='legacy-read-alert'")
        ).scalar_one() == "ACKNOWLEDGED"
    engine.dispose()


def test_phone_verification_is_rate_limited_single_use_and_required_for_activation():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            phone_number = "+14155550123"
            secret = generate_totp_secret()
            user = models.User(
                name="Verified Owner",
                email="verified-owner@example.com",
                phone_number=phone_number,
                password_hash="test",
            )
            session.add(user)
            await session.flush()
            session.add(models.TotpCredential(
                user_id=user.id,
                encrypted_secret=encrypt_totp_secret(secret),
                enabled=False,
            ))
            await session.commit()

            with (
                patch.object(settings, "phone_recovery_hmac_key", "test-key-with-more-than-32-characters"),
                patch("app.routers.auth._require_phone_verification_available"),
                patch("app.routers.auth.sms.send_phone_verification_code", new_callable=AsyncMock) as send_sms,
            ):
                requested = await auth.request_phone_verification(
                    _request("/api/auth/phone/verification/request"),
                    PhoneVerificationRequest(phone_number=phone_number),
                    session,
                )
                assert "does not confirm account existence" in requested.message
                assert send_sms.await_count == 1
                sms_code = send_sms.await_args.args[1]

                try:
                    await auth.activate_phone_account(
                        _request("/api/auth/phone/activate"),
                        PhoneTotpActivation(
                            phone_number=phone_number,
                            otp_code=_code_at(secret, time.time()),
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 401
                else:
                    raise AssertionError("An unverified phone must not activate an account.")

                confirmed = await auth.confirm_phone_verification(
                    PhoneVerificationConfirm(phone_number=phone_number, otp_code=sms_code),
                    session,
                )
                assert confirmed.message == "Phone number verified."
                assert user.phone_verified_at is not None

                try:
                    await auth.confirm_phone_verification(
                        PhoneVerificationConfirm(phone_number=phone_number, otp_code=sms_code),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 400
                else:
                    raise AssertionError("A phone-verification code must be single-use.")

                activated = await auth.activate_phone_account(
                    _request("/api/auth/phone/activate"),
                    PhoneTotpActivation(
                        phone_number=phone_number,
                        otp_code=_code_at(secret, (int(time.time() // 30) + 1) * 30),
                    ),
                    session,
                )
                assert activated["user"].id == user.id
        await engine.dispose()

    asyncio.run(run_flow())


def test_phone_totp_activation_admin_management_and_owner_location_scope():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                super_admin = models.User(
                    name="Platform Owner",
                    email="root@example.com",
                    phone_number="+14155550001",
                    role="SUPER_ADMIN",
                    password_hash="hash",
                )
                session.add(super_admin)
                await session.flush()

                provisioned = await admin.create_admin_user(
                    AdminUserCreate(
                        name="Device Owner",
                        phone_number="+14155550123",
                        role="USER",
                    ),
                    _request(),
                    super_admin,
                    session,
                )
                assert provisioned.phone_number == "+14155550123"
                provisioned_user = await session.get(models.User, provisioned.id)
                assert provisioned_user is not None
                try:
                    await auth.claim_account_invitation(
                        PhoneInvitationClaim(
                            phone_number=provisioned.phone_number,
                            invitation_token=provisioned.invitation_token,
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 403
                else:
                    raise AssertionError("An invitation must require verified phone ownership.")
                provisioned_user.phone_verified_at = datetime.utcnow()
                await session.commit()
                assert provisioned.invitation_token
                reissued = await admin.create_user_invitation(
                    provisioned.id,
                    _request(),
                    super_admin,
                    session,
                )
                try:
                    await auth.claim_account_invitation(
                        PhoneInvitationClaim(
                            phone_number=provisioned.phone_number,
                            invitation_token=provisioned.invitation_token,
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 400
                else:
                    raise AssertionError("Reissuing an invitation must revoke the previous token.")
                setup = await auth.claim_account_invitation(
                    PhoneInvitationClaim(
                        phone_number=provisioned.phone_number,
                        invitation_token=reissued.invitation_token,
                    ),
                    session,
                )
                try:
                    await auth.claim_account_invitation(
                        PhoneInvitationClaim(
                            phone_number=provisioned.phone_number,
                            invitation_token=reissued.invitation_token,
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 400
                else:
                    raise AssertionError("An account invitation must be single-use.")
                activated = await auth.activate_phone_account(
                    _request("/api/auth/phone/activate"),
                    PhoneTotpActivation(
                        phone_number=provisioned.phone_number,
                        otp_code=_code_at(setup.secret, time.time()),
                    ),
                    session,
                )
                owner = await security.get_current_user(
                    HTTPAuthorizationCredentials(
                        scheme="Bearer",
                        credentials=activated["access_token"],
                    ),
                    session,
                )
                assert owner.phone_number == provisioned.phone_number
                assert owner.role == "USER"
                assert await session.scalar(
                    select(models.AuthSession).where(models.AuthSession.user_id == owner.id)
                ) is not None

                try:
                    await admin.create_admin_user(
                        AdminUserCreate(
                            name="Unauthorized Admin",
                            phone_number="+14155550124",
                            role="ADMIN",
                        ),
                        _request(),
                        owner,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 403
                else:
                    raise AssertionError("A regular user must not provision an administrator.")

                next_counter = int(time.time() // 30) + 1
                signed_in = await auth.login_with_phone(
                    _request("/api/auth/phone/login"),
                    PhoneTotpLogin(
                        phone_number=provisioned.phone_number,
                        otp_code=_code_at(setup.secret, next_counter * 30),
                    ),
                    session,
                )
                assert signed_in["user"].id == owner.id
                try:
                    await auth.login_with_phone(
                        _request("/api/auth/phone/login"),
                        PhoneTotpLogin(
                            phone_number=provisioned.phone_number,
                            otp_code=_code_at(setup.secret, next_counter * 30),
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 401
                else:
                    raise AssertionError("A phone sign-in authenticator code must be single-use.")

                signed_in_user = await security.get_current_user(
                    HTTPAuthorizationCredentials(
                        scheme="Bearer",
                        credentials=signed_in["access_token"],
                    ),
                    session,
                )
                await auth.logout(signed_in_user, session)
                try:
                    await security.get_current_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer",
                            credentials=signed_in["access_token"],
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 401
                else:
                    raise AssertionError("Signing out must revoke the active login session.")

                try:
                    await security.get_admin_user(owner)
                except HTTPException as error:
                    assert error.status_code == 403
                else:
                    raise AssertionError("A USER must not access admin routes.")

                phone = models.Device(
                    id="owner-phone",
                    user_id=owner.id,
                    name="Owner phone",
                    device_type="android",
                    last_latitude=23.0225,
                    last_longitude=72.5714,
                )
                second_phone = models.Device(
                    id="owner-second-phone",
                    user_id=owner.id,
                    name="Owner second phone",
                    device_type="android",
                )
                owner_location = models.Location(
                    device_id="owner-phone",
                    latitude=23.0225,
                    longitude=72.5714,
                    timestamp=datetime.utcnow(),
                )
                other_user = models.User(
                    name="Other owner",
                    email="other@example.com",
                    password_hash="hash",
                )
                session.add_all([phone, second_phone, owner_location, other_user])
                await session.flush()
                other_device = models.Device(
                    id="other-device",
                    user_id=other_user.id,
                    name="Other phone",
                    device_type="android",
                )
                location = models.Location(
                    device_id=other_device.id,
                    latitude=10,
                    longitude=20,
                    timestamp=datetime.utcnow(),
                )
                session.add_all([other_device, location])
                await session.commit()

                own_location_result = await locations.get_current_location(phone.id, owner, session)
                assert own_location_result is not None
                assert own_location_result.latitude == 23.0225
                try:
                    await locations.get_current_location(other_device.id, owner, session)
                except HTTPException as error:
                    assert error.status_code == 404
                else:
                    raise AssertionError("Users must not view another account's device location.")

                device_inventory = await admin.list_admin_devices(_request(), super_admin, session)
                other_device_row = next(item for item in device_inventory if item.id == other_device.id)
                assert other_device_row.owner_phone_number is None
                assert "last_latitude" not in other_device_row.model_dump()
                assert "last_longitude" not in other_device_row.model_dump()

                request_response = await admin.create_location_access_request(
                    LocationAccessRequestCreate(
                        target_user_id=owner.id,
                        reason="Investigate the reported missing device.",
                        duration_minutes=15,
                    ),
                    _request(),
                    super_admin,
                    session,
                )
                assert request_response.status == "PENDING"
                try:
                    await admin.list_granted_device_locations(
                        request_response.id,
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 403
                else:
                    raise AssertionError("Pending requests must not expose device locations.")

                incoming = await access_requests.list_incoming_access_requests(owner, session)
                assert len(incoming) == 1
                assert incoming[0].reason == "Investigate the reported missing device."
                approved = await access_requests.decide_access_request(
                    request_response.id,
                    LocationAccessRequestDecision(action="APPROVE"),
                    owner,
                    session,
                )
                assert approved.status == "APPROVED"
                assert approved.expires_at is not None

                granted_locations = await admin.list_granted_device_locations(
                    request_response.id,
                    _request(),
                    super_admin,
                    session,
                )
                owner_grant = next(item for item in granted_locations if item.id == phone.id)
                assert owner_grant.last_latitude == 23.0225
                assert owner_grant.owner_name == owner.name
                assert owner_grant.owner_role == "USER"
                granted_history = await admin.list_granted_location_history(
                    request_response.id,
                    phone.id,
                    _request(),
                    "7days",
                    500,
                    super_admin,
                    session,
                )
                assert len(granted_history) == 1
                assert granted_history[0].latitude == 23.0225

                try:
                    await admin.create_location_access_request(
                        LocationAccessRequestCreate(
                            target_user_id=owner.id,
                            scope="DEVICE_CONTROL",
                            target_device_id=other_device.id,
                            reason="Try to select another account's device.",
                            duration_minutes=15,
                        ),
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 404
                else:
                    raise AssertionError("A control request must target a device owned by the selected account.")

                try:
                    await admin.send_approved_device_command(
                        request_response.id,
                        phone.id,
                        AdminDeviceCommand(command="ENABLE_LOST_MODE", confirmation=phone.name),
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 404
                else:
                    raise AssertionError("A location-only grant must not authorize device commands.")

                from app.services.admin_live import queue_authorized_admin_location_updates
                from app.websocket_manager import manager

                old_admin_connections = manager.dashboard_connections.get(super_admin.id)
                manager.dashboard_connections[super_admin.id] = {object()}
                try:
                    queued_updates = await queue_authorized_admin_location_updates(
                        session,
                        phone,
                        {"latitude": 23.0225, "longitude": 72.5714},
                    )
                    assert len(queued_updates) == 1
                    assert queued_updates[0][1]["access_request_id"] == request_response.id
                    assert queued_updates[0][1]["type"] == "ADMIN_LIVE_LOCATION_UPDATE"
                finally:
                    if old_admin_connections is None:
                        manager.dashboard_connections.pop(super_admin.id, None)
                    else:
                        manager.dashboard_connections[super_admin.id] = old_admin_connections

                revoked = await access_requests.decide_access_request(
                    request_response.id,
                    LocationAccessRequestDecision(action="REVOKE"),
                    owner,
                    session,
                )
                assert revoked.status == "REVOKED"
                try:
                    await admin.list_granted_device_locations(
                        request_response.id,
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 403
                else:
                    raise AssertionError("Revoked grants must no longer provide location access.")

                control_request = await admin.create_location_access_request(
                    LocationAccessRequestCreate(
                        target_user_id=owner.id,
                        scope="DEVICE_CONTROL",
                        target_device_id=phone.id,
                        reason="Assist with recovering the owner's reported phone.",
                        duration_minutes=15,
                    ),
                    _request(),
                    super_admin,
                    session,
                )
                assert control_request.scope == "DEVICE_CONTROL"
                assert control_request.target_device_id == phone.id
                owner_requests = await access_requests.list_incoming_access_requests(owner, session)
                owner_control_request = next(row for row in owner_requests if row.id == control_request.id)
                assert owner_control_request.target_device_name == phone.name
                assert owner_control_request.target_device_type == "android"
                control_approved = await access_requests.decide_access_request(
                    control_request.id,
                    LocationAccessRequestDecision(action="APPROVE"),
                    owner,
                    session,
                )
                assert control_approved.status == "APPROVED"
                try:
                    await admin.list_granted_device_locations(
                        control_request.id,
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 404
                else:
                    raise AssertionError("A device-control grant must not authorize location reads.")

                previous_device_socket = manager.device_connections.get(phone.id)
                manager.device_connections[phone.id] = object()
                try:
                    try:
                        await admin.send_approved_device_command(
                            control_request.id,
                            second_phone.id,
                            AdminDeviceCommand(
                                command="ENABLE_LOST_MODE",
                                confirmation=second_phone.name,
                            ),
                            _request(),
                            super_admin,
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 403
                    else:
                        raise AssertionError("Device-control grants must not authorize a different device.")

                    send_command = AsyncMock(return_value=True)
                    with patch.object(manager, "send_to_device", send_command):
                        controlled = await admin.send_approved_device_command(
                            control_request.id,
                            phone.id,
                            AdminDeviceCommand(command="ENABLE_LOST_MODE", confirmation=phone.name),
                            _request(),
                            super_admin,
                            session,
                        )
                    assert controlled.command == "ENABLE_LOST_MODE"
                    assert controlled.user_id == super_admin.id
                    assert phone.is_lost_mode is True
                    send_command.assert_awaited_once()

                    try:
                        await admin.send_approved_device_command(
                            control_request.id,
                            phone.id,
                            AdminDeviceCommand(command="ENABLE_LOST_MODE", confirmation="wrong name"),
                            _request(),
                            super_admin,
                            session,
                        )
                    except HTTPException as error:
                        assert error.status_code == 422
                    else:
                        raise AssertionError("Device commands must require exact device-name confirmation.")
                finally:
                    if previous_device_socket is None:
                        manager.device_connections.pop(phone.id, None)
                    else:
                        manager.device_connections[phone.id] = previous_device_socket

                try:
                    await admin.create_location_access_request(
                        LocationAccessRequestCreate(
                            target_user_id=owner.id,
                            scope="DEVICE_CONTROL",
                            target_device_id=phone.id,
                            reason="Request an invalid long device-control grant.",
                            duration_minutes=60,
                        ),
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 422
                else:
                    raise AssertionError("Device-control grants must be limited to 15 minutes.")

                try:
                    await admin.create_location_access_request(
                        LocationAccessRequestCreate(
                            target_user_id=owner.id,
                            scope="DEVICE_CONTROL",
                            reason="Request a control grant without selecting a device.",
                            duration_minutes=15,
                        ),
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 422
                else:
                    raise AssertionError("Device-control requests must specify a target device.")

                try:
                    await admin.update_admin_user(
                        super_admin.id,
                        AdminUserUpdate(role="ADMIN"),
                        _request(),
                        super_admin,
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 409
                else:
                    raise AssertionError("The last active super-administrator must not be demoted.")

                owner = await security.get_current_user(
                    HTTPAuthorizationCredentials(
                        scheme="Bearer",
                        credentials=activated["access_token"],
                    ),
                    session,
                )
                listed_sessions = await admin.list_user_sessions(
                    owner.id,
                    _request("/api/admin/users/sessions"),
                    super_admin,
                    session,
                )
                assert any(item.id == owner._trackguard_session_id for item in listed_sessions)
                revoked_session = await admin.revoke_user_session(
                    owner.id,
                    owner._trackguard_session_id,
                    _request("/api/admin/users/sessions/revoke"),
                    super_admin,
                    session,
                )
                assert revoked_session.revoked_at is not None
                try:
                    await security.get_current_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer",
                            credentials=activated["access_token"],
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 401
                else:
                    raise AssertionError("Administrator session revocation must invalidate its access token.")

                updated = await admin.update_admin_user(
                    owner.id,
                    AdminUserUpdate(account_status="SUSPENDED"),
                    _request(),
                    super_admin,
                    session,
                )
                assert updated.account_status == "SUSPENDED"
                try:
                    await security.get_current_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer",
                            credentials=signed_in["access_token"],
                        ),
                        session,
                    )
                except HTTPException as error:
                    assert error.status_code == 403
                else:
                    raise AssertionError("Suspended accounts must lose access immediately.")

                audit_actions = set((await session.scalars(
                    select(models.AdminAuditEvent.action)
                )).all())
                assert "ADMIN_LOCATION_ACCESS_REQUESTED" in audit_actions
                assert "OWNER_APPROVE_ADMIN_LOCATION_ACCESS" in audit_actions
                assert "OWNER_APPROVE_ADMIN_DEVICE_CONTROL" in audit_actions
                assert "ADMIN_GRANTED_LOCATION_VIEWED" in audit_actions
                assert "ADMIN_GRANTED_LOCATION_HISTORY_VIEWED" in audit_actions
                assert "OWNER_REVOKE_ADMIN_LOCATION_ACCESS" in audit_actions
                assert "ADMIN_DEVICE_CONTROL_REQUESTED" in audit_actions
                assert "ADMIN_DEVICE_COMMAND_REQUESTED" in audit_actions
                control_approval_event = await session.scalar(
                    select(models.AdminAuditEvent).where(
                        models.AdminAuditEvent.action == "OWNER_APPROVE_ADMIN_DEVICE_CONTROL"
                    )
                )
                assert control_approval_event is not None
                assert control_approval_event.target_device_id == phone.id
        finally:
            await engine.dispose()

    asyncio.run(run_flow())


def test_phone_normalization_requires_international_number():
    from app.phone import normalize_phone_number

    assert normalize_phone_number("+1 (415) 555-0123") == "+14155550123"
    try:
        normalize_phone_number("4155550123")
    except ValueError as error:
        assert "E.164" in str(error)
    else:
        raise AssertionError("A phone number without country code must be rejected.")


def test_configured_owner_phone_bootstraps_super_admin_role_on_phone_login():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        old_owner_phone = settings.local_user_phone
        old_super_admin_phone = settings.super_admin_phone
        old_owner_email = settings.local_user_email
        settings.local_user_phone = "+14155550999"
        settings.super_admin_phone = "+14155550999"
        settings.local_user_email = "owner@example.com"
        secret = generate_totp_secret()
        try:
            async with session_factory() as session:
                owner = models.User(
                    name="Configured Owner",
                    email="owner@example.com",
                    phone_number=None,
                    phone_verified_at=datetime.utcnow(),
                    role="USER",
                    password_hash="hash",
                )
                session.add(owner)
                await session.flush()
                session.add(models.TotpCredential(
                    user_id=owner.id,
                    encrypted_secret=encrypt_totp_secret(secret),
                    enabled=True,
                ))
                await session.commit()

                result = await auth.login_with_phone(
                    _request("/api/auth/phone/login"),
                    PhoneTotpLogin(
                        phone_number=settings.local_user_phone,
                        otp_code=_code_at(secret, time.time()),
                    ),
                    session,
                )
                assert result["user"].role == "SUPER_ADMIN"
                assert result["user"].account_status == "ACTIVE"
        finally:
            settings.local_user_phone = old_owner_phone
            settings.super_admin_phone = old_super_admin_phone
            settings.local_user_email = old_owner_email
            await engine.dispose()

    asyncio.run(run_flow())
