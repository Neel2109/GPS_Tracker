import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { BatteryMedium, Laptop, Monitor, Smartphone, Tablet, Watch } from 'lucide-react';
import type { Device } from '../types';
import { deviceAPI } from '../services/api';
import { wsService } from '../services/websocket';
import GoogleLiveMap from '../components/GoogleLiveMap';
import CommandPanel from '../components/CommandPanel';
import { formatAccuracy, formatCoordinate, formatLocationAge, getLocationSourceLabel, parseUtcTimestamp } from '../utils/location';

export default function DeviceDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<Device | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDevice = useCallback(async () => {
    if (!id) return;
    try { setDevice(await deviceAPI.get(id)); }
    catch (err) { console.error('Failed:', err); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { fetchDevice(); }, [fetchDevice]);
  useEffect(() => { const i = setInterval(fetchDevice, 1000); return () => clearInterval(i); }, [fetchDevice]);

  useEffect(() => {
    const unsubs = ['LOCATION_UPDATE','STATUS_UPDATE','BATTERY_UPDATE','DEVICE_STATUS','DEVICE_ONLINE','DEVICE_OFFLINE'].map(
      t => wsService.on(t, msg => { if (msg.device_id === id) fetchDevice(); })
    );
    return () => unsubs.forEach(u => u());
  }, [id, fetchDevice]);

  const handleDelete = async () => {
    if (!id || !confirm('Remove this device permanently?')) return;
    try { await deviceAPI.delete(id); navigate('/dashboard'); }
    catch (err: any) { alert(err.message); }
  };

  if (loading) return <div className="space-y-6 pt-4"><div className="skeleton h-10 w-48" /><div className="skeleton h-96" /></div>;

  if (!device) return (
    <div className="text-center py-20">
      <span className="text-5xl block mb-4">🔍</span>
      <h3 className="text-lg font-semibold text-text mb-2">Device not found</h3>
      <button onClick={() => navigate('/dashboard')} className="text-primary text-sm hover:underline">Back to Dashboard</button>
    </div>
  );

  const statusCls = device.status === 'online' ? 'tg-pill-online' : device.status === 'sleeping' ? 'tg-pill-sleeping' : 'tg-pill-offline';

  return (
    <div className="space-y-6 animate-in pt-2">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/dashboard')} className="w-9 h-9 rounded-xl bg-surface border border-border flex items-center justify-center hover:bg-card-hover transition-colors">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#636E72" strokeWidth="2" strokeLinecap="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <span className="device-type-icon"><DeviceTypeIcon type={device.device_type} /></span>
            <div>
              <h1 className="font-display text-xl font-bold text-text">{device.name}</h1>
              <p className="text-xs text-text-muted">{device.platform} · {device.device_type} · {device.last_seen ? getTimeAgo(device.last_seen) : 'Never'}</p>
            </div>
          </div>
        </div>
        <span className={`tg-pill ${statusCls}`}>{device.status}</span>
        <button onClick={handleDelete} className="w-9 h-9 rounded-xl hover:bg-[#FFF0F0] flex items-center justify-center transition-colors" title="Remove">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#FF6B6B" strokeWidth="2" strokeLinecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>

      {/* Lost Mode Banner */}
      {device.is_lost_mode && (
          <div className="lost-mode-banner rounded-xl px-5 py-4 flex items-center gap-3">
          <span className="text-xl">🔴</span>
          <div><p className="text-lost font-semibold text-sm">LOST MODE ACTIVE</p><p className="text-xs text-lost/60">Live location requests every second while the dashboard is open</p></div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Map + Info */}
        <div className="lg:col-span-2 space-y-6">
          {/* Map */}
          {device.last_latitude != null && device.last_longitude != null ? (
            <div className="tg-card !p-2">
              <div className="flex items-center justify-between px-4 pt-2 pb-1">
                <p className="text-xs font-semibold text-text">
                  {device.status === 'online' ? 'LIVE LOCATION' : 'LAST KNOWN LOCATION'}
                </p>
                {device.last_location_source && <span className="text-[10px] text-text-muted bg-bg px-2 py-0.5 rounded-md">{getLocationSourceLabel(device.last_location_source)}</span>}
              </div>
              {device.status !== 'online' && (
                <p className="px-4 pb-2 text-xs leading-5 text-text-secondary">
                  Last fix {formatLocationAge(device.last_location_time)}. A fresh location is unavailable until this device reconnects.
                </p>
              )}
              <GoogleLiveMap devices={[device]} selectedDeviceId={device.id} height="380px" showAccuracy className="device-details-map" />
            </div>
          ) : (
            <div className="tg-card text-center py-16">
              <span className="text-4xl block mb-3">📍</span>
              <p className="text-sm text-text-muted">No location data available</p>
            </div>
          )}

          {/* Location Details */}
          {device.last_latitude != null && (
            <div className="tg-card">
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">📍 Location Details</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <InfoItem label="Latitude" value={formatCoordinate(device.last_latitude, 'latitude')} />
                <InfoItem label="Longitude" value={formatCoordinate(device.last_longitude!, 'longitude')} />
                <InfoItem label="Accuracy" value={formatAccuracy(device.last_accuracy)} accent />
                <InfoItem label="Source" value={getLocationSourceLabel(device.last_location_source)} />
                <InfoItem label="Last fix" value={device.last_location_time ? `${formatLocationAge(device.last_location_time)} (${new Date(parseUtcTimestamp(device.last_location_time)).toLocaleString()})` : 'Never'} />
              </div>
            </div>
          )}

          {/* Device Info */}
          <div className="tg-card">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">🖥️ Device Information</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <InfoItem label="Platform" value={device.platform} />
              <InfoItem label="OS Version" value={device.os_version || '—'} />
              <InfoItem label="CPU" value={device.cpu_info || '—'} />
              <InfoItem label="RAM" value={device.ram_total || '—'} />
              <InfoItem label="Storage" value={device.storage_total || '—'} />
              <InfoItem label="Model" value={device.model || '—'} />
            </div>
          </div>

          {/* Network Info */}
          <div className="tg-card">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">🌐 Network Information</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <InfoItem label="Connection" value={device.wifi_connected ? 'Wi-Fi' : device.network_type || '—'} />
              <InfoItem label="Local IP" value={device.local_ip || '—'} />
              <InfoItem label="Public IP" value={device.public_ip || '—'} />
              <InfoItem label="MAC Address" value={device.mac_address || '—'} mono />
              <InfoItem label="Status" value={device.wifi_connected ? 'Connected' : 'Disconnected'} />
              <InfoItem label="Type" value={device.network_type || '—'} />
            </div>
          </div>
        </div>

        {/* Right: Battery + Commands + Identity */}
        <div className="space-y-6">
          {/* Battery */}
          <div className="tg-card">
            <h3 className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider mb-4"><BatteryMedium size={16} /> Battery</h3>
            <div className="text-center mb-4">
              <BatteryRing level={device.battery_level} />
              <p className="text-2xl font-display font-bold text-text mt-3">
                {device.battery_level != null ? `${device.battery_level}%` : '—'}
              </p>
              {device.is_charging && <p className="text-xs text-accent mt-1">⚡ Charging</p>}
            </div>
            {device.battery_level != null && (
              <div className="w-full h-2 bg-bg rounded-full overflow-hidden">
                <div className="h-full rounded-full battery-fill" style={{
                  width: `${device.battery_level}%`,
                  background: device.battery_level > 50 ? '#00B894' : device.battery_level > 20 ? '#FDCB6E' : '#FF6B6B',
                }} />
              </div>
            )}
          </div>

          {/* Commands */}
          <div className="tg-card">
            <CommandPanel device={device} onUpdate={fetchDevice} />
          </div>

          {/* Identity */}
          <div className="tg-card">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">🔐 Device Identity</h3>
            <div className="space-y-3">
              <InfoItem label="Device UUID" value={device.id} mono />
              <InfoItem label="Device Type" value={device.device_type} />
              <InfoItem label="Registered" value={new Date(device.created_at).toLocaleDateString()} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DeviceTypeIcon({ type }: { type: Device['device_type'] }) {
  const Icon = type === 'desktop' ? Monitor
    : type === 'android' || type === 'iphone' ? Smartphone
      : type === 'tablet' || type === 'ipad' ? Tablet
        : type === 'smartwatch' ? Watch
          : Laptop;
  return <Icon size={22} strokeWidth={1.8} aria-hidden="true" />;
}

function InfoItem({ label, value, mono, accent }: { label: string; value: string; mono?: boolean; accent?: boolean }) {
  return (
    <div>
      <p className="text-[10px] text-text-muted uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-sm ${accent ? 'text-primary font-semibold' : 'text-text'} ${mono ? 'font-mono text-xs break-all' : ''}`}>{value}</p>
    </div>
  );
}

function BatteryRing({ level }: { level: number | null }) {
  if (level == null) return <div className="text-4xl mx-auto">🔋</div>;
  const color = level > 50 ? '#00B894' : level > 20 ? '#FDCB6E' : '#FF6B6B';
  const c = 2 * Math.PI * 40;
  const offset = c - (level / 100) * c;
  return (
    <svg width="90" height="90" viewBox="0 0 100 100" className="mx-auto">
      <circle cx="50" cy="50" r="40" fill="none" stroke="#F5F5F7" strokeWidth="8" />
      <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset} transform="rotate(-90 50 50)" style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
    </svg>
  );
}

function getTimeAgo(iso: string): string {
  const d = Math.floor((Date.now() - parseUtcTimestamp(iso)) / 1000);
  if (!Number.isFinite(d)) return 'Unknown';
  if (d < 5) return 'Just now';
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}
