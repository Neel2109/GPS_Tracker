/**
 * TrackGuard API Service
 * Handles all HTTP requests to the backend.
 */
import type {
  AdminAuditEvent,
  AdminIncident,
  AdminPage,
  AdminSession,
  AdminDevice,
  AdminOverview,
  AdminGrantedDeviceLocation,
  AdminUser,
  AdminUserProvisioned,
  AdminDeviceCommandType,
  Alert,
  AuthResponse,
  Device,
  DeviceProximitySnapshot,
  Geofence,
  Location,
  Command,
  PairingCode,
  DeviceInstaller,
  AuditLog,
  Trip,
  LocationAccessRequest,
  User,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';

// ─── Token Management ──────────────────────────────────────
let accessToken: string | null = localStorage.getItem('access_token');
let refreshToken: string | null = localStorage.getItem('refresh_token');

export function setTokens(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
}

export function getAccessToken() {
  return accessToken;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

// ─── Fetch Wrapper ─────────────────────────────────────────
async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  const isSignInRequest = [
    '/api/auth/unlock',
    '/api/auth/phone/login',
    '/api/auth/phone/activate',
    '/api/auth/totp/setup',
    '/api/auth/totp/confirm',
  ].includes(path);
  if (res.status === 401 && retry && refreshToken && !isSignInRequest) {
    // Try to refresh the token
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, options, false);
    }
    clearTokens();
    window.location.href = '/unlock';
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    let errorMsg = `HTTP ${res.status}`;
    if (err.detail) {
      if (Array.isArray(err.detail)) {
        errorMsg = err.detail.map((e: any) => `${e.loc[e.loc.length - 1]}: ${e.msg}`).join(', ');
      } else {
        errorMsg = String(err.detail);
      }
    }
    throw new ApiError(errorMsg, res.status);
  }

  // Handle 204 No Content
  if (res.status === 204) return {} as T;

  return res.json();
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (res.ok) {
      const data: AuthResponse = await res.json();
      setTokens(data.access_token, data.refresh_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      return true;
    }
  } catch {
    // Refresh failed
  }
  return false;
}

// ─── Auth API ──────────────────────────────────────────────
export const authAPI = {
  loginWithPhone: (phone_number: string, otp_code: string) =>
    apiFetch<AuthResponse>('/api/auth/phone/login', {
      method: 'POST',
      body: JSON.stringify({ phone_number, otp_code }),
    }),

  activatePhoneAccount: (phone_number: string, otp_code: string) =>
    apiFetch<AuthResponse>('/api/auth/phone/activate', {
      method: 'POST',
      body: JSON.stringify({ phone_number, otp_code }),
    }),

  claimInvitation: (phone_number: string, invitation_token: string) =>
    apiFetch<{ secret: string; provisioning_uri: string }>('/api/auth/phone/invitation/setup', {
      method: 'POST',
      body: JSON.stringify({ phone_number, invitation_token }),
    }),

  requestPhoneRecovery: (phone_number: string) =>
    apiFetch<{ message: string }>('/api/auth/phone/recovery/request', {
      method: 'POST',
      body: JSON.stringify({ phone_number }),
    }),

  requestPhoneVerification: (phone_number: string) =>
    apiFetch<{ message: string }>('/api/auth/phone/verification/request', {
      method: 'POST',
      body: JSON.stringify({ phone_number }),
    }),

  confirmPhoneVerification: (phone_number: string, otp_code: string) =>
    apiFetch<{ message: string }>('/api/auth/phone/verification/confirm', {
      method: 'POST',
      body: JSON.stringify({ phone_number, otp_code }),
    }),

  confirmPhoneRecovery: (phone_number: string, otp_code: string) =>
    apiFetch<{ secret: string; provisioning_uri: string }>('/api/auth/phone/recovery/confirm', {
      method: 'POST',
      body: JSON.stringify({ phone_number, otp_code }),
    }),

  unlock: (pin: string, otp_code?: string) =>
    apiFetch<AuthResponse>('/api/auth/unlock', {
      method: 'POST',
      body: JSON.stringify({ pin, otp_code }),
    }),

  setupTotp: (pin: string, phone_number?: string) =>
    apiFetch<{ secret: string; provisioning_uri: string }>('/api/auth/totp/setup', {
      method: 'POST',
      body: JSON.stringify({ pin, phone_number }),
    }),

  confirmTotp: (pin: string, otp_code: string) =>
    apiFetch<AuthResponse>('/api/auth/totp/confirm', {
      method: 'POST',
      body: JSON.stringify({ pin, otp_code }),
    }),

  logout: () =>
    apiFetch<{ message: string }>('/api/auth/logout', { method: 'POST' }),

  getMe: () =>
    apiFetch<User>('/api/auth/me'),
};

