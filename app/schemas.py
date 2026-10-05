from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserResponse(UserBase):
    id: str
    created_at: datetime
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class TokenRefresh(BaseModel):
    refresh_token: str

class LocalPinUnlock(BaseModel):
    pin: str

class DeviceBase(BaseModel):
    name: str
    device_type: str = "laptop"

class DeviceCreate(DeviceBase):
    id: str
    platform: Optional[str] = None
    model: Optional[str] = None

class DeviceUpdate(BaseModel):
    mac_address: Optional[str] = None
    battery_level: Optional[int] = None
    is_charging: Optional[bool] = None
    wifi_connected: Optional[bool] = None
    network_type: Optional[str] = None
    local_ip: Optional[str] = None
    public_ip: Optional[str] = None
    os_version: Optional[str] = None
    cpu_info: Optional[str] = None
    ram_total: Optional[str] = None
    storage_total: Optional[str] = None

class DeviceResponse(DeviceBase):
    id: str
    user_id: str
    platform: Optional[str] = None
    model: Optional[str] = None
    mac_address: Optional[str] = None
    status: str
    is_lost_mode: bool
    battery_level: Optional[int] = None
    is_charging: Optional[bool] = None
    wifi_connected: Optional[bool] = None
    network_type: Optional[str] = None
    local_ip: Optional[str] = None
    public_ip: Optional[str] = None
    os_version: Optional[str] = None
    cpu_info: Optional[str] = None
    ram_total: Optional[str] = None
    storage_total: Optional[str] = None
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None
    last_accuracy: Optional[float] = None
    last_location_source: Optional[str] = None
    last_location_time: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    created_at: datetime
    class Config:
        from_attributes = True

class LocationCreate(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    source: Optional[str] = None

class LocationResponse(LocationCreate):
    id: str
    device_id: str
    timestamp: datetime
    class Config:
        from_attributes = True

class CommandResponse(BaseModel):
    id: str
    device_id: str
    user_id: str
    command: str
    status: str
    result: Optional[str] = None
    created_at: datetime
    executed_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class PairingCodeResponse(BaseModel):
    code: str
    device_name: str
    device_type: str
    expires_at: datetime
    class Config:
        from_attributes = True

class DeviceInstallerRequest(DeviceBase):
    server_url: str

class DeviceInstallerResponse(BaseModel):
    filename: str
    content_base64: str
    device_name: str
    expires_at: datetime

class DevicePairingResponse(BaseModel):
    id: str
    device_token: str
    name: str

class AuditLogResponse(BaseModel):
    id: str
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime
    class Config:
        from_attributes = True
