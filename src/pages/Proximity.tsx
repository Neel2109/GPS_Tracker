import { useCallback, useEffect, useState } from 'react';
import { ArrowLeftRight, CircleHelp, MapPin, RefreshCw, ShieldAlert } from 'lucide-react';
import type { DeviceProximityPair, DeviceProximitySnapshot } from '../types';
import { ApiError, locationAPI } from '../services/api';

const THRESHOLDS = [100, 250, 500, 1000];

const STATE_LABELS: Record<DeviceProximityPair['status'], string> = {
  NEAR: 'Near',
  SEPARATED: 'Separated',
  UNCERTAIN: 'Uncertain',
  UNKNOWN: 'Unknown',
};

function distanceLabel(distance: number | null) {
  if (distance == null || !Number.isFinite(distance)) return 'Distance unavailable';
  return distance >= 1000
    ? `${(distance / 1000).toFixed(2)} km`
    : `${Math.round(distance)} m`;
}

function locationTimeLabel(timestamp: string | null) {
  if (!timestamp) return 'No fix';
  const time = new Date(timestamp);
  return Number.isNaN(time.getTime()) ? 'Time unavailable' : time.toLocaleString();
}

function stateStyle(status: DeviceProximityPair['status']) {
  switch (status) {
    case 'NEAR': return 'border-emerald-300 bg-emerald-50 text-emerald-800';
    case 'SEPARATED': return 'border-amber-300 bg-amber-50 text-amber-900';
    case 'UNCERTAIN': return 'border-sky-300 bg-sky-50 text-sky-800';
    default: return 'border-border bg-surface text-text-muted';
  }
}

