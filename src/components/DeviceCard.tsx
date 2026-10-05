import { useNavigate } from 'react-router-dom';
import type { Device } from '../types';
import { formatAccuracy, formatCoordinate, getLocationSourceLabel } from '../utils/location';

interface Props {
  device: Device;
  expanded?: boolean;
}

export default function DeviceCard({ device, expanded }: Props) {
  const navigate = useNavigate();
  const icon = { laptop: '💻', desktop: '🖥️', android: '📱', iphone: '📱', ipad: '📱', tablet: '📱', smartwatch: '⌚', other: '📟' }[device.device_type] || '📟';

  const statusPill = {
    online: { cls: 'tg-pill-online', label: 'Online' },
    offline: { cls: 'tg-pill-offline', label: 'Offline' },
    sleeping: { cls: 'tg-pill-sleeping', label: 'Sleeping' },
    low_battery: { cls: 'tg-pill-online', label: 'Low Battery' },
    location_unavailable: { cls: 'tg-pill-offline', label: 'No Location' },
  }[device.status] || { cls: 'tg-pill-offline', label: device.status };

  const timeAgo = device.last_seen ? getTimeAgo(device.last_seen) : 'Never';

  if (!expanded) return null;

  return (
    <div
      className="tg-card cursor-pointer group"
      onClick={() => navigate(`/devices/${device.id}`)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-bg flex items-center justify-center text-xl">
            {icon}
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider font-medium">Device</p>
            <h3 className="text-base font-semibold text-text group-hover:text-primary transition-colors">
              {device.name}
            </h3>
          </div>
        </div>
        <span className={`tg-pill ${statusPill.cls}`}>{statusPill.label}</span>
      </div>

      {/* Info grid — like departure/arrival in reference */}
      <div className="flex gap-8 mb-5">
        <div>
          <p className="text-xs text-text-muted mb-0.5">Last Seen</p>
          <p className="text-sm font-semibold text-text">{timeAgo}</p>
        </div>
        {device.last_location_time && (
          <div className="flex items-center gap-4">
            <span className="text-text-muted">- - -</span>
            <div>
              <p className="text-xs text-text-muted mb-0.5">Location Updated</p>
              <p className="text-sm font-semibold text-text">{getTimeAgo(device.last_location_time)}</p>
            </div>
          </div>
        )}
      </div>

      {/* Stats row — like customer/price/description/weight in reference */}
      <div className="grid grid-cols-4 gap-4 mb-5">
        <div>
          <p className="text-[11px] text-text-muted mb-0.5">Platform</p>
          <p className="text-sm font-medium text-text capitalize">{device.platform}</p>
        </div>
        <div>
          <p className="text-[11px] text-text-muted mb-0.5">Battery</p>
          <p className="text-sm font-medium text-text">
            {device.battery_level != null ? `${device.battery_level}%` : '—'}
            {device.is_charging && ' ⚡'}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-text-muted mb-0.5">Network</p>
          <p className="text-sm font-medium text-text">{device.wifi_connected ? 'Wi-Fi' : device.network_type || '—'}</p>
        </div>
        <div>
          <p className="text-[11px] text-text-muted mb-0.5">Accuracy</p>
          <p className="text-sm font-medium text-text">{formatAccuracy(device.last_accuracy)}</p>
        </div>
      </div>

      {/* Location + Source — bottom section */}
      {device.last_latitude != null && device.last_longitude != null && (
        <div className="flex items-center justify-between pt-4 border-t border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-bg flex items-center justify-center">
              <PinIcon />
            </div>
            <div>
              <p className="text-xs text-text-muted">Location</p>
              <p className="text-xs font-medium text-text">
                {formatCoordinate(device.last_latitude, 'latitude')}, {formatCoordinate(device.last_longitude, 'longitude')}
              </p>
            </div>
          </div>
          <span className="text-[10px] text-text-muted bg-bg px-2.5 py-1 rounded-md tracking-wider">
            {getLocationSourceLabel(device.last_location_source)}
          </span>
        </div>
      )}

      {/* Lost Mode */}
      {device.is_lost_mode && (
        <div className="mt-4 px-4 py-3 rounded-xl lost-mode-banner text-center">
          <span className="text-xs font-semibold text-lost uppercase tracking-wider">🔴 Lost Mode Active</span>
        </div>
      )}
    </div>
  );
}

function PinIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6C5CE7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function getTimeAgo(isoString: string): string {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 5) return 'Just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
