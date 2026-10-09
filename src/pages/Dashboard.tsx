import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { Laptop, MapPin, Monitor, Smartphone, Tablet, Watch, Wifi, WifiOff } from 'lucide-react';
import type { Device, WSMessage } from '../types';
import { commandAPI, deviceAPI } from '../services/api';
import { wsService } from '../services/websocket';
import type { DashboardSearchContext } from '../components/AppLayout';
import LiveMap from '../components/LiveMap';
import PairDevice from '../components/PairDevice';
import { formatAccuracy, formatCoordinate, formatLocationAge, getLocationSourceLabel } from '../utils/location';

export default function Dashboard() {
  const navigate = useNavigate();
  const { searchQuery } = useOutletContext<DashboardSearchContext>();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPairing, setShowPairing] = useState(false);
  const [selectedMapDevice, setSelectedMapDevice] = useState<string | null>(null);
  const [requestingLocation, setRequestingLocation] = useState(false);
  const [locationRequestMessage, setLocationRequestMessage] = useState('');

  const fetchDevices = useCallback(async () => {
    try {
      setDevices(await deviceAPI.list());
    } catch (error) {
      console.error('Failed to fetch devices:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchDevices(); }, [fetchDevices]);
  useEffect(() => {
    const interval = setInterval(() => { void fetchDevices(); }, 5000);
    return () => clearInterval(interval);
  }, [fetchDevices]);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    if (!storedUser) return;
    try {
      const userId = (JSON.parse(storedUser) as { id?: string }).id;
      if (!userId) return;
      wsService.connect(userId);
      return wsService.onAny((message: WSMessage) => {
        if (['DEVICE_ONLINE', 'DEVICE_OFFLINE', 'DEVICE_STATUS', 'LOCATION_UPDATE', 'STATUS_UPDATE', 'BATTERY_UPDATE'].includes(message.type)) {
          void fetchDevices();
        }
      });
    } catch (error) {
      console.error('Could not start live device updates:', error);
    }
  }, [fetchDevices]);

  const filteredDevices = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return devices;
    return devices.filter(device => [
      device.name,
      device.device_type,
      device.platform,
      device.local_ip,
      device.public_ip,
      device.status,
    ].some(value => value?.toLowerCase().includes(query)));
  }, [devices, searchQuery]);

  const devicesWithLocation = filteredDevices.filter(
    device => device.last_latitude != null && device.last_longitude != null,
  );
  const onlineDevices = devices.filter(device => device.status === 'online');
  const activeDevice = filteredDevices.find(device => device.id === selectedMapDevice)
    || filteredDevices.find(device => device.status === 'online')
    || filteredDevices[0];

  const selectDevice = (device: Device) => {
    setSelectedMapDevice(device.id);
  };

  const requestLocation = async () => {
    if (!activeDevice) return;
    setRequestingLocation(true);
    setLocationRequestMessage('');
    try {
      await commandAPI.requestLocation(activeDevice.id);
      setLocationRequestMessage('Request sent. Waiting for the device to report its location.');
    } catch (error) {
      setLocationRequestMessage(error instanceof Error ? error.message : 'Could not request a location update.');
    } finally {
      setRequestingLocation(false);
    }
  };

  if (loading) {
    return (
      <div className="grid h-full min-h-[420px] grid-cols-1 gap-4 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="space-y-4">
          <div className="skeleton h-36" />
          <div className="skeleton h-44" />
          <div className="skeleton h-48" />
        </div>
        <div className="skeleton min-h-[480px]" />
      </div>
    );
  }

  return (
    <div className="tracking-dashboard animate-in">
      <div className="tracking-top-row">
        <section className="tracking-pair-card">
          <div className="relative z-10">
            <span className="tracking-eyebrow">TRACKGUARD · LIVE DEVICES</span>
            <h1 className="mt-2 text-[21px] font-bold tracking-tight">Track, Secure &amp; Control<br />All Your Devices</h1>
            <p className="mt-1 max-w-sm text-[13px] leading-5">
              Monitor live location and device health from anywhere.
            </p>
            <button
              id="btn-add-device"
              onClick={() => setShowPairing(true)}
              className="tracking-pair-action mt-4"
            >
              <span>+ &nbsp; Add Device</span>
              <ArrowIcon />
            </button>
          </div>
          <div className="tracking-pair-orb" aria-hidden="true" />
        </section>

        <section className="tracking-stats" aria-label="Device status summary">
          <Stat icon={<Monitor />} label="Total devices" value={devices.length} detail="Registered devices" tone="cyan" />
          <Stat icon={<Wifi />} label="Online" value={onlineDevices.length} detail={`${devices.length ? Math.round(onlineDevices.length / devices.length * 100) : 0}% of devices`} tone="green" />
          <Stat icon={<WifiOff />} label="Offline" value={devices.length - onlineDevices.length} detail="Not connected" tone="red" />
          <Stat icon={<MapPin />} label="Locations" value={devicesWithLocation.length} detail="Reported positions" tone="lime" />
        </section>
      </div>

      <div className="tracking-overview">
        <section className="tracking-left-column">
          {activeDevice ? (
            <section className="tracking-featured-card" aria-label={`Selected device ${activeDevice.name}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="tracking-device-icon tracking-device-icon-featured">
                    <DeviceIcon type={activeDevice.device_type} />
                  </div>
                  <div className="min-w-0">
                    <p className="tracking-eyebrow text-[#72747b]">SELECTED DEVICE</p>
                    <h2 className="truncate text-[15px] font-bold text-[#202124]">{activeDevice.name}</h2>
                    <div className="mt-1 flex items-center gap-1.5 text-[11px] font-medium text-[#696b70]">
                      <span className={`h-2 w-2 rounded-full ${activeDevice.status === 'online' ? 'bg-[#63a55a]' : 'bg-[#aeb2b8]'}`} />
                      {activeDevice.status.replaceAll('_', ' ')}
                    </div>
                  </div>
                </div>
                <span className={`tracking-status ${activeDevice.status === 'online' ? 'tracking-status-online' : 'tracking-status-offline'}`}>
                  {activeDevice.status === 'online' ? 'Online' : activeDevice.status.replaceAll('_', ' ')}
                </span>
              </div>

              <div className="tracking-device-facts">
                <Fact label="Local IP" value={activeDevice.local_ip || 'Not reported'} mono />
                <Fact label="Public IP" value={activeDevice.public_ip || 'Not reported'} mono />
                <Fact label="Last location" value={activeDevice.last_latitude != null && activeDevice.last_longitude != null
                  ? `${formatCoordinate(activeDevice.last_latitude, 'latitude')} · ${formatCoordinate(activeDevice.last_longitude, 'longitude')}`
                  : 'No location yet'} />
                <Fact label="Accuracy" value={formatAccuracy(activeDevice.last_accuracy)} />
                <Fact label="Source" value={getLocationSourceLabel(activeDevice.last_location_source)} />
                <Fact label="Operating system" value={activeDevice.os_version || activeDevice.platform || 'Not reported'} />
                <Fact label="Memory" value={activeDevice.ram_total || 'Not reported'} />
                <Fact label="Storage" value={activeDevice.storage_total || 'Not reported'} />
              </div>

              {activeDevice.status !== 'online' && (
                <div role="status" className="mb-3 rounded-lg border border-[#d8e1e7] bg-[#f3f6f8] px-3 py-2.5 text-xs leading-5 text-[#596873]">
                  <strong className="text-[#344550]">Last known fix · {formatLocationAge(activeDevice.last_location_time)}</strong>
                  <p>
                    {activeDevice.last_latitude != null && activeDevice.last_longitude != null
                      ? 'This is the last position reported before the device became unreachable. It is not a live trace; new fixes resume when the app reconnects.'
                      : 'The device cannot report a position while unreachable, and no earlier location fix is available.'}
                  </p>
                </div>
              )}

              {locationRequestMessage && <p role="status" className="mb-3 text-xs text-[#5b5b65]">{locationRequestMessage}</p>}
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-black/[0.06] pt-3">
                <span className="text-[11px] text-[#777981]">
                  Updated {formatLocationAge(activeDevice.last_location_time)}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={requestLocation}
                    disabled={requestingLocation || activeDevice.status !== 'online'}
                    className="tracking-secondary-action"
                  >
                    {requestingLocation ? 'Requesting…' : 'Refresh location'}
                  </button>
                  <button onClick={() => navigate(`/devices/${activeDevice.id}`)} className="tracking-primary-action">
                    Device details
                  </button>
                </div>
              </div>
            </section>
          ) : (
            <section className="tracking-empty-card">
              <div className="tracking-empty-icon"><DeviceIcon type="laptop" /></div>
              <h2 className="mt-3 text-base font-semibold text-[#24252b]">
                {devices.length > 0 ? 'No matching devices' : 'No devices paired yet'}
              </h2>
              <p className="mt-1 max-w-xs text-center text-sm text-[#7b7d84]">
                {devices.length > 0
                  ? 'Try another device name or IP address.'
                  : 'Install the agent on a Windows computer to see its location and reported IP here.'}
              </p>
              {devices.length === 0 && (
                <button onClick={() => setShowPairing(true)} className="tracking-primary-action mt-4">
                  Pair your first device
                </button>
              )}
            </section>
          )}

          <section className="tracking-device-list-card">
            <div className="flex items-center justify-between px-4 pb-2 pt-3">
              <div>
                <h2 className="text-[13px] font-bold text-[#24252b]">Your devices</h2>
                <p className="mt-0.5 text-[11px] text-[#85878d]">
                  {searchQuery.trim() ? `${filteredDevices.length} matching` : `${onlineDevices.length} online · ${devices.length} total`}
                </p>
              </div>
              <span className="rounded-full bg-[#f3f1fb] px-2.5 py-1 text-[10px] font-semibold text-[#7965cc]">IP searchable</span>
            </div>
            <div className="tracking-device-list">
              {filteredDevices.map(device => (
                <DeviceListRow
                  key={device.id}
                  device={device}
                  isActive={device.id === activeDevice?.id}
                  onClick={() => selectDevice(device)}
                />
              ))}
              {filteredDevices.length === 0 && devices.length > 0 && (
                <p className="px-4 py-6 text-center text-xs text-[#8b8d93]">No devices match “{searchQuery}”.</p>
              )}
            </div>
          </section>
        </section>

        <section className="tracking-map-panel" aria-label="Device location map">
          <div className="tracking-map-heading">
            <div>
              <p className="tracking-eyebrow text-[#797b81]">
                {activeDevice?.status === 'online' ? 'LIVE MAP' : activeDevice ? 'LAST KNOWN LOCATION' : 'DEVICE MAP'}
              </p>
              <h2 className="mt-1 text-sm font-bold text-[#26272c]">
                {activeDevice ? activeDevice.name : 'Device locations'}
              </h2>
            </div>
            {activeDevice && (
              <span className="tracking-map-age">{formatLocationAge(activeDevice.last_location_time)}</span>
            )}
          </div>
          {devicesWithLocation.length === 0 && (
            <div className="tracking-map-empty">
              <span className="mb-2 text-3xl">📍</span>
              <p className="text-sm font-semibold text-[#53555b]">No reported coordinates yet</p>
              <p className="mt-1 max-w-[230px] text-center text-xs leading-5 text-[#81838a]">
                The map will show a device after its agent sends a location fix.
              </p>
            </div>
          )}
          <LiveMap
            devices={devicesWithLocation}
            selectedDeviceId={activeDevice?.id}
            onDeviceClick={id => {
              const clickedDevice = filteredDevices.find(device => device.id === id);
              if (clickedDevice) selectDevice(clickedDevice);
            }}
            className="tracking-leaflet-map"
            height="100%"
          />
          {activeDevice && devicesWithLocation.some(device => device.id === activeDevice.id) && (
            <div className="tracking-map-location">
              <span className="text-base">📍</span>
              <div className="min-w-0">
                <p className="truncate text-xs font-bold text-[#292a30]">{activeDevice.name}</p>
                <p className="mt-0.5 text-[10px] text-[#777981]">
                  {formatAccuracy(activeDevice.last_accuracy)} · {getLocationSourceLabel(activeDevice.last_location_source)}
                </p>
              </div>
            </div>
          )}
        </section>
      </div>

      {showPairing && (
        <PairDevice
          onClose={() => setShowPairing(false)}
          onPaired={() => { void fetchDevices(); }}
        />
      )}
    </div>
  );
}

function DeviceListRow({ device, isActive, onClick }: {
  device: Device;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`tracking-device-row ${isActive ? 'tracking-device-row-active' : ''}`}
    >
      <div className={`tracking-device-icon ${device.device_type === 'laptop' || device.device_type === 'desktop' ? 'tracking-device-icon-laptop' : 'tracking-device-icon-mobile'}`}>
        <DeviceIcon type={device.device_type} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-[12px] font-bold text-[#303137]">{device.name}</p>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${device.status === 'online' ? 'bg-[#55a365]' : 'bg-[#b8bbc0]'}`} />
        </div>
        <p className="mt-0.5 truncate font-mono text-[10px] text-[#73757d]">
          {device.local_ip ? `LAN ${device.local_ip}` : 'LAN IP pending'}
        </p>
        <p className="mt-0.5 truncate font-mono text-[10px] text-[#9799a0]">
          {device.public_ip ? `Public ${device.public_ip}` : 'Public IP pending'}
        </p>
        <p className="mt-0.5 truncate text-[10px] text-[#9799a0]">
          {device.last_latitude != null && device.last_longitude != null
            ? `${formatCoordinate(device.last_latitude, 'latitude')} · ${formatCoordinate(device.last_longitude, 'longitude')}`
            : 'Location pending'}
        </p>
      </div>
      <span className={`tracking-mini-status ${device.status === 'online' ? 'tracking-mini-status-online' : ''}`}>
        {device.status === 'online' ? 'Online' : 'Offline'}
      </span>
    </button>
  );
}

function Stat({ icon, label, value, detail, tone }: {
  icon: React.ReactNode;
  label: string;
  value: number;
  detail: string;
  tone: string;
}) {
  return (
    <article className={`tracking-stat tracking-stat-${tone}`}>
      <span className="tracking-stat-icon" aria-hidden="true">{icon}</span>
      <p className="tracking-stat-label">{label}</p>
      <p className="tracking-stat-value">{value}</p>
      <p className="tracking-stat-detail">{detail}</p>
    </article>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] font-semibold uppercase tracking-[0.11em] text-[#85868c]">{label}</p>
      <p className={`mt-1 truncate text-[11px] font-semibold text-[#303137] ${mono ? 'font-mono' : ''}`}>{value}</p>
    </div>
  );
}

function DeviceIcon({ type }: { type: Device['device_type'] }) {
  const Icon = type === 'desktop' ? Monitor
    : type === 'android' || type === 'iphone' ? Smartphone
      : type === 'tablet' || type === 'ipad' ? Tablet
        : type === 'smartwatch' ? Watch
          : Laptop;
  return <Icon size={19} strokeWidth={1.8} aria-hidden="true" />;
}

function ArrowIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
    </svg>
  );
}
