import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    devices = relationship("Device", back_populates="owner", cascade="all, delete-orphan")

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
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="devices")
    locations = relationship("Location", back_populates="device", cascade="all, delete-orphan")
    commands = relationship("Command", back_populates="device", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="device", cascade="all, delete-orphan")

class Location(Base):
    __tablename__ = "locations"
    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    source = Column(String, nullable=True)
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
