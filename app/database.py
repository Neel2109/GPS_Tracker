from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import inspect, text
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    echo=False,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


def _migrate_legacy_users(sync_connection):
    inspector = inspect(sync_connection)
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    migrations = {
        "phone_number": "ALTER TABLE users ADD COLUMN phone_number VARCHAR(16)",
        "phone_verified_at": "ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP",
        "role": "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'USER'",
        "account_status": "ALTER TABLE users ADD COLUMN account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'",
        "last_login_at": "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP",
    }
    for column, statement in migrations.items():
        if column not in existing_columns:
            sync_connection.execute(text(statement))

    sync_connection.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_number ON users (phone_number)")
    )

    if "alerts" in inspector.get_table_names():
        alert_columns = {
            column["name"] for column in inspect(sync_connection).get_columns("alerts")
        }
        alert_migrations = {
            "status": "ALTER TABLE alerts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'OPEN'",
            "acknowledged_at": "ALTER TABLE alerts ADD COLUMN acknowledged_at TIMESTAMP",
            "resolved_at": "ALTER TABLE alerts ADD COLUMN resolved_at TIMESTAMP",
        }
        for column, statement in alert_migrations.items():
            if column not in alert_columns:
                sync_connection.execute(text(statement))
        if "read" in alert_columns:
            sync_connection.execute(text(
                "UPDATE alerts SET status = 'ACKNOWLEDGED' "
                "WHERE read = TRUE AND status = 'OPEN'"
            ))
        sync_connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts (status)")
        )

    if "admin_location_access_requests" in inspector.get_table_names():
        access_columns = {
            column["name"]
            for column in inspect(sync_connection).get_columns("admin_location_access_requests")
        }
        if "target_device_id" not in access_columns:
            sync_connection.execute(
                text("ALTER TABLE admin_location_access_requests ADD COLUMN target_device_id VARCHAR")
            )
            access_columns.add("target_device_id")
        sync_connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_admin_location_access_requests_target_device_id "
                "ON admin_location_access_requests (target_device_id)"
            )
        )
        if {"scope", "status", "decided_at", "target_device_id"} <= access_columns:
            sync_connection.execute(
                text(
                    "UPDATE admin_location_access_requests "
                    "SET status = 'REVOKED', decided_at = CURRENT_TIMESTAMP "
                    "WHERE scope = 'DEVICE_CONTROL' AND target_device_id IS NULL "
                    "AND status IN ('PENDING', 'APPROVED')"
                )
            )

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_legacy_users)

async def get_db():
    async with SessionLocal() as session:
        yield session
