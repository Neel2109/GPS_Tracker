import { useEffect, useState, useRef } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { MapPin, Navigation2, ShieldCheck, Smartphone, Watch } from 'lucide-react';
import { deviceAPI, getAccessToken } from '../services/api';
import { wsService } from '../services/websocket';

export default function MobileTracker() {
  const [isTracking, setIsTracking] = useState(false);
  const [status, setStatus] = useState('Standby');
  const [deviceToken, setDeviceToken] = useState(localStorage.getItem('android_device_token'));
  const [deviceId, setDeviceId] = useState(localStorage.getItem('android_device_id'));
  const [deviceName, setDeviceName] = useState('My Android Phone');
  
  const watchIdRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const startTracking = async () => {
    if (!deviceToken || !deviceId) {
      // Register device first
      try {
        setStatus('Registering device...');
        const codeRes = await deviceAPI.generatePairingCode(deviceName, 'android');
        
        // In a real app we'd use the pairing code on the dashboard to authenticate.
        // For this PWA demo, we assume the backend has an endpoint or we pair automatically if logged in.
        // Let's prompt user to enter a pairing code from the dashboard, OR since this is a PWA
        // running in the same browser, we can just use the Dashboard's pairing flow.
        alert(`Your pairing code is: ${codeRes.code}. Enter this on the Dashboard to link this device.`);
        setStatus('Waiting for pairing...');
        return;
      } catch (err) {
        setStatus('Failed to register');
        return;
      }
    }

    setStatus('Connecting...');
    const WS_BASE = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
    const ws = new WebSocket(`${WS_BASE}/ws/device/${deviceId}?token=${deviceToken}`);
    
    ws.onopen = () => {
      setStatus('Connected & Tracking');
      setIsTracking(true);
      
      // Start GPS
      if ('geolocation' in navigator) {
        watchIdRef.current = navigator.geolocation.watchPosition(
          (pos) => {
            const loc = {
              type: 'LOCATION_UPDATE',
              data: {
                latitude: pos.coords.latitude,
                longitude: pos.coords.longitude,
                accuracy: pos.coords.accuracy,
                altitude: pos.coords.altitude,
                speed: pos.coords.speed, // m/s
                heading: pos.coords.heading,
                source: 'android_web'
              }
            };
            ws.send(JSON.stringify(loc));
          },
          (err) => console.error(err),
          { enableHighAccuracy: true, maximumAge: 0, timeout: 5000 }
        );
      }
    };

    ws.onclose = () => {
      setStatus('Disconnected');
      setIsTracking(false);
      if (watchIdRef.current) navigator.geolocation.clearWatch(watchIdRef.current);
    };

    wsRef.current = ws;
  };

  const stopTracking = () => {
    if (wsRef.current) wsRef.current.close();
    if (watchIdRef.current) navigator.geolocation.clearWatch(watchIdRef.current);
    setIsTracking(false);
    setStatus('Standby');
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0d0e15] p-6 text-white">
      <div className="w-full max-w-sm rounded-3xl bg-[#1a1b26] p-8 shadow-2xl ring-1 ring-white/10 text-center">
        <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-blue-500/20 text-blue-400">
          <Navigation2 size={40} className={isTracking ? 'animate-pulse' : ''} />
        </div>
        
        <h1 className="text-2xl font-bold tracking-tight">TrackGuard Mobile</h1>
        <p className="mt-2 text-sm text-gray-400">Turn this device into a GPS tracker</p>
        
        <div className="mt-8 rounded-xl bg-black/40 p-4">
          <p className="text-xs uppercase tracking-widest text-gray-500">Status</p>
          <p className={`mt-1 font-semibold ${isTracking ? 'text-green-400' : 'text-gray-300'}`}>{status}</p>
        </div>

        {!deviceToken && (
          <div className="mt-6 text-left">
            <label className="text-xs text-gray-400 uppercase">Device Name</label>
            <input 
              value={deviceName}
              onChange={e => setDeviceName(e.target.value)}
              className="mt-1 w-full rounded-lg bg-black/30 p-3 text-sm text-white ring-1 ring-white/10 outline-none focus:ring-blue-500"
            />
          </div>
        )}

        <button
          onClick={isTracking ? stopTracking : startTracking}
          className={`mt-8 w-full rounded-xl py-4 font-bold shadow-lg transition-all active:scale-95 ${
            isTracking 
              ? 'bg-red-500/20 text-red-500 ring-1 ring-red-500/50 hover:bg-red-500/30'
              : 'bg-blue-600 text-white hover:bg-blue-500'
          }`}
        >
          {isTracking ? 'Stop Tracking' : 'Start Tracking'}
        </button>

        <p className="mt-6 text-xs text-gray-500">
          Add this page to your home screen to use it as a standalone app.
        </p>
      </div>
    </div>
  );
}
