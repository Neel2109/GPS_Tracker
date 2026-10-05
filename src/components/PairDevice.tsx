import { useCallback, useEffect, useRef, useState } from 'react';
import type { DeviceInstaller, DeviceType } from '../types';
import { DEVICE_TYPE_LABELS } from '../types';
import { deviceAPI } from '../services/api';

interface Props { onClose: () => void; onPaired: () => void; }
type PairingStatus = 'ready' | 'connected' | 'expired';

function parseUtcDate(value: string): number {
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`).getTime();
}

export default function PairDevice({ onClose, onPaired }: Props) {
  const [step, setStep] = useState<'form' | 'installer'>('form');
  const [name, setName] = useState('');
  const [type, setType] = useState<DeviceType>('laptop');
  const [installer, setInstaller] = useState<DeviceInstaller | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [pairingStatus, setPairingStatus] = useState<PairingStatus>('ready');
  const existingDeviceIds = useRef<Set<string>>(new Set());
  const generatedAt = useRef(0);
  const [serverUrl, setServerUrl] = useState(`${window.location.protocol}//${window.location.hostname}:8000`);
  const serverAddress = serverUrl.trim().replace(/\/+$/, '');
  const serverAddressIsValid = /^https?:\/\/[^/\s]+(?::\d+)?$/i.test(serverAddress);
  const formattedCountdown = `${Math.floor(countdown / 3600)}:${Math.floor((countdown % 3600) / 60).toString().padStart(2, '0')}:${(countdown % 60).toString().padStart(2, '0')}`;
  const types: DeviceType[] = ['laptop', 'desktop'];

  const checkForConnection = useCallback(async () => {
    if (!installer || pairingStatus !== 'ready') return;
    try {
      const devices = await deviceAPI.list();
      const connectedDevice = devices.find(device =>
        !existingDeviceIds.current.has(device.id)
        && device.name === installer.device_name
        && device.device_type === type
        && device.status === 'online'
        && parseUtcDate(device.created_at) >= generatedAt.current - 5000,
      );
      if (connectedDevice) {
        setPairingStatus('connected');
        onPaired();
      }
    } catch (requestError) {
      console.error('Could not check device installer status:', requestError);
    }
  }, [installer, onPaired, pairingStatus, type]);

  useEffect(() => {
    if (step !== 'installer' || !installer) return;
    const expiresAt = parseUtcDate(installer.expires_at);
    const updateCountdown = () => {
      const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
      setCountdown(remaining);
      if (remaining === 0) setPairingStatus(status => status === 'connected' ? status : 'expired');
    };
    updateCountdown();
    const timer = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(timer);
  }, [installer, step]);

  useEffect(() => {
    if (step !== 'installer' || !installer || pairingStatus !== 'ready') return;
    void checkForConnection();
    const interval = window.setInterval(() => { void checkForConnection(); }, 2500);
    return () => window.clearInterval(interval);
  }, [checkForConnection, installer, pairingStatus, step]);

  const createInstaller = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const existingDevices = await deviceAPI.list();
      existingDeviceIds.current = new Set(existingDevices.map(device => device.id));
      generatedAt.current = Date.now();
      const packageInfo = await deviceAPI.createInstaller(name.trim(), type, serverAddress);
      setInstaller(packageInfo);
      setPairingStatus('ready');
      setDownloaded(false);
      setCountdown(Math.max(0, Math.floor((parseUtcDate(packageInfo.expires_at) - Date.now()) / 1000)));
      setStep('installer');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not create the device installer.');
    } finally {
      setLoading(false);
    }
  };

  const downloadInstaller = () => {
    if (!installer) return;
    try {
      const binary = window.atob(installer.content_base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = installer.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDownloaded(true);
    } catch (downloadError) {
      console.error('Could not download TrackGuard installer:', downloadError);
      setError('The installer download failed. Please try again.');
    }
  };

  const regenerateInstaller = async () => {
    setLoading(true);
    setError('');
    try {
      const devices = await deviceAPI.list();
      existingDeviceIds.current = new Set(devices.map(device => device.id));
      generatedAt.current = Date.now();
      const packageInfo = await deviceAPI.createInstaller(name.trim(), type, serverAddress);
      setInstaller(packageInfo);
      setPairingStatus('ready');
      setDownloaded(false);
      setCountdown(Math.max(0, Math.floor((parseUtcDate(packageInfo.expires_at) - Date.now()) / 1000)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not create the installer.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 modal-overlay z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="tg-card !w-full !max-w-[410px] !rounded-[18px] !p-6 animate-scale"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.12)' }}
        onClick={event => event.stopPropagation()}
      >
        {step === 'form' ? (
          <>
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#f0edff] text-primary">
              <DeviceGlyph type={type} />
            </div>
            <h3 className="text-center text-xl font-semibold text-text mb-1">Add a device</h3>
            <p className="text-center text-sm text-text-muted mb-5">
              Create a one-time graphical installer. The device IP will appear automatically after it connects.
            </p>

            {error && <div role="alert" className="tg-error mb-4">{error}</div>}

            <form onSubmit={createInstaller} className="space-y-4">
              <div>
                <label htmlFor="device-name" className="tg-label">Device name</label>
                <input
                  id="device-name"
                  value={name}
                  onChange={event => setName(event.target.value)}
                  required
                  maxLength={100}
                  className="tg-input"
                  placeholder="e.g. Neel's Laptop"
                />
              </div>

              <div>
                <label className="tg-label">Device type</label>
                <div className="grid grid-cols-2 gap-2">
                  {types.map(deviceType => (
                    <button
                      key={deviceType}
                      type="button"
                      onClick={() => setType(deviceType)}
                      aria-pressed={type === deviceType}
                      className={`rounded-lg border py-2 text-xs font-medium transition-all ${type === deviceType ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border bg-bg text-text-muted hover:text-text-secondary'}`}
                    >
                      {DEVICE_TYPE_LABELS[deviceType]}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="agent-server-url" className="tg-label">TrackGuard server IP / address</label>
                <input
                  id="agent-server-url"
                  value={serverUrl}
                  onChange={event => setServerUrl(event.target.value)}
                  className={`tg-input !py-2.5 !text-xs ${serverAddressIsValid ? '' : '!border-[#e17878]'}`}
                  placeholder="http://192.168.1.10:8000"
                  spellCheck={false}
                  required
                />
                <p className="mt-1.5 text-[10px] leading-4 text-[#898b91]">
                  Enter the address of the computer running TrackGuard. A remote device needs a publicly reachable server address.
                </p>
              </div>

              <div className="rounded-xl border border-[#e7e2fa] bg-[#f7f5ff] px-3 py-2.5 text-left">
                <p className="text-[11px] font-semibold text-[#55469c]">No terminal or code entry</p>
                <p className="mt-0.5 text-[10px] leading-4 text-[#77718f]">
                    Download the Windows app, open it on the device, and click Install and connect.
                </p>
              </div>

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={onClose} className="tg-btn tg-btn-outline flex-1 justify-center">Cancel</button>
                <button
                  type="submit"
                  disabled={loading || !name.trim() || !serverAddressIsValid}
                  className="tg-btn tg-btn-primary flex-1 justify-center"
                >
                  {loading ? 'Creating installer…' : 'Create installer'}
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="text-center">
            <div className={`mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full ${pairingStatus === 'connected' ? 'bg-[#e5f7ec] text-[#39814d]' : pairingStatus === 'expired' ? 'bg-[#fff0f0] text-[#bd4545]' : 'bg-[#f0edff] text-primary'}`}>
              {pairingStatus === 'connected' ? <CheckIcon /> : <DeviceGlyph type={type} />}
            </div>
            <h3 className="text-xl font-semibold text-text mb-1">
              {pairingStatus === 'connected' ? 'Device connected' : pairingStatus === 'expired' ? 'Installer expired' : 'Install on your device'}
            </h3>
            <p className="text-sm text-text-muted mb-4">
              {pairingStatus === 'connected'
                ? `${installer?.device_name} is online. Find it using its IP in the dashboard.`
                : pairingStatus === 'expired'
                  ? 'For security, this installer can no longer be used. Create a new one.'
                  : <>Setup package for <span className="font-medium text-text">{installer?.device_name}</span></>}
            </p>

            <div className="mb-4 flex items-center justify-center gap-2 text-xs">
              <span className={`h-2 w-2 rounded-full ${pairingStatus === 'connected' ? 'bg-[#4caa65]' : pairingStatus === 'expired' ? 'bg-[#dc6262]' : 'animate-pulse bg-[#d9a82e]'}`} />
              <span className={pairingStatus === 'connected' ? 'font-medium text-[#39814d]' : pairingStatus === 'expired' ? 'font-medium text-[#bd4545]' : 'text-text-secondary'}>
                {pairingStatus === 'connected' ? 'Agent connected securely'
                  : pairingStatus === 'expired' ? 'Download expired'
                    : <>Waiting for installation · expires in <span className="font-mono font-semibold">{formattedCountdown}</span></>}
              </span>
            </div>

            {pairingStatus === 'ready' && (
              <div className="mb-4 space-y-2 rounded-xl border border-[#e4e4e7] bg-[#f7f7f8] p-3 text-left text-[11px] leading-5 text-[#777981]">
                <p><strong className="text-[#55565e]">1.</strong> Transfer the downloaded EXE to {installer?.device_name}.</p>
                <p><strong className="text-[#55565e]">2.</strong> Double-click the EXE and choose <strong>Install and connect</strong>.</p>
                <p><strong className="text-[#55565e]">3.</strong> The bundled agent runs in the background and starts when you sign in. No Python installation is needed.</p>
                <p className="border-t border-[#e4e4e7] pt-2 text-[10px] leading-4">
                  Keep the EXE private: it contains a one-use enrollment credential and expires in 24 hours. The address above is the TrackGuard server address, not the tracked device's IP.
                </p>
              </div>
            )}

            {pairingStatus === 'ready' && downloaded && (
              <p role="status" className="mb-3 text-xs text-[#5c785e]">
                Installer downloaded. Keep this window open; it will detect the agent and show the device IP in your list.
              </p>
            )}
            {error && <p role="alert" className="mb-3 text-left text-xs text-[#b14f4f]">{error}</p>}

            <div className="flex gap-2">
              {pairingStatus === 'ready' && (
                <button onClick={downloadInstaller} className="tg-btn tg-btn-primary flex-1 justify-center">
                  {downloaded ? 'Download EXE again' : 'Download Windows EXE'}
                </button>
              )}
              {pairingStatus === 'expired' && (
                <button onClick={() => void regenerateInstaller()} disabled={loading} className="tg-btn tg-btn-primary flex-1 justify-center">
                  {loading ? 'Creating…' : 'Create a new installer'}
                </button>
              )}
              <button onClick={onClose} className="tg-btn tg-btn-outline flex-1 justify-center">
                {pairingStatus === 'connected' || pairingStatus === 'expired' ? 'Done' : 'Close'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DeviceGlyph({ type }: { type: DeviceType }) {
  const glyph = type === 'laptop' ? '💻'
    : type === 'desktop' ? '🖥️'
      : type === 'smartwatch' ? '⌚'
        : type === 'other' ? '📟' : '📱';
  return <span aria-hidden="true" className="text-lg">{glyph}</span>;
}

function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}
