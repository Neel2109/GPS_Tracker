import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Device, DeviceType } from '../types';
import { DEVICE_TYPE_LABELS } from '../types';
import { deviceAPI } from '../services/api';

interface Props { onClose: () => void; onPaired: () => void; }

function parseUtcDate(value: string): number {
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`).getTime();
}

export default function PairDevice({ onClose, onPaired }: Props) {
  const [step, setStep] = useState<'form' | 'waiting'>('form');
  const [name, setName] = useState('');
  const [type, setType] = useState<DeviceType>('laptop');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const existingDeviceIds = useRef<Set<string>>(new Set());
  const generatedAt = useRef(0);
  const onPairedRef = useRef(onPaired);
  const types: DeviceType[] = ['laptop', 'desktop'];

  useEffect(() => {
    onPairedRef.current = onPaired;
  }, [onPaired]);

  const checkForConnection = useCallback(async (): Promise<Device | null> => {
    try {
      const devices = await deviceAPI.list();
      return devices.find(device =>
        !existingDeviceIds.current.has(device.id)
        && device.name === name.trim()
        && device.device_type === type
        && device.status === 'online'
        && parseUtcDate(device.created_at) >= generatedAt.current - 5000,
      ) ?? null;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not check for the device connection.');
      return null;
    }
  }, [name, type]);

  useEffect(() => {
    if (step !== 'waiting') return;
    let checking = false;
    const check = async () => {
      if (checking) return;
      checking = true;
      const connectedDevice = await checkForConnection();
      checking = false;
      if (connectedDevice) {
        onPairedRef.current();
        onClose();
      }
    };
    void check();
    const interval = window.setInterval(() => { void check(); }, 2500);
    return () => window.clearInterval(interval);
  }, [checkForConnection, onClose, step]);

  const beginPairing = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const existingDevices = await deviceAPI.list();
      existingDeviceIds.current = new Set(existingDevices.map(device => device.id));
      generatedAt.current = Date.now();
      setStep('waiting');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not start device pairing.');
    } finally {
      setLoading(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 modal-overlay flex items-start justify-center overflow-y-auto p-4 sm:items-center sm:py-6"
      style={{ zIndex: 2000 }}
      onClick={onClose}
    >
      <div
        className="tg-card my-auto !w-full !max-w-[440px] !max-h-[calc(100dvh-3rem)] !overflow-y-auto !rounded-xl !p-5 sm:!p-6 animate-scale"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.12)' }}
        onClick={event => event.stopPropagation()}
      >
        {step === 'form' ? (
          <>
            <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-[#e9f3ee] text-[#28714d]">
              <DeviceGlyph type={type} />
            </div>
            <h3 className="mb-2 text-center text-xl font-semibold text-text">Add a device</h3>
            <p className="mx-auto mb-5 max-w-sm text-center text-sm leading-5 text-text-muted">
              Open the TrackGuard app already installed on the device. It pairs after you enter the PIN and connects.
            </p>

            {error && <div role="alert" className="tg-error mb-4">{error}</div>}

            <form onSubmit={beginPairing} className="space-y-4">
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

              <div className="rounded-lg border border-[#d9e8df] bg-[#f3f8f5] px-3.5 py-3 text-left">
                <p className="text-xs font-semibold text-[#315c45]">Use the installed app</p>
                <p className="mt-1 text-xs leading-5 text-[#61756a]">
                  No download is created here. Enter the owner PIN in the device app; configure its server address there if needed.
                </p>
              </div>

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={onClose} className="tg-btn tg-btn-outline min-h-11 flex-1 justify-center">Cancel</button>
                <button
                  type="submit"
                  disabled={loading || !name.trim()}
                  className="tg-btn tg-btn-primary min-h-11 flex-1 justify-center"
                >
                  {loading ? 'Connecting…' : 'Start pairing'}
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-[#e9f3ee] text-[#28714d]">
              <DeviceGlyph type={type} />
            </div>
            <h3 className="mb-2 text-xl font-semibold text-text">Waiting for the app</h3>
            <p className="mx-auto mb-5 max-w-sm text-sm leading-5 text-text-muted">
              Open TrackGuard on <span className="font-medium text-text">{name.trim()}</span>, enter the owner PIN, and start pairing. The app must already be configured to reach this server.
            </p>

            <div className="mb-4 rounded-lg border border-[#e4e4e7] bg-[#f7f7f8] p-3 text-left">
              <p className="text-xs font-semibold text-[#55565e]">Waiting for {name.trim()}</p>
              <p className="mt-1 text-xs leading-5 text-[#696b70]">Pairing completes only after the installed app authenticates with the PIN and its agent connects online.</p>
            </div>
            {error && <p role="alert" className="mb-3 text-left text-xs text-[#b14f4f]">{error}</p>}

            <div className="flex gap-3">
              <button type="button" onClick={() => setStep('form')} className="tg-btn tg-btn-outline min-h-11 flex-1 justify-center">Back</button>
              <button type="button" onClick={onClose} className="tg-btn tg-btn-primary min-h-11 flex-1 justify-center">Close</button>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
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
