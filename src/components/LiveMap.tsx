import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { renderToString } from 'react-dom/server';
import { Laptop, Smartphone, Watch, Car, Bike, User, MapPin, Tablet } from 'lucide-react';
import type { Device, Location } from '../types';
import { formatAccuracy, formatCoordinate, getLocationSourceLabel } from '../utils/location';
import { locationAPI } from '../services/api';

interface Props {
  devices: Device[];
  selectedDeviceId?: string | null;
  onDeviceClick?: (deviceId: string) => void;
  className?: string;
  showAccuracy?: boolean;
  height?: string;
}

const getDeviceIcon = (device: Device, size = 18) => {
  const isMoving = device.last_longitude && (device as any).movement_state && (device as any).movement_state !== 'STATIONARY';

  if (isMoving) {
    const state = (device as any).movement_state;
    if (state === 'DRIVING') return <Car size={size} />;
    if (state === 'CYCLING') return <Bike size={size} />;
    if (state === 'WALKING') return <User size={size} />;
    return <Car size={size} />; // Default moving
  }

  switch (device.device_type) {
    case 'laptop':
    case 'desktop': return <Laptop size={size} />;
    case 'iphone':
    case 'android': return <Smartphone size={size} />;
    case 'smartwatch': return <Watch size={size} />;
    case 'tablet':
    case 'ipad': return <Tablet size={size} />;
    default: return <MapPin size={size} />;
  }
};

function createMarkerIcon(device: Device, isSelected: boolean) {
  const color = device.status === 'online' ? '#00B894' : device.status === 'sleeping' ? '#6C5CE7' : '#B2BEC3';
  const size = isSelected ? 36 : 30;

  const isMoving = (device as any).movement_state && (device as any).movement_state !== 'STATIONARY';
  const heading = (device as any).last_heading || 0;

  const iconHtml = renderToString(
    <div style={{
      width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: 'white'
    }}>
      {getDeviceIcon(device, isSelected ? 20 : 16)}
    </div>
  );

  return L.divIcon({
    className: 'device-marker',
    html: `
      <div style="
        width:${size}px;
        height:${size}px;
        background:${color};
        border-radius:${isMoving ? '8px' : '50%'};
        border:2px solid #fff;
        box-shadow:0 4px 12px ${color}80;
        display:flex;
        align-items:center;
        justify-content:center;
        transform: rotate(${isMoving ? heading : 0}deg);
        transition: transform 0.3s ease;
      ">
        ${iconHtml}
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

export default function LiveMap({ devices, selectedDeviceId, onDeviceClick, className = '', showAccuracy = true, height = '400px' }: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());
  const circlesRef = useRef<Map<string, L.Circle>>(new Map());
  const polylinesRef = useRef<Map<string, L.Polyline>>(new Map());
  const containerRef = useRef<HTMLDivElement>(null);

  const [historyPoints, setHistoryPoints] = useState<Record<string, Location[]>>({});

  // Fetch history for routing
  useEffect(() => {
    devices.forEach(d => {
      locationAPI.getHistory(d.id, { period: 'today', limit: 200 }).then(pts => {
        setHistoryPoints(prev => ({ ...prev, [d.id]: pts }));
      }).catch(console.error);
    });
  }, [devices.length]); // Refresh history if devices change length

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [23.0225, 72.5714],
      zoom: 13,
      zoomControl: true,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map);

    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const activeIds = new Set<string>();

    devices.forEach(device => {
      if (device.last_latitude == null || device.last_longitude == null) return;
      activeIds.add(device.id);
      const pos: L.LatLngExpression = [device.last_latitude, device.last_longitude];
      const isSelected = device.id === selectedDeviceId;
      const icon = createMarkerIcon(device, isSelected);

      let marker = markersRef.current.get(device.id);
      if (marker) {
        marker.setLatLng(pos);
        marker.setIcon(icon);
      } else {
        marker = L.marker(pos, { icon }).addTo(map);
        marker.on('click', () => onDeviceClick?.(device.id));
        markersRef.current.set(device.id, marker);
      }

      marker.bindPopup(`
        <div style="font-family:'Inter',sans-serif;min-width:180px;">
          <div style="font-weight:600;font-size:14px;margin-bottom:6px;color:#1A1A2E;">${device.name}</div>
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
            <span style="width:7px;height:7px;border-radius:50%;background:${device.status === 'online' ? '#00B894' : '#B2BEC3'};display:inline-block;"></span>
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:#636E72;">${device.status}</span>
          </div>
          <div style="font-size:12px;color:#636E72;line-height:1.7;">
            ${formatCoordinate(device.last_latitude, 'latitude')}, ${formatCoordinate(device.last_longitude, 'longitude')}<br/>
            Accuracy: ${formatAccuracy(device.last_accuracy)}<br/>
            ${device.battery_level != null ? `Battery: ${device.battery_level}%` : ''}
          </div>
        </div>
      `);

      // Route Polyline
      const pts = historyPoints[device.id] || [];
      const latlngs: L.LatLngExpression[] = pts.map(p => [p.latitude, p.longitude]);
      latlngs.push(pos); // include current live position

      let polyline = polylinesRef.current.get(device.id);
      if (polyline) {
        polyline.setLatLngs(latlngs);
      } else {
        polyline = L.polyline(latlngs, {
          color: device.status === 'online' ? '#00B894' : '#6C5CE7',
          weight: 4,
          opacity: 0.6,
          dashArray: '8, 8',
          lineCap: 'round',
          lineJoin: 'round'
        }).addTo(map);
        polylinesRef.current.set(device.id, polyline);
      }

    });

    // Cleanup stale markers/polylines
    markersRef.current.forEach((marker, id) => {
      if (!activeIds.has(id)) { marker.remove(); markersRef.current.delete(id); }
    });
    polylinesRef.current.forEach((line, id) => {
      if (!activeIds.has(id)) { line.remove(); polylinesRef.current.delete(id); }
    });

    // Auto-fit or follow
    if (selectedDeviceId) {
      const sel = devices.find(d => d.id === selectedDeviceId);
      if (sel?.last_latitude != null && sel?.last_longitude != null) {
        map.setView([sel.last_latitude, sel.last_longitude], 16, { animate: true });
      }
    }
  }, [devices, selectedDeviceId, showAccuracy, onDeviceClick, historyPoints]);

  return (
    <div
      ref={containerRef}
      className={`rounded-2xl overflow-hidden ${className}`}
      style={{ height, width: '100%' }}
    />
  );
}