function PairCard({
  pair,
  freshnessLimitMinutes,
  maxFixSkewMinutes,
}: {
  pair: DeviceProximityPair;
  freshnessLimitMinutes: number;
  maxFixSkewMinutes: number;
}) {
  return (
    <article className="tg-card space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="rounded-xl bg-primary/10 p-2 text-primary"><ArrowLeftRight size={19} /></span>
          <div>
            <h2 className="font-semibold text-text">{pair.first_device_name} <span className="text-text-muted">↔</span> {pair.second_device_name}</h2>
            <p className="mt-1 text-xs text-text-muted">
              Last known separation: {distanceLabel(pair.last_known_distance_meters)}
            </p>
          </div>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${stateStyle(pair.status)}`}>
          {STATE_LABELS[pair.status]}
        </span>
      </div>

      <div className="grid gap-3 text-xs text-text-secondary sm:grid-cols-2">
        <div className="rounded-xl bg-background p-3">
          <p className="font-medium text-text">{pair.first_device_name}</p>
          <p className="mt-1">Fix: {locationTimeLabel(pair.first_location_time)}</p>
          <p>Reported accuracy: {pair.first_accuracy_meters == null ? 'not reported' : `±${Math.round(pair.first_accuracy_meters)} m`}</p>
        </div>
        <div className="rounded-xl bg-background p-3">
          <p className="font-medium text-text">{pair.second_device_name}</p>
          <p className="mt-1">Fix: {locationTimeLabel(pair.second_location_time)}</p>
          <p>Reported accuracy: {pair.second_accuracy_meters == null ? 'not reported' : `±${Math.round(pair.second_accuracy_meters)} m`}</p>
        </div>
      </div>

      {pair.possible_left_behind_device_name && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
          <ShieldAlert size={18} className="mt-0.5 shrink-0" />
          <p><strong>Possible separation:</strong> {pair.possible_left_behind_device_name} last reported stationary while the other device was moving. Check the device directly; this is an estimate, not proof it was left behind.</p>
        </div>
      )}
      {pair.status === 'UNKNOWN' && (
        <p className="flex items-start gap-2 text-xs text-text-muted">
          <CircleHelp size={16} className="mt-0.5 shrink-0" />
          One or both fixes are missing or older than {freshnessLimitMinutes} minutes, their timestamps differ by more than {maxFixSkewMinutes} minutes, or a timestamp is too far in the future. The displayed distance, if present, is only the last known separation.
        </p>
      )}
      {pair.status === 'UNCERTAIN' && (
        <p className="text-xs text-text-muted">
          Location accuracy overlaps the {pair.threshold_meters} m threshold, or an accuracy value is missing. TrackGuard will not claim these devices are near or separated.
        </p>
      )}
    </article>
  );
}

export default function Proximity() {
  const [threshold, setThreshold] = useState(250);
  const [snapshot, setSnapshot] = useState<DeviceProximitySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSnapshot(await locationAPI.getProximity(threshold));
    } catch (requestError) {
      setError(requestError instanceof ApiError || requestError instanceof Error
        ? requestError.message
        : 'Could not load device proximity.');
    } finally {
      setLoading(false);
    }
  }, [threshold]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => { void refresh(); }, 30_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const pairs = snapshot?.pairs ?? [];
  const separated = pairs.filter(pair => pair.status === 'SEPARATED').length;

  return (
    <div className="animate-in space-y-6 pt-2">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="tracking-eyebrow">TRACKGUARD · DEVICE INTELLIGENCE</p>
          <h1 className="mt-1 font-display text-2xl font-bold text-text">Device proximity</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            Compare the latest reported positions of your own devices. We use reported GPS accuracy and mark old fixes as unknown rather than treating them as live.
          </p>
        </div>
        <button type="button" className="tg-button-secondary inline-flex items-center gap-2" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <section className="tg-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-text">Separation threshold</h2>
          <p className="mt-1 text-xs text-text-muted">A pair is separated only when its accuracy-adjusted minimum distance exceeds this value.</p>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Choose device separation threshold">
          {THRESHOLDS.map(value => (
            <button
              key={value}
              type="button"
              aria-pressed={threshold === value}
              onClick={() => {
                setLoading(true);
                setSnapshot(null);
                setThreshold(value);
              }}
              className={`rounded-lg border px-3 py-2 text-xs font-semibold ${threshold === value ? 'border-primary bg-primary/10 text-primary' : 'border-border bg-surface text-text-secondary'}`}
            >
              {value} m
            </button>
          ))}
        </div>
      </section>

      {error && <p role="alert" className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      {snapshot && (
        <div className="flex flex-wrap gap-3 text-xs text-text-secondary">
          <span className="inline-flex items-center gap-2 rounded-full bg-surface px-3 py-2"><MapPin size={15} /> {pairs.length} device pairs</span>
          <span className="rounded-full bg-surface px-3 py-2">{separated} confidently separated</span>
          <span className="rounded-full bg-surface px-3 py-2">Fix freshness limit: {snapshot.freshness_limit_minutes} minutes</span>
          <span className="rounded-full bg-surface px-3 py-2">Last calculated: {new Date(snapshot.generated_at).toLocaleTimeString()}</span>
        </div>
      )}

      {loading && !snapshot ? (
        <div className="skeleton h-48" aria-label="Loading device proximity" />
      ) : pairs.length ? (
        <div className="grid gap-4 xl:grid-cols-2">{pairs.map(pair => (
          <PairCard
            key={`${pair.first_device_id}:${pair.second_device_id}`}
            pair={pair}
            freshnessLimitMinutes={snapshot?.freshness_limit_minutes ?? 10}
            maxFixSkewMinutes={snapshot?.max_fix_skew_minutes ?? 5}
          />
        ))}</div>
      ) : !error && (
        <section className="tg-card py-12 text-center">
          <MapPin size={28} className="mx-auto text-text-muted" />
          <h2 className="mt-3 font-semibold text-text">{snapshot ? 'Add another device to compare' : 'No device pairs yet'}</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-text-muted">
            Proximity appears when your account has at least two paired devices. Devices need to report a location for a meaningful comparison.
          </p>
        </section>
      )}
    </div>
  );
}
