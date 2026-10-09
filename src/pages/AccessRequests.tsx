import { useCallback, useEffect, useState } from 'react';
import { accessRequestAPI } from '../services/api';
import type { LocationAccessRequest } from '../types';

export default function AccessRequests() {
  const [requests, setRequests] = useState<LocationAccessRequest[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setError('');
    try {
      setRequests(await accessRequestAPI.list());
    } catch (loadError: unknown) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load access requests.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const decide = async (request: LocationAccessRequest, action: 'APPROVE' | 'DENY' | 'REVOKE') => {
    setBusyId(request.id);
    setError('');
    try {
      await accessRequestAPI.decide(request.id, action);
      await refresh();
    } catch (decisionError: unknown) {
      setError(decisionError instanceof Error ? decisionError.message : 'Could not update access request.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 md:p-8">
      <header>
        <p className="text-sm font-semibold uppercase tracking-widest text-emerald-700">Privacy controls</p>
        <h1 className="mt-1 text-3xl font-bold text-slate-900">Access approvals</h1>
        <p className="mt-2 text-slate-600">
          Review each request's scope and reason. Access expires automatically, and you can revoke an approval at any time.
        </p>
      </header>

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}

      <div className="space-y-4">
        {requests.map(request => {
          const active = request.status === 'APPROVED'
            && !!request.expires_at
            && new Date(request.expires_at).getTime() > Date.now();
          return (
            <article key={request.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">
                    {request.requester_name} requests {request.scope === 'DEVICE_CONTROL' ? 'device control' : 'location access'}
                  </h2>
                  <p className="mt-1 text-sm text-slate-700">{request.reason}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-bold ${active
                  ? 'bg-emerald-100 text-emerald-800'
                  : request.status === 'PENDING'
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-slate-100 text-slate-700'}`}>
                  {request.status}
                </span>
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">Requested access</dt>
                  <dd className="font-semibold">
                    {request.scope === 'DEVICE_CONTROL'
                      ? `Control ${request.target_device_name || 'the selected device'} (${request.target_device_type || 'device'})`
                      : 'View your devices’ current locations and location history'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Maximum duration</dt>
                  <dd className="font-semibold">{request.duration_minutes} minutes</dd>
                </div>
                {request.scope === 'DEVICE_CONTROL' && (
                  <div className="sm:col-span-2 text-xs text-slate-600">
                    Online Windows agents support lock, sleep, restart, shut down, and Lost Mode. Android supports Lost Mode only.
                    Each command requires the administrator to type the exact device name. Arbitrary shell commands are never allowed.
                  </div>
                )}
                <div><dt className="text-slate-500">Requested</dt><dd>{new Date(request.created_at).toLocaleString()}</dd></div>
                {request.expires_at && <div><dt className="text-slate-500">Expires</dt><dd>{new Date(request.expires_at).toLocaleString()}</dd></div>}
              </dl>
              {request.status === 'PENDING' && (
                <div className="mt-5 flex gap-3">
                  <button disabled={busyId === request.id} onClick={() => void decide(request, 'APPROVE')}
                    className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                    Approve for {request.duration_minutes} minutes
                  </button>
                  <button disabled={busyId === request.id} onClick={() => void decide(request, 'DENY')}
                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">
                    Deny
                  </button>
                </div>
              )}
              {active && (
                <button disabled={busyId === request.id} onClick={() => void decide(request, 'REVOKE')}
                  className="mt-5 rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-50">
                  Revoke access now
                </button>
              )}
            </article>
          );
        })}
        {requests.length === 0 && !error && (
          <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-600">
            No administrator access requests.
          </div>
        )}
      </div>
    </div>
  );
}
