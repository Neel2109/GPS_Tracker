from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal, Optional
from datetime import datetime

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserResponse(UserBase):
    email: str
    id: str
    phone_number: Optional[str] = None
    phone_verified_at: Optional[datetime] = None
    role: str = "USER"
    account_status: str = "ACTIVE"
    created_at: datetime
    last_login_at: Optional[datetime] = None
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
    pin: str = Field(pattern=r"^[0-9]{6,12}$")
    otp_code: Optional[str] = Field(default=None, pattern=r"^[0-9]{6}$")
    phone_number: Optional[str] = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")


class PhoneTotpLogin(BaseModel):
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    otp_code: str = Field(pattern=r"^[0-9]{6}$")


class PhoneTotpActivation(PhoneTotpLogin):
    pass


class PhoneRecoveryRequest(BaseModel):
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")


class PhoneRecoveryConfirm(PhoneRecoveryRequest):
    otp_code: str = Field(pattern=r"^[0-9]{6}$")


class PhoneRecoveryRequestResponse(BaseModel):
    message: str


class PhoneVerificationRequest(BaseModel):
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")


class PhoneVerificationConfirm(PhoneVerificationRequest):
    otp_code: str = Field(pattern=r"^[0-9]{6}$")


class AlertStatusUpdate(BaseModel):
    status: Literal["ACKNOWLEDGED", "RESOLVED"]


class LocalPinTotpConfirm(BaseModel):
    pin: str = Field(pattern=r"^[0-9]{6,12}$")
    otp_code: str = Field(pattern=r"^[0-9]{6}$")


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    role: Literal["USER", "ADMIN"] = "USER"


class AdminUserUpdate(BaseModel):
    role: Optional[Literal["USER", "ADMIN", "SUPER_ADMIN"]] = None
    account_status: Optional[Literal["ACTIVE", "SUSPENDED"]] = None


class AdminUserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone_number: Optional[str] = None
    phone_verified_at: Optional[datetime] = None
    role: str
    account_status: str
    device_count: int
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AdminPageInfo(BaseModel):
    total: int
    offset: int
    limit: int


class AdminUserPage(AdminPageInfo):
    items: list[AdminUserResponse]


class AdminUserProvisioned(AdminUserResponse):
    invitation_token: str
    invitation_expires_at: datetime


class AccountInvitationResponse(BaseModel):
    invitation_token: str
    invitation_expires_at: datetime


class PhoneInvitationClaim(BaseModel):
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    invitation_token: str = Field(min_length=32, max_length=128)


