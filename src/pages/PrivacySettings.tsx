import { useState } from 'react';
import { Download, ShieldCheck, Trash2 } from 'lucide-react';
import { privacyAPI } from '../services/api';

export default function PrivacySettings() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const exportData = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const data = await privacyAPI.exportAccountData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `trackguard-account-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice('Your account data export was downloaded.');
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : 'Could not export account data.');
    } finally {
      setBusy(false);
    }
  };

  const deleteHistory = async () => {
    const confirmed = window.confirm(
      'Permanently delete all location history from every device on this account? This cannot be undone. Your devices, account, alerts, and geofences will remain.',
    );
    if (!confirmed) return;
    const phrase = window.prompt('Type DELETE MY LOCATION HISTORY to confirm.');
    if (phrase !== 'DELETE MY LOCATION HISTORY') {
      setError('Location history was not deleted; the confirmation did not match.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await privacyAPI.deleteLocationHistory();
      setNotice(`${result.deleted_locations} location records permanently deleted.`);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not delete location history.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5 pt-2">
      <header>
        <p className="text-xs font-bold tracking-[0.18em] text-lime-400">ACCOUNT CONTROLS</p>
        <h1 className="mt-1 text-2xl font-bold text-white">Privacy &amp; data</h1>
        <p className="mt-1 text-sm text-slate-400">Review active administrator grants under Access approvals. Location history is kept until you delete it.</p>
      </header>
      {error && <p role="alert" className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</p>}
      {notice && <p role="status" className="rounded-xl border border-lime-400/30 bg-lime-400/10 px-4 py-3 text-sm text-lime-200">{notice}</p>}
      <section className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
        <div className="flex gap-3">
          <ShieldCheck className="mt-1 shrink-0 text-lime-300" size={20} />
          <div>
            <h2 className="font-semibold text-white">Owner-controlled access</h2>
            <p className="mt-1 text-sm text-slate-400">Administrator location access requires your approval and expires. You can review or revoke grants from Access approvals; device-control grants are separate and device-scoped.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3 border-t border-white/10 pt-4">
          <button type="button" onClick={() => void exportData()} disabled={busy}
            className="inline-flex items-center gap-2 rounded-xl bg-lime-300 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50">
            <Download size={16} /> Export my account data
          </button>
        </div>
      </section>
      <section className="space-y-3 rounded-2xl border border-red-300/20 bg-red-400/[0.04] p-5">
        <div className="flex gap-3">
          <Trash2 className="mt-1 shrink-0 text-red-300" size={20} />
          <div>
            <h2 className="font-semibold text-white">Delete location history</h2>
            <p className="mt-1 text-sm text-slate-400">Permanently removes saved location points for all devices you own. Trip reports and route playback based on those points will no longer be available. Your account, devices, alerts, geofences, and access requests are not deleted.</p>
          </div>
        </div>
        <button type="button" onClick={() => void deleteHistory()} disabled={busy}
          className="rounded-xl border border-red-300/40 px-4 py-2 text-sm font-semibold text-red-200 hover:bg-red-400/10 disabled:opacity-50">
          {busy ? 'Working…' : 'Permanently delete location history'}
        </button>
      </section>
    </div>
  );
}
