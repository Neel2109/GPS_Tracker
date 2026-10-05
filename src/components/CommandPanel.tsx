import { useState } from 'react';
import { LocateFixed, LockKeyhole, Moon, Power, RotateCw, type LucideIcon } from 'lucide-react';
import type { Device } from '../types';
import { commandAPI, deviceAPI } from '../services/api';
import { wsService } from '../services/websocket';
import { useEffect } from 'react';

interface Props { device: Device; onUpdate?: () => void; }

interface CmdDef {
  id: string; label: string; icon: LucideIcon; bg: string; border: string; text: string;
  confirmTitle: string; confirmMsg: string; action: (id: string) => Promise<any>; danger?: boolean;
}

const CMDS: CmdDef[] = [
  { id: 'lock', label: 'Lock', icon: LockKeyhole, bg: '#EDF2FF', border: '#CADCFF', text: '#4C6EF5', confirmTitle: 'Lock Device?', confirmMsg: 'Lock the Windows session immediately.', action: id => commandAPI.lock(id) },
  { id: 'sleep', label: 'Sleep', icon: Moon, bg: '#F0EDFF', border: '#D9D1FF', text: '#6C5CE7', confirmTitle: 'Sleep Device?', confirmMsg: 'Put the device into sleep mode.', action: id => commandAPI.sleep(id) },
  { id: 'restart', label: 'Restart', icon: RotateCw, bg: '#FFF8E6', border: '#FFE6A0', text: '#E67E22', confirmTitle: 'Restart?', confirmMsg: 'Restart the device. Unsaved work may be lost.', action: id => commandAPI.restart(id), danger: true },
  { id: 'shutdown', label: 'Power Off', icon: Power, bg: '#FFF0F0', border: '#FFCACA', text: '#FF6B6B', confirmTitle: 'Shut Down?', confirmMsg: 'Shut down the device. It will go offline.', action: id => commandAPI.shutdown(id), danger: true },
];

export default function CommandPanel({ device, onUpdate }: Props) {
  const [activeConfirm, setActiveConfirm] = useState<string | null>(null);
  const [executing, setExecuting] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  useEffect(() => wsService.on('COMMAND_RESULT', message => {
    if (message.device_id !== device.id) return;
    const commandResult = message as typeof message & { status?: string; result?: string };
    setResult({
      ok: commandResult.status === 'success' || commandResult.status === 'executed',
      msg: commandResult.result || `Command ${commandResult.status || 'completed'}`,
    });
    onUpdate?.();
  }), [device.id, onUpdate]);

  const exec = async (cmd: CmdDef) => {
    setActiveConfirm(null); setExecuting(cmd.id); setResult(null);
    try { await cmd.action(device.id); setResult({ ok: true, msg: `${cmd.label} sent` }); onUpdate?.(); }
    catch (e: any) { setResult({ ok: false, msg: e.message || 'Failed' }); }
    finally { setExecuting(null); setTimeout(() => setResult(null), 3000); }
  };

  const toggleLost = async () => {
    setExecuting('lost');
    try {
      if (device.is_lost_mode) { await deviceAPI.disableLostMode(device.id); setResult({ ok: true, msg: 'Lost Mode off' }); }
      else { await deviceAPI.enableLostMode(device.id); setResult({ ok: true, msg: 'Lost Mode on' }); }
      onUpdate?.();
    } catch (e: any) { setResult({ ok: false, msg: e.message }); }
    finally { setExecuting(null); setTimeout(() => setResult(null), 3000); }
  };

  const offline = device.status === 'offline';

  return (
    <div className="space-y-4">
      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">⚡ Device Control</h3>

      {result && (
        <div className={`px-4 py-3 rounded-xl text-sm font-medium animate-scale ${result.ok ? 'bg-[#E6FAF2] text-accent border border-accent/20' : 'bg-[#FFF0F0] text-lost border border-lost/20'}`}>
          {result.ok ? '✓' : '✕'} {result.msg}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {CMDS.map(cmd => (
          <div key={cmd.id}>
            <button
              id={`cmd-${cmd.id}`}
              disabled={offline || executing !== null}
              onClick={() => setActiveConfirm(cmd.id)}
              className="cmd-btn w-full flex flex-col items-center gap-2 py-5 rounded-xl border disabled:opacity-30 disabled:cursor-not-allowed"
              style={{ background: cmd.bg, borderColor: cmd.border, color: cmd.text }}
            >
              <cmd.icon size={24} strokeWidth={1.8} aria-hidden="true" />
              <span className="text-xs font-semibold uppercase tracking-wider">{cmd.label}</span>
              {executing === cmd.id && <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />}
            </button>

            {activeConfirm === cmd.id && (
              <div className="fixed inset-0 modal-overlay z-50 flex items-center justify-center p-4" onClick={() => setActiveConfirm(null)}>
                <div className="tg-card !rounded-2xl !p-6 max-w-sm w-full animate-scale" style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.12)' }} onClick={e => e.stopPropagation()}>
                  <div className="text-center mb-6">
                    <cmd.icon className="mx-auto mb-3" size={34} strokeWidth={1.7} aria-hidden="true" />
                    <h4 className="text-lg font-semibold text-text mb-2">{cmd.confirmTitle}</h4>
                    <p className="text-sm text-text-secondary">{cmd.confirmMsg}</p>
                    <p className="text-sm text-text font-medium mt-2">{device.name}</p>
                  </div>
                  <div className="flex gap-3">
                    <button onClick={() => setActiveConfirm(null)} className="tg-btn tg-btn-outline flex-1 justify-center">Cancel</button>
                    <button onClick={() => exec(cmd)} className="tg-btn flex-1 justify-center" style={{ background: cmd.danger ? '#FF6B6B' : '#1A1A1A', color: '#fff' }}>{cmd.label}</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <button id="cmd-lost-mode" disabled={executing !== null} onClick={toggleLost}
        className={`w-full py-4 rounded-xl border text-sm font-semibold uppercase tracking-wider transition-all cmd-btn disabled:opacity-30
          ${device.is_lost_mode ? 'lost-mode-banner text-lost' : 'bg-[#FFF5F5] border-[#FFCACA] text-lost/70 hover:bg-[#FFEBEB]'}`}>
        {executing === 'lost' ? <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin inline-block" /> : <LocateFixed className="mr-1 inline" size={16} aria-hidden="true" />}
        {executing !== 'lost' && (device.is_lost_mode ? 'Disable Lost Mode' : 'Enable Lost Mode')}
      </button>

      {offline && <p className="text-xs text-text-muted text-center">Device is offline. Commands will be queued.</p>}
    </div>
  );
}