class AdminIncidentResponse(BaseModel):
    id: str
    user_id: str
    user_name: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    type: str
    title: str
    message: str
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class AdminSessionResponse(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AdminDeviceResponse(BaseModel):
    id: str
    name: str
    device_type: str
    platform: Optional[str] = None
    model: Optional[str] = None
    status: str
    is_lost_mode: bool
    battery_level: Optional[int] = None
    last_seen: Optional[datetime] = None
    owner_user_id: str
    owner_name: str
    owner_phone_number: Optional[str] = None
    created_at: datetime


class AdminDevicePage(AdminPageInfo):
    items: list[AdminDeviceResponse]


class AdminAuditEventResponse(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    action: str
    target_user_id: Optional[str] = None
    target_device_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime


class AdminAuditEventPage(AdminPageInfo):
    items: list[AdminAuditEventResponse]


class AdminOverview(BaseModel):
    total_users: int
    active_users: int
    admins: int
    total_devices: int
    online_devices: int


class LocationAccessRequestCreate(BaseModel):
    target_user_id: str
    scope: Literal["LOCATION_READ", "DEVICE_CONTROL"] = "LOCATION_READ"
    target_device_id: Optional[str] = None
    reason: str = Field(min_length=10, max_length=500)
    duration_minutes: int = Field(ge=15, le=240)


class LocationAccessRequestDecision(BaseModel):
    action: Literal["APPROVE", "DENY", "REVOKE"]


class LocationAccessRequestResponse(BaseModel):
    id: str
    requester_user_id: str
    requester_name: str
    target_user_id: str
    target_name: str
    target_device_id: Optional[str] = None
    target_device_name: Optional[str] = None
    target_device_type: Optional[str] = None
    scope: str
    status: str
    reason: str
    duration_minutes: int
    created_at: datetime
    decided_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class AdminGrantedDeviceLocation(BaseModel):
    id: str
    name: str
    device_type: str
    status: str
    access_request_id: str
    owner_user_id: str
    owner_name: str
    owner_role: str
    platform: Optional[str] = None
    model: Optional[str] = None
    is_lost_mode: bool = False
    battery_level: Optional[int] = None
    is_charging: Optional[bool] = None
    network_type: Optional[str] = None
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None
    last_accuracy: Optional[float] = None
    last_location_source: Optional[str] = None
    last_location_time: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    last_speed: Optional[float] = None
    movement_state: Optional[str] = None


class AdminDeviceCommand(BaseModel):
    command: Literal["LOCK", "SLEEP", "RESTART", "SHUTDOWN", "ENABLE_LOST_MODE", "DISABLE_LOST_MODE"]
    confirmation: str = Field(min_length=1, max_length=100)

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
    connection_state: Optional[str] = None
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
    last_online: Optional[datetime] = None
    last_offline: Optional[datetime] = None
    last_battery: Optional[int] = None
    last_ip: Optional[str] = None
    last_network: Optional[str] = None
    offline_since: Optional[datetime] = None
    last_movement_state: Optional[str] = None
    last_speed: Optional[float] = None
    last_heading: Optional[float] = None
    last_wifi_network: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class LocationCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    source: Optional[str] = None
    movement_state: str = "STATIONARY"
    timestamp: Optional[datetime] = None

class DeviceLocationBatch(BaseModel):
    locations: List[LocationCreate] = Field(max_length=500)

class LocationResponse(LocationCreate):
    id: str
    device_id: str
    timestamp: datetime
    class Config:
        from_attributes = True

class DeviceProximityPair(BaseModel):
    first_device_id: str
    first_device_name: str
    first_location_time: Optional[datetime] = None
    first_accuracy_meters: Optional[float] = None
    first_movement_state: Optional[str] = None
    second_device_id: str
    second_device_name: str
    second_location_time: Optional[datetime] = None
    second_accuracy_meters: Optional[float] = None
    second_movement_state: Optional[str] = None
    last_known_distance_meters: Optional[float] = None
    threshold_meters: int
    status: Literal["NEAR", "SEPARATED", "UNCERTAIN", "UNKNOWN"]
    possible_left_behind_device_name: Optional[str] = None


class DeviceProximitySnapshot(BaseModel):
    generated_at: datetime
    threshold_meters: int
    freshness_limit_minutes: int
    max_fix_skew_minutes: int
    pairs: List[DeviceProximityPair]

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


class GeofenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius: float = Field(gt=0, le=100000)
    enabled: bool = True


class GeofenceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius: Optional[float] = Field(default=None, gt=0, le=100000)
    enabled: Optional[bool] = None


class GeofenceResponse(GeofenceCreate):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: str
    device_id: Optional[str] = None
    type: str
    title: str
    message: str
    read: bool
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"] = "OPEN"
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SosCreate(BaseModel):
    device_id: Optional[str] = None
    message: str = Field(default="Emergency assistance requested", min_length=1, max_length=500)


class TripResponse(BaseModel):
    id: str
    device_id: str
    start_time: datetime
    end_time: datetime
    start_latitude: float
    start_longitude: float
    end_latitude: float
    end_longitude: float
    distance_meters: float
    duration_seconds: float
    average_speed: Optional[float] = None
    maximum_speed: Optional[float] = None
    point_count: int
    stop_count: int = 0
    active_duration_seconds: float = 0