export const adminAPI = {
  overview: () => apiFetch<AdminOverview>('/api/admin/overview'),

  users: () => apiFetch<AdminUser[]>('/api/admin/users'),

  usersPage: (params: {
    offset: number; limit: number; search?: string; role?: string; status?: string;
    sort_by?: string; sort_direction?: string;
  }) => apiFetch<AdminPage<AdminUser>>(`/api/admin/users/page?${new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((query, [key, value]) => {
      if (value !== undefined && value !== '') query[key] = String(value);
      return query;
    }, {}),
  )}`),

  createUser: (user: { name: string; phone_number: string; role: 'USER' | 'ADMIN' }) =>
    apiFetch<AdminUserProvisioned>('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(user),
    }),

  updateUser: (
    id: string,
    update: { role?: AdminUser['role']; account_status?: AdminUser['account_status'] },
  ) =>
    apiFetch<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    }),

  resetAuthenticator: (id: string) =>
    apiFetch<{ secret: string; provisioning_uri: string }>(
      `/api/admin/users/${encodeURIComponent(id)}/reset-authenticator`,
      { method: 'POST' },
    ),

  createInvitation: (id: string) =>
    apiFetch<{ invitation_token: string; invitation_expires_at: string }>(
      `/api/admin/users/${encodeURIComponent(id)}/invitation`,
      { method: 'POST' },
    ),

  userSessions: (id: string) =>
    apiFetch<AdminSession[]>(`/api/admin/users/${encodeURIComponent(id)}/sessions`),

  revokeUserSession: (userId: string, sessionId: string) =>
    apiFetch<AdminSession>(
      `/api/admin/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/revoke`,
      { method: 'POST' },
    ),

  devices: () => apiFetch<AdminDevice[]>('/api/admin/devices'),

  devicesPage: (params: {
    offset: number; limit: number; search?: string; status?: string; device_type?: string;
    lost_mode?: string; sort_by?: string; sort_direction?: string; owner_user_id?: string;
  }) => apiFetch<AdminPage<AdminDevice>>(`/api/admin/devices/page?${new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((query, [key, value]) => {
      if (value !== undefined && value !== '') query[key] = String(value);
      return query;
    }, {}),
  )}`),

  audit: () => apiFetch<AdminAuditEvent[]>('/api/admin/audit'),

  auditPage: (params: {
    offset: number; limit: number; search?: string; action?: string; sort_direction?: string;
  }) => apiFetch<AdminPage<AdminAuditEvent>>(`/api/admin/audit/page?${new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((query, [key, value]) => {
      if (value !== undefined && value !== '') query[key] = String(value);
      return query;
    }, {}),
  )}`),

  incidents: (status: string = 'OPEN') =>
    apiFetch<AdminIncident[]>(`/api/admin/incidents?status=${encodeURIComponent(status)}`),

  updateIncident: (id: string, status: 'ACKNOWLEDGED' | 'RESOLVED') =>
    apiFetch<AdminIncident>(`/api/admin/incidents/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),

  accessRequests: () =>
    apiFetch<LocationAccessRequest[]>('/api/admin/access-requests'),

  requestLocationAccess: (request: {
    target_user_id: string;
    scope: 'LOCATION_READ' | 'DEVICE_CONTROL';
    target_device_id?: string;
    reason: string;
    duration_minutes: number;
  }) =>
    apiFetch<LocationAccessRequest>('/api/admin/access-requests', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  revokeLocationAccess: (id: string) =>
    apiFetch<LocationAccessRequest>(`/api/admin/access-requests/${encodeURIComponent(id)}/revoke`, {
      method: 'POST',
    }),

  grantedDeviceLocations: (id: string) =>
    apiFetch<AdminGrantedDeviceLocation[]>(
      `/api/admin/access-requests/${encodeURIComponent(id)}/devices`,
    ),

  grantedDeviceHistory: (requestId: string, deviceId: string, period = '7days') =>
    apiFetch<Location[]>(
      `/api/admin/access-requests/${encodeURIComponent(requestId)}/devices/${encodeURIComponent(deviceId)}/locations?period=${encodeURIComponent(period)}`,
    ),

  controlDevice: (
    requestId: string,
    deviceId: string,
    command: AdminDeviceCommandType,
    confirmation: string,
  ) =>
    apiFetch<Command>(
      `/api/admin/access-requests/${encodeURIComponent(requestId)}/devices/${encodeURIComponent(deviceId)}/commands`,
      {
        method: 'POST',
        body: JSON.stringify({ command, confirmation }),
      },
    ),
};

export const accessRequestAPI = {
  list: () => apiFetch<LocationAccessRequest[]>('/api/access-requests'),

  decide: (id: string, action: 'APPROVE' | 'DENY' | 'REVOKE') =>
    apiFetch<LocationAccessRequest>(`/api/access-requests/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
};

