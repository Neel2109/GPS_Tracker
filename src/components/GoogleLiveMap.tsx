import { useEffect, useRef, useState } from 'react';
import { Loader } from '@googlemaps/js-api-loader';
import type { Device } from '../types';
import { formatAccuracy, formatCoordinate, getLocationSourceLabel } from '../utils/location';

interface Props {
  devices: Device[];
  selectedDeviceId?: string | null;
  onDeviceClick?: (deviceId: string) => void;
  className?: string;
  showAccuracy?: boolean;
  height?: string;
}

type MapLayer = 'roadmap' | 'satellite' | 'terrain';

const mapLayers: { id: MapLayer; label: string }[] = [
  { id: 'roadmap', label: 'Map' },
  { id: 'satellite', label: 'Satellite' },
  { id: 'terrain', label: 'Terrain' },
];

export default function GoogleLiveMap({
  devices,
  selectedDeviceId,
  onDeviceClick,
  className = '',
  showAccuracy = true,
  height = '400px',
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<Map<string, google.maps.Marker>>(new Map());
  const circlesRef = useRef<Map<string, google.maps.Circle>>(new Map());
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);
  const onDeviceClickRef = useRef(onDeviceClick);
  const [layer, setLayer] = useState<MapLayer>('satellite');
  const [mapReady, setMapReady] = useState(false);
  const [error, setError] = useState('');
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  useEffect(() => {
    onDeviceClickRef.current = onDeviceClick;
  }, [onDeviceClick]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!apiKey) {
      setError('Add VITE_GOOGLE_MAPS_API_KEY to .env to load Google Maps.');
      return;
    }

    let cancelled = false;
    const loader = new Loader({ apiKey, version: 'weekly' });
    loader.importLibrary('maps').then(() => {
      if (cancelled || !containerRef.current) return;
      const map = new google.maps.Map(containerRef.current, {
        center: { lat: 23.0225, lng: 72.5714 },
        zoom: 13,
        mapTypeId: google.maps.MapTypeId.SATELLITE,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false,
        clickableIcons: false,
        gestureHandling: 'greedy',
      });
      mapRef.current = map;
      infoWindowRef.current = new google.maps.InfoWindow();
      setMapReady(true);
      setError('');
    }).catch(() => {
      if (!cancelled) setError('Google Maps could not load. Check the API key and Maps JavaScript API billing settings.');
    });

    return () => {
      cancelled = true;
      markersRef.current.forEach(marker => marker.setMap(null));
      circlesRef.current.forEach(circle => circle.setMap(null));
      markersRef.current.clear();
      circlesRef.current.clear();
      mapRef.current = null;
      infoWindowRef.current = null;
    };
  }, [apiKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    map.setMapTypeId(layer);
    const activeIds = new Set<string>();

    devices.forEach(device => {
      if (device.last_latitude == null || device.last_longitude == null) return;
      activeIds.add(device.id);
      const position = { lat: device.last_latitude, lng: device.last_longitude };
      const selected = device.id === selectedDeviceId;
      const color = device.status === 'online' ? '#58ee5b' : '#a7b4c5';
      let marker = markersRef.current.get(device.id);

      if (!marker) {
        marker = new google.maps.Marker({
          map,
          position,
          title: device.name,
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: selected ? 10 : 7,
            fillColor: color,
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 2,
          },
        });
        marker.addListener('click', () => {
          const current = devices.find(item => item.id === device.id) ?? device;
          const latitude = current.last_latitude ?? position.lat;
          const longitude = current.last_longitude ?? position.lng;
          const details = [
            `${formatCoordinate(latitude, 'latitude')}, ${formatCoordinate(longitude, 'longitude')}`,
            `${formatAccuracy(current.last_accuracy)} · ${getLocationSourceLabel(current.last_location_source)}`,
          ].join('<br>');
          infoWindowRef.current?.setContent(`<strong>${escapeHtml(current.name)}</strong><br>${details}`);
          infoWindowRef.current?.open({ map, anchor: marker });
          onDeviceClickRef.current?.(device.id);
        });
        markersRef.current.set(device.id, marker);
      }

      marker.setPosition(position);
      marker.setIcon({
        path: google.maps.SymbolPath.CIRCLE,
        scale: selected ? 10 : 7,
        fillColor: color,
        fillOpacity: 1,
        strokeColor: '#ffffff',
        strokeWeight: 2,
      });

      if (showAccuracy && device.last_accuracy != null && device.last_accuracy > 0) {
        let circle = circlesRef.current.get(device.id);
        if (!circle) {
          circle = new google.maps.Circle({
            map,
            center: position,
            radius: device.last_accuracy,
            fillColor: '#56ed65',
            fillOpacity: 0.12,
            strokeColor: '#56ed65',
            strokeOpacity: 0.24,
            strokeWeight: 1,
          });
          circlesRef.current.set(device.id, circle);
        } else {
          circle.setCenter(position);
          circle.setRadius(device.last_accuracy);
        }
      } else {
        circlesRef.current.get(device.id)?.setMap(null);
        circlesRef.current.delete(device.id);
      }
    });

    markersRef.current.forEach((marker, id) => {
      if (!activeIds.has(id)) {
        marker.setMap(null);
        markersRef.current.delete(id);
      }
    });
    circlesRef.current.forEach((circle, id) => {
      if (!activeIds.has(id)) {
        circle.setMap(null);
        circlesRef.current.delete(id);
      }
    });

    const selected = devices.find(device => device.id === selectedDeviceId);
    if (selected?.last_latitude != null && selected.last_longitude != null) {
      map.setCenter({ lat: selected.last_latitude, lng: selected.last_longitude });
      map.setZoom(16);
    } else {
      const located = devices.filter(device => device.last_latitude != null && device.last_longitude != null);
      if (located.length === 1) {
        map.setCenter({ lat: located[0].last_latitude!, lng: located[0].last_longitude! });
        map.setZoom(15);
      } else if (located.length > 1) {
        const bounds = new google.maps.LatLngBounds();
        located.forEach(device => bounds.extend({ lat: device.last_latitude!, lng: device.last_longitude! }));
        map.fitBounds(bounds, 48);
      }
    }
  }, [devices, selectedDeviceId, showAccuracy, layer, mapReady]);

  return (
    <div className={`google-map-shell ${className}`} style={{ height, width: '100%' }}>
      <div ref={containerRef} className="google-map-canvas" />
      <div className="google-map-layers" role="group" aria-label="Map layer">
        {mapLayers.map(item => (
          <button
            key={item.id}
            type="button"
            className={layer === item.id ? 'google-map-layer-active' : ''}
            onClick={() => setLayer(item.id)}
            aria-pressed={layer === item.id}
          >
            {item.label}
          </button>
        ))}
      </div>
      {error && <div className="google-map-error" role="status">{error}</div>}
    </div>
  );
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] ?? character);
}