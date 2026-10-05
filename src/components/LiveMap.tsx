import { useEffect, useRef } from 'react';
import L from 'leaflet';
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

function createMarkerIcon(status: string, isSelected: boolean) {
  const color = status === 'online' ? '#00B894' : status === 'sleeping' ? '#6C5CE7' : '#B2BEC3';
  const size = isSelected ? 16 : 12;
  const pulse = isSelected ? 34 : 26;

  return L.divIcon({
    className: 'device-marker',
    html: `
      <div style="width:${pulse}px;height:${pulse}px;display:flex;align-items:center;justify-content:center;position:relative;">
        ${status === 'online' ? `<div style="width:${pulse}px;height:${pulse}px;border-radius:50%;background:${color}18;position:absolute;animation:marker-ripple 2s ease-out infinite;"></div>` : ''}
        <div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 2px 8px ${color}60;position:relative;z-index:2;"></div>
      </div>
    `,
    iconSize: [pulse, pulse],
    iconAnchor: [pulse / 2, pulse / 2],
    popupAnchor: [0, -pulse / 2],
  });
}

export default function LiveMap({ devices, selectedDeviceId, onDeviceClick, className = '', showAccuracy = true, height = '400px' }: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());
  const circlesRef = useRef<Map<string, L.Circle>>(new Map());
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [23.0225, 72.5714],
      zoom: 13,
      zoomControl: true,
      attributionControl: false,
    });

    // Light, clean map tiles — matching the reference image's map style
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
      const icon = createMarkerIcon(device.status, isSelected);

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
            Source: ${getLocationSourceLabel(device.last_location_source)}<br/>
            ${device.battery_level != null ? `Battery: ${device.battery_level}%` : ''}
          </div>
        </div>
      `);

      if (showAccuracy && device.last_accuracy != null && device.last_accuracy > 0) {
        let circle = circlesRef.current.get(device.id);
        if (circle) {
          circle.setLatLng(pos);
          circle.setRadius(device.last_accuracy);
        } else {
          circle = L.circle(pos, {
            radius: device.last_accuracy,
            fillColor: '#6C5CE7',
            fillOpacity: 0.06,
            color: '#6C5CE7',
            opacity: 0.15,
            weight: 1.5,
          }).addTo(map);
          circlesRef.current.set(device.id, circle);
        }
      } else {
        const circle = circlesRef.current.get(device.id);
        if (circle) {
          circle.remove();
          circlesRef.current.delete(device.id);
        }
      }
    });

    // Remove stale markers/circles
    markersRef.current.forEach((marker, id) => {
      if (!activeIds.has(id)) { marker.remove(); markersRef.current.delete(id); }
    });
    circlesRef.current.forEach((circle, id) => {
      if (!activeIds.has(id)) { circle.remove(); circlesRef.current.delete(id); }
    });

    // Auto-fit
    if (selectedDeviceId) {
      const sel = devices.find(d => d.id === selectedDeviceId);
      if (sel?.last_latitude != null && sel?.last_longitude != null) {
        map.setView([sel.last_latitude, sel.last_longitude], 16, { animate: true });
      }
    } else {
      const valid = devices.filter(d => d.last_latitude != null && d.last_longitude != null);
      if (valid.length === 1) {
        map.setView([valid[0].last_latitude!, valid[0].last_longitude!], 15, { animate: true });
      } else if (valid.length > 1) {
        map.fitBounds(L.latLngBounds(valid.map(d => [d.last_latitude!, d.last_longitude!] as L.LatLngTuple)), { padding: [50, 50], animate: true });
      }
    }
  }, [devices, selectedDeviceId, showAccuracy, onDeviceClick]);

  return (
    <div
      ref={containerRef}
      className={`rounded-2xl overflow-hidden ${className}`}
      style={{ height, width: '100%' }}
    />
  );
}
