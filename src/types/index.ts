// ─── User Types ────────────────────────────────────────────
export interface User {
  id: string;
  name: string;
  email: string;
  phone_number: string | null;
  phone_verified_at?: string | null;
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN';
  account_status: 'ACTIVE' | 'SUSPENDED';
  created_at: string;
  last_login_at: string | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface AdminOverview {
  total_users: number;
  active_users: number;
  admins: number;
  total_devices: number;
  online_devices: number;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  phone_number: string | null;
  phone_verified_at: string | null;
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN';
  account_status: 'ACTIVE' | 'SUSPENDED';
  device_count: number;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserProvisioned extends AdminUser {
  invitation_token: string;
  invitation_expires_at: string;
}

export interface AdminPage<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface AdminDevice {
  id: string;
  name: string;
  device_type: string;
  platform: string | null;
  model: string | null;
  status: string;
  is_lost_mode: boolean;
  battery_level: number | null;
  last_seen: string | null;
  owner_user_id: string;
  owner_name: string;
  owner_phone_number: string | null;
  created_at: string;
}

export interface AdminAuditEvent {
  id: string;
  actor_user_id: string | null;
  action: string;
  target_user_id: string | null;
  target_device_id: string | null;
  details: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface AdminIncident {
  id: string;
  user_id: string;
  user_name: string;
  device_id: string | null;
  device_name: string | null;
  type: string;
  title: string;
  message: string;
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export interface AdminSession {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
  ip_address: string | null;
  user_agent: string | null;
}

export interface LocationAccessRequest {
  id: string;
  requester_user_id: string;
  requester_name: string;
  target_user_id: string;
  target_name: string;
  target_device_id: string | null;
  target_device_name: string | null;
  target_device_type: string | null;
  scope: string;
  status: 'PENDING' | 'APPROVED' | 'DENIED' | 'REVOKED' | 'EXPIRED';
  reason: string;
  duration_minutes: number;
  created_at: string;
  decided_at: string | null;
  expires_at: string | null;
}

export interface AdminGrantedDeviceLocation {
  id: string;
  name: string;
  device_type: string;
  status: string;
  access_request_id: string;
  owner_user_id: string;
  owner_name: string;
  owner_role: 'USER' | 'ADMIN' | 'SUPER_ADMIN';
  platform: string | null;
  model: string | null;
  is_lost_mode: boolean;
  battery_level: number | null;
  is_charging: boolean | null;
  network_type: string | null;
  last_latitude: number | null;
  last_longitude: number | null;
  last_accuracy: number | null;
  last_location_source: string | null;
  last_location_time: string | null;
  last_seen: string | null;
  last_speed: number | null;
  movement_state: string | null;
}

export type AdminDeviceCommandType =
  | 'LOCK'
  | 'SLEEP'
  | 'RESTART'
  | 'SHUTDOWN'
  | 'ENABLE_LOST_MODE'
  | 'DISABLE_LOST_MODE';

// ─── Device Types ──────────────────────────────────────────
export type DeviceType = 'laptop' | 'desktop' | 'android' | 'iphone' | 'ipad' | 'tablet' | 'smartwatch' | 'other';
export type DeviceStatus = 'online' | 'recently_offline' | 'offline' | 'sleeping' | 'powered_off' | 'location_unavailable' | 'unknown' | 'low_battery';
export type CommandType = 'LOCK' | 'SLEEP' | 'RESTART' | 'SHUTDOWN' | 'GET_STATUS' | 'GET_LOCATION' | 'PING' | 'ENABLE_LOST_MODE' | 'DISABLE_LOST_MODE';

export interface Device {
  id: string;
  user_id: string;
  name: string;
  device_type: DeviceType;
  platform: string;
  model: string | null;
  mac_address: string | null;
  status: DeviceStatus;
  connection_state?: string | null;
  is_lost_mode: boolean;
  battery_level: number | null;
  is_charging: boolean | null;
  wifi_connected: boolean | null;
  network_type: string | null;
  local_ip: string | null;
  public_ip: string | null;
  os_version: string | null;
  cpu_info: string | null;
  ram_total: string | null;
  storage_total: string | null;
  last_latitude: number | null;
  last_longitude: number | null;
  last_accuracy: number | null;
  last_location_source: string | null;
  last_location_time: string | null;
  last_seen: string | null;
  last_online?: string | null;
  last_offline?: string | null;
  last_battery?: number | null;
  last_ip?: string | null;
  last_network?: string | null;
  offline_since?: string | null;
  last_movement_state?: string | null;
  last_speed?: number | null;
  last_heading?: number | null;
  last_wifi_network?: string | null;
  movement_state?: string;
  created_at: string;
}

// ─── Location Types ────────────────────────────────────────
export interface Location {
  id: string;
  device_id: string;
  latitude: number;
  longitude: number;
  accuracy: number | null;
  altitude: number | null;
  speed: number | null;
  heading: number | null;
  source: string | null;
  movement_state: string;
  timestamp: string;
}

export interface DeviceProximityPair {
  first_device_id: string;
  first_device_name: string;
  first_location_time: string | null;
  first_accuracy_meters: number | null;
  first_movement_state: string | null;
  second_device_id: string;
  second_device_name: string;
  second_location_time: string | null;
  second_accuracy_meters: number | null;
  second_movement_state: string | null;
  last_known_distance_meters: number | null;
  threshold_meters: number;
  status: 'NEAR' | 'SEPARATED' | 'UNCERTAIN' | 'UNKNOWN';
  possible_left_behind_device_name: string | null;
}

export interface DeviceProximitySnapshot {
  generated_at: string;
  threshold_meters: number;
  freshness_limit_minutes: number;
  max_fix_skew_minutes: number;
  pairs: DeviceProximityPair[];
}

export interface Geofence {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius: number;
  enabled: boolean;
  created_at: string;
}

export interface Alert {
  id: string;
  device_id: string | null;
  type: string;
  title: string;
  message: string;
  read: boolean;
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export interface Trip {
  id: string;
  device_id: string;
  start_time: string;
  end_time: string;
  start_latitude: number;
  start_longitude: number;
  end_latitude: number;
  end_longitude: number;
  distance_meters: number;
  duration_seconds: number;
  average_speed: number | null;
  maximum_speed: number | null;
  point_count: number;
  stop_count?: number;
  active_duration_seconds?: number;
}

// ─── Command Types ─────────────────────────────────────────
export interface Command {
  id: string;
  device_id: string;
  user_id: string;
  command: string;
  status: string;
  result: string | null;
  created_at: string;
  executed_at: string | null;
}

// ─── Pairing Types ─────────────────────────────────────────
export interface PairingCode {
  code: string;
  device_name: string;
  device_type: string;
  expires_at: string;
}

export interface DeviceInstaller {
  filename: string;
  content_base64: string;
  device_name: string;
  expires_at: string;
}

// ─── Audit Log Types ───────────────────────────────────────
export interface AuditLog {
  id: string;
  action: string;
  details: string | null;
  ip_address: string | null;
  timestamp: string;
}

// ─── WebSocket Message Types ───────────────────────────────
export interface WSMessage {
  type: string;
  device_id?: string;
  access_request_id?: string;
  data?: Record<string, unknown>;
}

// ─── Device Icon Mapping ───────────────────────────────────
export const DEVICE_ICONS: Record<DeviceType, string> = {
  laptop: '💻',
  desktop: '🖥️',
  android: '📱',
  iphone: '📱',
  ipad: '📱',
  tablet: '📱',
  smartwatch: '⌚',
  other: '📟',
};

export const DEVICE_TYPE_LABELS: Record<DeviceType, string> = {
  laptop: 'Laptop',
  desktop: 'Desktop',
  android: 'Android',
  iphone: 'iPhone',
  ipad: 'iPad',
  tablet: 'Tablet',
  smartwatch: 'Smartwatch',
  other: 'Other',
};