// ─── Device API ────────────────────────────────────────────
export const deviceAPI = {
  list: () =>
    apiFetch<Device[]>('/api/devices'),

  get: (id: string) =>
    apiFetch<Device>(`/api/devices/${id}`),

  delete: (id: string) =>
    apiFetch<{ message: string }>(`/api/devices/${id}`, { method: 'DELETE' }),

  getStatus: (id: string) =>
    apiFetch<Record<string, unknown>>(`/api/devices/${id}/status`),

  // Pairing
  generatePairingCode: (deviceName: string, deviceType: string = 'laptop') =>
    apiFetch<PairingCode>('/api/devices/pair/generate', {
      method: 'POST',
      body: JSON.stringify({ name: deviceName, device_type: deviceType }),
    }),

  createInstaller: (deviceName: string, deviceType: string, serverUrl: string) =>
    apiFetch<DeviceInstaller>('/api/devices/pair/installer', {
      method: 'POST',
      body: JSON.stringify({ name: deviceName, device_type: deviceType, server_url: serverUrl }),
    }),

  // Lost Mode
  enableLostMode: (id: string) =>
    apiFetch<{ message: string; is_lost_mode: boolean }>(`/api/devices/${id}/lost-mode/enable`, { method: 'POST' }),

  disableLostMode: (id: string) =>
    apiFetch<{ message: string; is_lost_mode: boolean }>(`/api/devices/${id}/lost-mode/disable`, { method: 'POST' }),
};

// ─── Location API ──────────────────────────────────────────
export const locationAPI = {
  getProximity: (thresholdMeters = 250) =>
    apiFetch<DeviceProximitySnapshot>(
      `/api/devices/proximity?threshold_meters=${encodeURIComponent(thresholdMeters)}`,
    ),

  getCurrent: (deviceId: string) =>
    apiFetch<Location | null>(`/api/devices/${deviceId}/location`),

  getHistory: (deviceId: string, params?: { period?: string; start_date?: string; end_date?: string; limit?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.period) searchParams.set('period', params.period);
    if (params?.start_date) searchParams.set('start_date', params.start_date);
    if (params?.end_date) searchParams.set('end_date', params.end_date);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    const query = searchParams.toString();
    return apiFetch<Location[]>(`/api/devices/${deviceId}/locations${query ? `?${query}` : ''}`);
  },
};

export const tripAPI = {
  list: (deviceId: string, period = '30days') =>
    apiFetch<Trip[]>(`/api/devices/${deviceId}/trips?period=${encodeURIComponent(period)}`),

  getLocations: (deviceId: string, tripId: string, period = '30days') =>
    apiFetch<Location[]>(
      `/api/devices/${deviceId}/trips/${encodeURIComponent(tripId)}/locations?period=${encodeURIComponent(period)}`
    ),
};

export const geofenceAPI = {
  list: () => apiFetch<Geofence[]>('/api/geofences'),

  create: (geofence: Omit<Geofence, 'id' | 'created_at'>) =>
    apiFetch<Geofence>('/api/geofences', {
      method: 'POST',
      body: JSON.stringify(geofence),
    }),

  update: (id: string, geofence: Partial<Omit<Geofence, 'id' | 'created_at'>>) =>
    apiFetch<Geofence>(`/api/geofences/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(geofence),
    }),

  delete: (id: string) =>
    apiFetch<void>(`/api/geofences/${id}`, { method: 'DELETE' }),
};

export const alertAPI = {
  list: (unreadOnly = false) =>
    apiFetch<Alert[]>(`/api/alerts?unread_only=${unreadOnly}`),

  markRead: (id: string) =>
    apiFetch<Alert>(`/api/alerts/${id}/read`, { method: 'POST' }),

  markAllRead: () =>
    apiFetch<void>('/api/alerts/read-all', { method: 'POST' }),

  updateStatus: (id: string, status: 'ACKNOWLEDGED' | 'RESOLVED') =>
    apiFetch<Alert>(`/api/alerts/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),

  sos: (deviceId: string | undefined, message: string) =>
    apiFetch<Alert>('/api/alerts/sos', {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId || null, message }),
    }),
};

export const privacyAPI = {
  exportAccountData: () =>
    apiFetch<Record<string, unknown>>('/api/account/export'),

  deleteLocationHistory: () =>
    apiFetch<{ deleted_locations: number }>(
      '/api/account/location-history?confirmation=DELETE_MY_LOCATION_HISTORY',
      { method: 'DELETE' },
    ),
};

export const healthAPI = {
  check: () => apiFetch<{ status: string; database: string }>('/health'),
};

// ─── Command API ───────────────────────────────────────────
export const commandAPI = {
  lock: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/lock`, { method: 'POST' }),

  sleep: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/sleep`, { method: 'POST' }),

  restart: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/restart`, { method: 'POST' }),

  shutdown: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/shutdown`, { method: 'POST' }),

  requestStatus: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/status`, { method: 'POST' }),

  requestLocation: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/location`, { method: 'POST' }),

  ping: (deviceId: string) =>
    apiFetch<Command>(`/api/devices/${deviceId}/commands/ping`, { method: 'POST' }),

  getHistory: (deviceId: string, limit = 50) =>
    apiFetch<Command[]>(`/api/devices/${deviceId}/commands?limit=${limit}`),

  getAuditLog: (deviceId: string, limit = 50) =>
    apiFetch<AuditLog[]>(`/api/devices/${deviceId}/audit?limit=${limit}`),
};
