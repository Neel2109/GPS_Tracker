import { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import type { Device, Location } from '../types';
import { deviceAPI, locationAPI } from '../services/api';
import { formatAccuracy, formatCoordinate, getLocationSourceLabel } from '../utils/location';

const PERIODS = [
  { label: 'Today', value: 'today' },
  { label: 'Yesterday', value: 'yesterday' },
  { label: '7 Days', value: '7days' },
  { label: '30 Days', value: '30days' },
];

export default function History() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [period, setPeriod] = useState('today');
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(false);
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const polyRef = useRef<L.Polyline | null>(null);
  const pointsRef = useRef<L.CircleMarker[]>([]);

  useEffect(() => { deviceAPI.list().then(l => { setDevices(l); if (l.length && !selectedDevice) setSelectedDevice(l[0].id); }); }, []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { center: [23.0225, 72.5714], zoom: 13, zoomControl: true, attributionControl: false });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    if (!selectedDevice) return;
    setLoading(true);
    locationAPI.getHistory(selectedDevice, { period, limit: 500 })
      .then(locs => { setLocations(locs); draw(locs); })
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, [selectedDevice, period]);

  function draw(locs: Location[]) {
    const map = mapRef.current;
    if (!map) return;
    polyRef.current?.remove();
    pointsRef.current.forEach(m => m.remove());
    pointsRef.current = [];
    if (!locs.length) return;

    const pts = locs.map(l => [l.latitude, l.longitude] as L.LatLngTuple);
    polyRef.current = L.polyline(pts, { color: '#6C5CE7', weight: 3, opacity: 0.5, dashArray: '8 4' }).addTo(map);

    locs.forEach((loc, i) => {
      const first = i === 0, last = i === locs.length - 1;
      const m = L.circleMarker([loc.latitude, loc.longitude], {
        radius: first || last ? 7 : 3,
        fillColor: first ? '#4C6EF5' : last ? '#6C5CE7' : '#A29BFE',
        fillOpacity: first || last ? 1 : 0.4,
        color: '#fff', weight: first || last ? 2 : 0, opacity: first || last ? 0.8 : 0,
      }).addTo(map);
      m.bindPopup(`<div style="font-family:'Inter',sans-serif;font-size:12px;color:#1A1A2E;min-width:120px;">
        <b>${first ? '🏁 Start' : last ? '📍 Latest' : `#${i + 1}`}</b><br/>
        ${formatCoordinate(loc.latitude, 'latitude')}, ${formatCoordinate(loc.longitude, 'longitude')}<br/>
        ${formatAccuracy(loc.accuracy)} · ${getLocationSourceLabel(loc.source)}<br/>
        ${new Date(loc.timestamp).toLocaleTimeString()}
      </div>`);
      pointsRef.current.push(m);
    });

    map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], animate: true });
  }

  const devName = devices.find(d => d.id === selectedDevice)?.name || 'Device';

  return (
    <div className="space-y-6 animate-in pt-2">
      <div>
        <h1 className="font-display text-2xl font-bold text-text">Location History</h1>
        <p className="text-sm text-text-secondary mt-0.5">View movement history and routes</p>
      </div>

      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1">
          <label className="tg-label">Device</label>
          <select value={selectedDevice} onChange={e => setSelectedDevice(e.target.value)}
            className="tg-input !py-3 appearance-none cursor-pointer">
            <option value="">Select device...</option>
            {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label className="tg-label">Period</label>
          <div className="flex gap-2">
            {PERIODS.map(p => (
              <button key={p.value} onClick={() => setPeriod(p.value)}
                className={`px-4 py-3 rounded-xl text-xs font-medium transition-all border ${period === p.value ? 'bg-primary/10 text-primary border-primary/30' : 'bg-surface border-border text-text-muted hover:text-text-secondary'}`}>
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="tg-card !p-2">
        <div className="flex items-center justify-between px-4 pt-2 pb-1">
          <p className="text-xs font-semibold text-text">{devName} — Route</p>
          <span className="text-xs text-text-muted">{loading ? 'Loading...' : `${locations.length} points`}</span>
        </div>
        <div ref={containerRef} className="rounded-2xl overflow-hidden" style={{ height: '480px', width: '100%' }} />
      </div>

      {locations.length > 0 && (
        <div className="tg-card">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">📍 Points ({locations.length})</h3>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {locations.slice(0, 50).map((loc, i) => (
              <div key={loc.id} className="flex items-center gap-4 py-2 px-3 rounded-lg hover:bg-bg text-sm">
                <span className="text-xs text-text-muted w-6">{i + 1}</span>
                <span className="text-text">{formatCoordinate(loc.latitude, 'latitude')}, {formatCoordinate(loc.longitude, 'longitude')}</span>
                <span className="text-text-muted text-xs">{formatAccuracy(loc.accuracy)}</span>
                <span className="text-text-muted text-xs">{getLocationSourceLabel(loc.source)}</span>
                <span className="text-text-muted text-xs ml-auto">{new Date(loc.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && !locations.length && selectedDevice && (
        <div className="text-center py-12"><span className="text-4xl block mb-3">🗺️</span><p className="text-sm text-text-muted">No location history for this period</p></div>
      )}
    </div>
  );
}
