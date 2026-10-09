import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())


def resolve_device_status(
    *,
    status=None,
    last_seen=None,
    last_online=None,
    last_offline=None,
    offline_since=None,
    last_location_time=None,
    last_latitude=None,
    last_longitude=None,
    connection_state=None,
):
    if connection_state in {"online", "recently_offline", "offline", "sleeping", "powered_off", "location_unavailable", "unknown"}:
        return connection_state

    if status in {"sleeping", "powered_off", "location_unavailable", "unknown"}:
        return status

    now = datetime.utcnow()
    if last_seen is not None:
        age = now - last_seen
        if age <= timedelta(minutes=2):
            return "online"
        if age <= timedelta(minutes=10):
            return "recently_offline"

    if last_latitude is not None and last_longitude is not None:
        if last_location_time is not None:
            age = now - last_location_time
            if age <= timedelta(minutes=10):
                return "offline"
        return "offline"

    if status == "online":
        return "location_unavailable"

    return "offline" if status == "offline" else "unknown"

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone_number = Column(String(16), nullable=True)
    phone_verified_at = Column(DateTime, nullable=True)
    role = Column(String(20), nullable=False, default="USER", server_default="USER")
    account_status = Column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    devices = relationship("Device", back_populates="owner", cascade="all, delete-orphan")


class TotpCredential(Base):
    __tablename__ = "totp_credentials"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    encrypted_secret = Column(String, nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)
    last_counter = Column(Integer, nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    auth_time = Column(Integer, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)


class AccountInvitation(Base):
    __tablename__ = "account_invitations"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class PhoneRecoveryChallenge(Base):
    __tablename__ = "phone_recovery_challenges"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    phone_hash = Column(String(64), nullable=False, index=True)
    ip_hash = Column(String(64), nullable=False, index=True)
    code_hash = Column(String(64), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    sent_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)


class PhoneVerificationChallenge(Base):
    __tablename__ = "phone_verification_challenges"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    phone_hash = Column(String(64), nullable=False, index=True)
    ip_hash = Column(String(64), nullable=False, index=True)
    code_hash = Column(String(64), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    sent_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)


class Device(Base):
    __tablename__ = "devices"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    device_type = Column(String, default="laptop")
    platform = Column(String, nullable=True)
    model = Column(String, nullable=True)
    mac_address = Column(String, nullable=True)
    status = Column(String, default="offline")
    connection_state = Column(String, default="unknown")
    is_lost_mode = Column(Boolean, default=False)
    battery_level = Column(Integer, nullable=True)
    is_charging = Column(Boolean, nullable=True)
    wifi_connected = Column(Boolean, nullable=True)
    network_type = Column(String, nullable=True)
    local_ip = Column(String, nullable=True)
    public_ip = Column(String, nullable=True)
    os_version = Column(String, nullable=True)
    cpu_info = Column(String, nullable=True)
    ram_total = Column(String, nullable=True)
    storage_total = Column(String, nullable=True)
    last_latitude = Column(Float, nullable=True)
    last_longitude = Column(Float, nullable=True)
    last_accuracy = Column(Float, nullable=True)
    last_location_source = Column(String, nullable=True)
    last_location_time = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    last_online = Column(DateTime, nullable=True)
    last_offline = Column(DateTime, nullable=True)
    last_battery = Column(Integer, nullable=True)
    last_ip = Column(String, nullable=True)
    last_network = Column(String, nullable=True)
    offline_since = Column(DateTime, nullable=True)
    last_movement_state = Column(String, nullable=True)
    last_speed = Column(Float, nullable=True)
    last_heading = Column(Float, nullable=True)
    last_wifi_network = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="devices")
    locations = relationship("Location", back_populates="device", cascade="all, delete-orphan")
    commands = relationship("Command", back_populates="device", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="device", cascade="all, delete-orphan")
    offline_sessions = relationship("OfflineSession", back_populates="device", cascade="all, delete-orphan")


class OfflineSession(Base):
    __tablename__ = "offline_sessions"
    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    reason = Column(String, default="UNKNOWN")
    last_known_latitude = Column(Float, nullable=True)
    last_known_longitude = Column(Float, nullable=True)
    last_known_accuracy = Column(Float, nullable=True)
    last_known_battery = Column(Integer, nullable=True)
    last_known_ip = Column(String, nullable=True)
    device = relationship("Device", back_populates="offline_sessions")

class Location(Base):
    __tablename__ = "locations"
    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    source = Column(String, nullable=True)
    movement_state = Column(String, default="STATIONARY")
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    device = relationship("Device", back_populates="locations")

class Command(Base):
    __tablename__ = "commands"
    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True)
    user_id = Column(String, ForeignKey("users.id"))
    command = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, executed, failed
    result = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)
    device = relationship("Device", back_populates="commands")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True)
    action = Column(String, nullable=False)
    details = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    device = relationship("Device", back_populates="audit_logs")

class PairingCode(Base):
    __tablename__ = "pairing_codes"
    code = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    device_name = Column(String, nullable=False)
    device_type = Column(String, default="laptop")
    expires_at = Column(DateTime, nullable=False)


class Geofence(Base):
    __tablename__ = "geofences"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius = Column(Float, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GeofenceState(Base):
    __tablename__ = "geofence_states"
    __table_args__ = (UniqueConstraint("geofence_id", "device_id", name="uq_geofence_device_state"),)
    id = Column(String, primary_key=True, default=generate_uuid)
    geofence_id = Column(String, ForeignKey("geofences.id"), index=True, nullable=False)
    device_id = Column(String, ForeignKey("devices.id"), index=True, nullable=False)
    inside = Column(Boolean, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    device_id = Column(String, ForeignKey("devices.id"), index=True, nullable=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    read = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="OPEN", server_default="OPEN", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class AlertStatusEvent(Base):
    __tablename__ = "alert_status_events"
    id = Column(String, primary_key=True, default=generate_uuid)
    alert_id = Column(String, ForeignKey("alerts.id"), index=True, nullable=False)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    old_status = Column(String(20), nullable=False)
    new_status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"
    id = Column(String, primary_key=True, default=generate_uuid)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    target_user_id = Column(String, nullable=True, index=True)
    target_device_id = Column(String, nullable=True, index=True)
    details = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class AdminLocationAccessRequest(Base):
    __tablename__ = "admin_location_access_requests"
    id = Column(String, primary_key=True, default=generate_uuid)
    requester_user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    target_user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    target_device_id = Column(String, index=True, nullable=True)
    scope = Column(String(40), nullable=False, default="LOCATION_READ", server_default="LOCATION_READ")
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    reason = Column(String(500), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    decided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
