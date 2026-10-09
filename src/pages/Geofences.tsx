import { useCallback, useEffect, useRef, useState } from 'react';
import { CirclePlus, MapPin, Trash2 } from 'lucide-react';
import L from 'leaflet';
import type { Geofence } from '../types';
import { geofenceAPI } from '../services/api';

export default function Geofences() {
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [name, setName] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [radius, setRadius] = useState('200');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const mapElementRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const geofenceLayerRef = useRef<L.FeatureGroup | null>(null);

  const loadGeofences = useCallback(async () => {
    try {
      setGeofences(await geofenceAPI.list());
      setError('');
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load geofences.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadGeofences(); }, [loadGeofences]);

  useEffect(() => {
    if (!mapElementRef.current || mapRef.current) return;
    const map = L.map(mapElementRef.current, { center: [23.0225, 72.5714], zoom: 12 });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    const layer = L.featureGroup().addTo(map);
    map.on('click', event => {
      setLatitude(event.latlng.lat.toFixed(6));
      setLongitude(event.latlng.lng.toFixed(6));
    });
    mapRef.current = map;
    geofenceLayerRef.current = layer;
    return () => {
      map.remove();
      mapRef.current = null;
      geofenceLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = geofenceLayerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    geofences.forEach(geofence => {
      const color = geofence.enabled ? '#84cc16' : '#94a3b8';
      L.circle([geofence.latitude, geofence.longitude], {
        radius: geofence.radius,
        color,
        fillColor: color,
        fillOpacity: 0.14,
        weight: 2,
      }).bindPopup(`${escapeHtml(geofence.name)} · ${Math.round(geofence.radius)} m`).addTo(layer);
      L.circleMarker([geofence.latitude, geofence.longitude], {
        radius: 5,
        color: '#ffffff',
        fillColor: color,
        fillOpacity: 1,
        weight: 2,
      }).addTo(layer);
    });
    if (geofences.length) {
      map.fitBounds(layer.getBounds(), { padding: [30, 30], maxZoom: 15 });
    }
  }, [geofences]);

  const createGeofence = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const created = await geofenceAPI.create({
        name: name.trim(),
        latitude: Number(latitude),
        longitude: Number(longitude),
        radius: Number(radius),
        enabled: true,
      });
      setGeofences(current => [created, ...current]);
      setName('');
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save this geofence.');
    } finally {
      setSaving(false);
    }
  };

  const toggleGeofence = async (geofence: Geofence) => {
    try {
      const updated = await geofenceAPI.update(geofence.id, { enabled: !geofence.enabled });
      setGeofences(current => current.map(item => item.id === updated.id ? updated : item));
      setError('');
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Could not update this geofence.');
    }
  };

  const removeGeofence = async (geofence: Geofence) => {
    if (!window.confirm(`Delete the “${geofence.name}” geofence?`)) return;
    try {
      await geofenceAPI.delete(geofence.id);
      setGeofences(current => current.filter(item => item.id !== geofence.id));
      setError('');
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not delete this geofence.');
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5 animate-in pt-2">
      <header>
        <p className="text-xs font-bold tracking-[0.18em] text-lime-400">SAVED PLACES</p>
        <h1 className="mt-1 text-2xl font-bold text-white">Geofences</h1>
        <p className="mt-1 text-sm text-slate-400">Get an in-app alert when a reporting device crosses a saved boundary.</p>
      </header>

      {error && <p role="alert" className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</p>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.8fr)]">
        <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04]">
          <div ref={mapElementRef} className="h-[430px] w-full" aria-label="Geofence map; click to choose its center" />
          <p className="border-t border-white/10 px-4 py-2 text-xs text-slate-400">Click the map to set a new geofence center. Circles represent the configured radius.</p>
        </section>

        <div className="space-y-5">
          <form onSubmit={createGeofence} className="space-y-3 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <h2 className="flex items-center gap-2 font-semibold text-white"><CirclePlus size={18} /> Create geofence</h2>
            <label className="block text-xs text-slate-300">Place name
              <input required maxLength={80} value={name} onChange={event => setName(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white" placeholder="Home, office, parking..." />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs text-slate-300">Latitude
                <input required type="number" min="-90" max="90" step="any" value={latitude} onChange={event => setLatitude(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white" placeholder="Click map" />
              </label>
              <label className="block text-xs text-slate-300">Longitude
                <input required type="number" min="-180" max="180" step="any" value={longitude} onChange={event => setLongitude(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white" placeholder="Click map" />
              </label>
            </div>
            <label className="block text-xs text-slate-300">Radius (meters)
              <input required type="number" min="1" max="100000" value={radius} onChange={event => setRadius(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white" />
            </label>
            <button disabled={saving} className="w-full rounded-xl bg-lime-400 px-4 py-3 text-sm font-bold text-slate-950 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save geofence'}
            </button>
          </form>

          <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold text-white">Your places</h2>
              <span className="text-xs text-slate-400">{geofences.length}</span>
            </div>
            {loading ? <p className="py-5 text-sm text-slate-400">Loading geofences…</p> : geofences.length === 0
              ? <p className="py-5 text-sm text-slate-400">No places yet. Add one to enable boundary alerts.</p>
              : <ul className="space-y-2">
                {geofences.map(geofence => (
                  <li key={geofence.id} className="flex items-center gap-3 rounded-xl bg-black/20 p-3">
                    <MapPin size={17} className={geofence.enabled ? 'text-lime-400' : 'text-slate-500'} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-white">{geofence.name}</p>
                      <p className="text-xs text-slate-400">{Math.round(geofence.radius)} m radius</p>
                    </div>
                    <button type="button" onClick={() => void toggleGeofence(geofence)} className="text-xs text-slate-300 hover:text-white">
                      {geofence.enabled ? 'Pause' : 'Enable'}
                    </button>
                    <button type="button" onClick={() => void removeGeofence(geofence)} className="rounded-lg p-2 text-red-300 hover:bg-red-400/10" aria-label={`Delete ${geofence.name}`}>
                      <Trash2 size={15} />
                    </button>
                  </li>
                ))}
              </ul>}
          </section>
        </div>
      </div>
      <p className="text-xs leading-5 text-slate-500">Boundary events are evaluated when a paired device uploads a location. Initial position establishes inside/outside state; it does not generate a false entry alert. Alerts are shown in TrackGuard and are not push notifications or emergency-service dispatch.</p>
    </div>
  );
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] ?? character);
}
