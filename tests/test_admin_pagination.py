import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app import models
from app.database import Base
from app.routers import admin


def _request(path: str) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.90", 12345),
        "server": ("test", 80),
    })


def test_admin_pages_apply_search_sort_limits_and_owner_filter():
    async def run_flow():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                actor = models.User(
                    name="Admin",
                    email="admin@example.com",
                    password_hash="hash",
                    role="SUPER_ADMIN",
                )
                north = models.User(
                    name="Alice North",
                    email="north@example.com",
                    password_hash="hash",
                )
                south = models.User(
                    name="Alice South",
                    email="south@example.com",
                    password_hash="hash",
                )
                session.add_all((actor, north, south))
                await session.flush()
                session.add_all((
                    models.Device(id="north-device", user_id=north.id, name="North phone"),
                    models.Device(id="south-device", user_id=south.id, name="South phone"),
                ))
                session.add_all((
                    models.AdminAuditEvent(
                        actor_user_id=actor.id,
                        action="ADMIN_NOTE",
                        details="needle event",
                    ),
                    models.AdminAuditEvent(
                        actor_user_id=actor.id,
                        action="ADMIN_NOTE",
                        details="other event",
                    ),
                ))
                await session.flush()

                users = await admin.list_admin_users_page(
                    _request("/api/admin/users/page"),
                    0,
                    1,
                    "Alice",
                    "USER",
                    "ALL",
                    "name",
                    "asc",
                    actor,
                    session,
                )
                assert users.total == 2
                assert len(users.items) == 1
                assert users.items[0].name == "Alice North"

                devices = await admin.list_admin_devices_page(
                    _request("/api/admin/devices/page"),
                    0,
                    25,
                    "",
                    north.id,
                    "ALL",
                    "ALL",
                    "ALL",
                    "name",
                    "asc",
                    actor,
                    session,
                )
                assert devices.total == 1
                assert devices.items[0].id == "north-device"

                audit = await admin.list_admin_audit_page(
                    _request("/api/admin/audit/page"),
                    0,
                    25,
                    "needle",
                    "ALL",
                    "desc",
                    actor,
                    session,
                )
                assert audit.total == 1
                assert audit.items[0].details == "needle event"
        finally:
            await engine.dispose()

    asyncio.run(run_flow())
