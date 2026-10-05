const LOCATION_SOURCE_LABELS: Record<string, string> = {
  gps: 'GPS / GNSS',
  satellite: 'GPS / GNSS',
  windows_location: 'Windows Location Services',
  wifi_location: 'Wi-Fi positioning',
  cellular_location: 'Cellular positioning',
  ip_geolocation: 'IP geolocation (approximate)',
  android_fused: 'Android Fused Location',
  core_location: 'Apple Core Location',
  watch_gnss: 'Watch GPS / GNSS',
  unavailable: 'Location unavailable',
};

export function getLocationSourceLabel(source: string | null | undefined): string {
  if (!source) return 'Source unavailable';
  return LOCATION_SOURCE_LABELS[source.toLowerCase()] || source.replaceAll('_', ' ');
}

export function formatCoordinate(value: number, axis: 'latitude' | 'longitude'): string {
  const direction = axis === 'latitude'
    ? value < 0 ? 'S' : 'N'
    : value < 0 ? 'W' : 'E';
  return `${Math.abs(value).toFixed(4)}° ${direction}`;
}

export function formatAccuracy(meters: number | null | undefined): string {
  if (meters == null || !Number.isFinite(meters) || meters < 0) return 'Not reported';
  if (meters >= 1000) return `±${(meters / 1000).toFixed(meters >= 10000 ? 0 : 1)} km`;
  return `±${Math.round(meters)} m`;
}

export function parseUtcTimestamp(timestamp: string): number {
  const includesTimezone = /(?:z|[+-]\d{2}:\d{2})$/i.test(timestamp);
  return Date.parse(includesTimezone ? timestamp : `${timestamp}Z`);
}

export function formatLocationAge(timestamp: string | null | undefined): string {
  if (!timestamp) return 'Never';
  const elapsedSeconds = Math.floor((Date.now() - parseUtcTimestamp(timestamp)) / 1000);
  if (!Number.isFinite(elapsedSeconds)) return 'Unknown';
  if (elapsedSeconds < 5) return 'Just now';
  if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`;
  if (elapsedSeconds < 3600) return `${Math.floor(elapsedSeconds / 60)}m ago`;
  if (elapsedSeconds < 86400) return `${Math.floor(elapsedSeconds / 3600)}h ago`;
  return `${Math.floor(elapsedSeconds / 86400)}d ago`;
}
