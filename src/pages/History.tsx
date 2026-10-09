import { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import type { Device, Location, Trip } from '../types';
import { deviceAPI, locationAPI, tripAPI } from '../services/api';
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
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedTripId, setSelectedTripId] = useState('');
  const [replayIndex, setReplayIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const polyRef = useRef<L.Polyline | null>(null);
  const pointsRef = useRef<L.CircleMarker[]>([]);
  const replayMarkerRef = useRef<L.CircleMarker | null>(null);

  useEffect(() => { deviceAPI.list().then(l => { setDevices(l); if (l.length && !selectedDevice) setSelectedDevice(l[0].id); }); }, []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { center: [23.0225, 72.5714], zoom: 13, zoomControl: true, attributionControl: false });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    if (!selectedDevice) {
      setTrips([]);
      return;
    }
    tripAPI.list(selectedDevice, period)
      .then(items => setTrips(items))
      .catch(error => setError(error instanceof Error ? error.message : 'Could not load trip summaries.'));
  }, [selectedDevice, period]);

  useEffect(() => {
    if (!selectedDevice) return;
    setLoading(true);
    setError('');
    const request = selectedTripId
      ? tripAPI.getLocations(selectedDevice, selectedTripId, period)
      : locationAPI.getHistory(selectedDevice, { period, limit: 500 });
    request
      .then(locs => { setLocations(locs); setReplayIndex(0); draw(locs); })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load location history.'))
      .finally(() => setLoading(false));
  }, [selectedDevice, period, selectedTripId]);

  useEffect(() => {
    if (!isPlaying || locations.length < 2) return;
    const timer = window.setInterval(() => {
      setReplayIndex(index => {
        if (index >= locations.length - 1) {
          setIsPlaying(false);
          return index;
        }
        return index + 1;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, [isPlaying, locations.length]);

  useEffect(() => {
    const map = mapRef.current;
    const point = locations[replayIndex];
    if (!map || !selectedTripId || !point) {
      replayMarkerRef.current?.remove();
      replayMarkerRef.current = null;
      return;
    }
    if (!replayMarkerRef.current) {
      replayMarkerRef.current = L.circleMarker([point.latitude, point.longitude], {
        radius: 9,
        fillColor: '#d4ff3f',
        fillOpacity: 1,
        color: '#111827',
        weight: 3,
      }).addTo(map);
    } else {
      replayMarkerRef.current.setLatLng([point.latitude, point.longitude]);
    }
  }, [locations, replayIndex, selectedTripId]);

  function draw(locs: Location[]) {
    const map = mapRef.current;
    if (!map) return;
    polyRef.current?.remove();
    pointsRef.current.forEach(m => m.remove());
    replayMarkerRef.current?.remove();
    replayMarkerRef.current = null;
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
        <p className="text-sm text-text-secondary mt-0.5">Review recorded points, detected trip segments, and replay a route</p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1">
          <label className="tg-label">Device</label>
          <select value={selectedDevice} onChange={e => {
            setIsPlaying(false);
            setSelectedTripId('');
            setSelectedDevice(e.target.value);
          }}
            className="tg-input !py-3 appearance-none cursor-pointer">
            <option value="">Select device...</option>
            {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label className="tg-label">Period</label>
          <div className="flex gap-2">
            {PERIODS.map(p => (
              <button key={p.value} onClick={() => {
                setIsPlaying(false);
                setSelectedTripId('');
                setPeriod(p.value);
              }}
                className={`px-4 py-3 rounded-xl text-xs font-medium transition-all border ${period === p.value ? 'bg-primary/10 text-primary border-primary/30' : 'bg-surface border-border text-text-muted hover:text-text-secondary'}`}>
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <section className="tg-card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-text">Detected trips</h2>
            <p className="mt-1 text-xs text-text-muted">Trips split at reporting gaps over 30 minutes. Stops are estimated from reported stationary samples lasting at least 5 minutes; active time excludes those periods.</p>
          </div>
          <span className="text-xs text-text-muted">{trips.length} segments</span>
        </div>
        {trips.length === 0 ? <p className="py-3 text-sm text-text-muted">No multi-point trip segments in this period.</p> : (
          <div className="grid gap-2 md:grid-cols-2">
            {trips.map((trip, index) => (
              <button
                key={trip.id}
                type="button"
                onClick={() => {
                  setIsPlaying(false);
                  setReplayIndex(0);
                  setSelectedTripId(current => current === trip.id ? '' : trip.id);
                }}
                className={`rounded-xl border p-3 text-left transition-colors ${selectedTripId === trip.id ? 'border-primary/40 bg-primary/5' : 'border-border bg-bg hover:border-primary/20'}`}
              >
                <span className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-text">Trip {trips.length - index}</span>
                  <span className="text-xs text-text-muted">{trip.point_count} points</span>
                </span>
                <span className="mt-2 block text-xs text-text-secondary">
                  {new Date(trip.start_time).toLocaleString()} — {new Date(trip.end_time).toLocaleTimeString()}
                </span>
                <span className="mt-1 block text-xs text-text-muted">
                  {(trip.distance_meters / 1000).toFixed(2)} km · {formatDuration(trip.duration_seconds)}
                  {' · '}{trip.stop_count ?? 0} stops (5+ min)
                  {' · '}{formatDuration(trip.active_duration_seconds ?? trip.duration_seconds)} active
                </span>
                <span className="mt-1 block text-xs text-text-muted">
                  Avg {trip.average_speed == null ? '—' : `${(trip.average_speed * 3.6).toFixed(1)} km/h`}
                  {' · '}Max {trip.maximum_speed == null ? '—' : `${(trip.maximum_speed * 3.6).toFixed(1)} km/h`}
                </span>
              </button>
            ))}
          </div>
        )}
        {selectedTripId && locations.length > 1 && (
          <div className="mt-4 flex items-center gap-3 border-t border-border pt-3">
            <button type="button" onClick={() => {
              if (replayIndex >= locations.length - 1) setReplayIndex(0);
              setIsPlaying(value => !value);
            }} className="tg-btn tg-btn-primary !px-4 !py-2">
              {isPlaying ? 'Pause replay' : 'Play replay'}
            </button>
            <input aria-label="Route replay position" type="range" min="0" max={locations.length - 1} value={replayIndex} onChange={event => {
              setIsPlaying(false);
              setReplayIndex(Number(event.target.value));
            }} className="min-w-0 flex-1 accent-lime-400" />
            <span className="text-xs text-text-muted">{replayIndex + 1}/{locations.length}</span>
            <button type="button" onClick={() => {
              setIsPlaying(false);
              setSelectedTripId('');
            }} className="text-xs text-text-secondary hover:text-text">Clear trip</button>
          </div>
        )}
      </section>

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

function formatDuration(seconds: number): string {
  const minutes = Math.max(0, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
