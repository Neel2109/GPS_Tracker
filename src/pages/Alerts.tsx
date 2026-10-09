import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, CheckCheck, Siren } from 'lucide-react';
import type { Alert, Device, WSMessage } from '../types';
import { alertAPI, deviceAPI } from '../services/api';
import { wsService } from '../services/websocket';

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceId, setDeviceId] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'UNREAD' | 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'>('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [deviceFilter, setDeviceFilter] = useState('ALL');
  const [sosMessage, setSosMessage] = useState('Emergency assistance requested');
  const [loading, setLoading] = useState(true);
  const [sendingSos, setSendingSos] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      const [alertList, deviceList] = await Promise.all([alertAPI.list(), deviceAPI.list()]);
      setAlerts(alertList);
      setDevices(deviceList);
      setError('');
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load alerts.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    let userId: string | undefined;
    try {
      userId = (JSON.parse(localStorage.getItem('user') || '{}') as { id?: string }).id;
    } catch (parseError) {
      console.error('Could not read TrackGuard account for live alert updates:', parseError);
    }
    if (!userId) return;
    wsService.connect(userId);
    return wsService.onAny((message: WSMessage) => {
      if (message.type === 'ALERT_CREATED' || message.type === 'ALERT_UPDATED') void load();
    });
  }, [load]);

  const sendSos = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!window.confirm('Send an SOS alert to your TrackGuard account? This does not contact emergency services or your emergency contacts.')) return;
    setSendingSos(true);
    setError('');
    setNotice('');
    try {
      await alertAPI.sos(deviceId || undefined, sosMessage.trim());
      setNotice('SOS alert created in TrackGuard.');
      await load();
    } catch (sosError) {
      setError(sosError instanceof Error ? sosError.message : 'Could not create the SOS alert.');
    } finally {
      setSendingSos(false);
    }
  };

  const markRead = async (alert: Alert) => {
    try {
      const updated = await alertAPI.markRead(alert.id);
      setAlerts(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (readError) {
      setError(readError instanceof Error ? readError.message : 'Could not mark alert as read.');
    }
  };

  const markAllRead = async () => {
    try {
      await alertAPI.markAllRead();
      await load();
    } catch (readError) {
      setError(readError instanceof Error ? readError.message : 'Could not mark alerts as read.');
    }
  };

  const updateAlertStatus = async (alert: Alert, status: 'ACKNOWLEDGED' | 'RESOLVED') => {
    try {
      const updated = await alertAPI.updateStatus(alert.id, status);
      setAlerts(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : 'Could not update the incident.');
    }
  };

  const unreadCount = alerts.filter(alert => !alert.read).length;
  const filteredAlerts = alerts.filter(alert => {
    const category = alert.type === 'SOS'
      ? 'SOS'
      : alert.type.startsWith('GEOFENCE')
        ? 'GEOFENCE'
        : ['DEVICE_OFFLINE', 'LOW_BATTERY'].includes(alert.type)
          ? 'DEVICE_HEALTH'
          : 'OTHER';
    return (statusFilter === 'ALL'
      || (statusFilter === 'UNREAD' && !alert.read)
      || alert.status === statusFilter)
      && (typeFilter === 'ALL' || category === typeFilter)
      && (deviceFilter === 'ALL' || alert.device_id === deviceFilter);
  });
  const activeIncidentCount = alerts.filter(alert =>
    alert.status !== 'RESOLVED'
    && ['DEVICE_OFFLINE', 'LOW_BATTERY', 'SOS'].includes(alert.type),
  ).length;

  return (
    <div className="mx-auto max-w-5xl space-y-5 animate-in pt-2">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-bold tracking-[0.18em] text-lime-400">ACTIVITY CENTER</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Incident center</h1>
          <p className="mt-1 text-sm text-slate-400">{activeIncidentCount} active incidents · {unreadCount} unread alerts</p>
        </div>
        <button type="button" onClick={() => void markAllRead()} disabled={!unreadCount} className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-white/5 disabled:opacity-40">
          <CheckCheck size={15} /> Mark all read
        </button>
      </header>

      {error && <p role="alert" className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</p>}
      {notice && <p role="status" className="rounded-xl border border-lime-400/30 bg-lime-400/10 px-4 py-3 text-sm text-lime-200">{notice}</p>}

      <form onSubmit={sendSos} className="grid gap-4 rounded-2xl border border-red-400/20 bg-red-400/[0.06] p-5 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <div>
          <h2 className="flex items-center gap-2 font-semibold text-white"><Siren size={17} className="text-red-300" /> Send an SOS alert</h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">Creates an in-app alert for your account. It does not call emergency services.</p>
        </div>
        <div className="space-y-2">
          <label className="block text-xs text-slate-300">Associated device
            <select value={deviceId} onChange={event => setDeviceId(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white">
              <option value="">Account-wide SOS</option>
              {devices.map(device => <option key={device.id} value={device.id}>{device.name}</option>)}
            </select>
          </label>
          <label className="block text-xs text-slate-300">Message
            <input value={sosMessage} maxLength={500} onChange={event => setSosMessage(event.target.value)} required className="tg-input mt-1 !bg-black/20 !text-white" />
          </label>
        </div>
        <button type="submit" disabled={sendingSos} className="rounded-xl bg-red-400 px-5 py-3 text-sm font-bold text-slate-950 hover:bg-red-300 disabled:opacity-50">
          {sendingSos ? 'Sending…' : 'Confirm SOS'}
        </button>
      </form>

      <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04]">
        <div className="flex flex-wrap gap-2 border-b border-white/10 p-4">
          <label className="text-xs text-slate-400">Status
            <select value={statusFilter} onChange={event => setStatusFilter(event.target.value as typeof statusFilter)} className="tg-input mt-1 !bg-black/20 !text-white">
              <option value="ALL">All alerts</option>
              <option value="UNREAD">Unread only</option>
              <option value="OPEN">Open incidents</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </label>
          <label className="text-xs text-slate-400">Category
            <select value={typeFilter} onChange={event => setTypeFilter(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white">
              <option value="ALL">All categories</option>
              <option value="SOS">SOS</option>
              <option value="GEOFENCE">Geofence</option>
              <option value="DEVICE_HEALTH">Device health</option>
              <option value="OTHER">Other</option>
            </select>
          </label>
          <label className="text-xs text-slate-400">Device
            <select value={deviceFilter} onChange={event => setDeviceFilter(event.target.value)} className="tg-input mt-1 !bg-black/20 !text-white">
              <option value="ALL">All devices</option>
              {devices.map(device => <option key={device.id} value={device.id}>{device.name}</option>)}
            </select>
          </label>
        </div>
        {loading ? <p className="p-6 text-sm text-slate-400">Loading alerts…</p> : filteredAlerts.length === 0
          ? <div className="p-12 text-center"><Bell className="mx-auto text-slate-500" size={28} /><p className="mt-3 text-sm text-slate-300">No alerts yet</p><p className="mt-1 text-xs text-slate-500">Geofence transitions and SOS events will appear here.</p></div>
          : <ul className="divide-y divide-white/[0.07]">
            {filteredAlerts.map(alert => (
              <li key={alert.id} className={`flex flex-wrap items-start gap-3 p-4 ${alert.status === 'OPEN' ? 'bg-white/[0.025]' : ''}`}>
                <span className={`mt-0.5 rounded-xl p-2 ${alert.type === 'SOS' ? 'bg-red-400/10 text-red-300' : alert.type.startsWith('GEOFENCE') ? 'bg-lime-400/10 text-lime-300' : 'bg-sky-400/10 text-sky-300'}`}>
                  {alert.type === 'SOS' ? <Siren size={17} /> : alert.type.startsWith('GEOFENCE') ? <MapPinIcon /> : <AlertTriangle size={17} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-white">{alert.title}</p>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${alert.status === 'OPEN' ? 'bg-amber-300/10 text-amber-200' : alert.status === 'RESOLVED' ? 'bg-slate-300/10 text-slate-300' : 'bg-sky-300/10 text-sky-200'}`}>{alert.status}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-300">{alert.message}</p>
                  <p className="mt-1 text-xs text-slate-500">{new Date(alert.created_at).toLocaleString()}</p>
                  {alert.acknowledged_at && <p className="mt-1 text-xs text-slate-500">Acknowledged {new Date(alert.acknowledged_at).toLocaleString()}</p>}
                  {alert.resolved_at && <p className="mt-1 text-xs text-slate-500">Resolved {new Date(alert.resolved_at).toLocaleString()}</p>}
                </div>
                <div className="flex gap-2">
                  {alert.status === 'OPEN' && <button type="button" onClick={() => void updateAlertStatus(alert, 'ACKNOWLEDGED')} className="rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-white/10">Acknowledge</button>}
                  {alert.status !== 'RESOLVED' && <button type="button" onClick={() => void updateAlertStatus(alert, 'RESOLVED')} className="rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-white/10">Resolve</button>}
                  {!alert.read && <button type="button" onClick={() => void markRead(alert)} className="rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-white/10">Mark read</button>}
                </div>
              </li>
            ))}
          </ul>}
      </section>
    </div>
  );
}

function MapPinIcon() {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg>;
}
