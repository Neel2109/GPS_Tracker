// ─── User Types ────────────────────────────────────────────
export interface User {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// ─── Device Types ──────────────────────────────────────────
export type DeviceType = 'laptop' | 'desktop' | 'android' | 'iphone' | 'ipad' | 'tablet' | 'smartwatch' | 'other';
export type DeviceStatus = 'online' | 'offline' | 'sleeping' | 'low_battery' | 'location_unavailable';
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
  created_at: string;
}

// ─── Location Types ────────────────────────────────────────
export interface Location {
  id: string;
  device_id: string;
  latitude: number;
  longitude: number;
  accuracy: number | null;
  source: string | null;
  timestamp: string;
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
