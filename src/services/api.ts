/**
 * TrackGuard API Service
 * Handles all HTTP requests to the backend.
 */
import type { AuthResponse, Device, Location, Command, PairingCode, DeviceInstaller, AuditLog } from '../types';

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

  if (res.status === 401 && retry && refreshToken) {
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
    throw new Error(errorMsg);
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
  unlock: (pin: string) =>
    apiFetch<AuthResponse>('/api/auth/unlock', {
      method: 'POST',
      body: JSON.stringify({ pin }),
    }),

  logout: () =>
    apiFetch<{ message: string }>('/api/auth/logout', { method: 'POST' }),

  getMe: () =>
    apiFetch<{ id: string; name: string; email: string }>('/api/auth/me'),
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
