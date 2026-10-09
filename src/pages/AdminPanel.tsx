import { useCallback, useEffect, useState } from 'react';
import { adminAPI, healthAPI } from '../services/api';
import { wsService } from '../services/websocket';
import GoogleLiveMap from '../components/GoogleLiveMap';
import type {
  AdminAuditEvent,
  AdminIncident,
  AdminDeviceCommandType,
  AdminDevice,
  AdminGrantedDeviceLocation,
  AdminPage,
  AdminOverview,
  AdminSession,
  AdminUser,
  Location,
  LocationAccessRequest,
  User,
  WSMessage,
} from '../types';

interface Props {
  user: User;
}

interface AdminSecretNotice {
  name: string;
  invitationUrl?: string;
  invitationToken?: string;
  invitationExpiresAt?: string;
  totpSecret?: string;
  provisioningUri?: string;
}

const PAGE_SIZE = 25;

const emptyOverview: AdminOverview = {
  total_users: 0,
  active_users: 0,
  admins: 0,
  total_devices: 0,
  online_devices: 0,
};

function downloadCsv(filename: string, headers: string[], rows: unknown[][]) {
  const escapeCell = (value: unknown) => {
    const text = value == null ? '' : String(value);
    const safeText = /^[\u0000-\u0020\uFEFF]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)
      ? `'${text}`
      : text;
    return `"${safeText.replaceAll('"', '""')}"`;
  };
  const csv = [headers, ...rows]
    .map(row => row.map(escapeCell).join(','))
    .join('\r\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function AdminPanel({ user }: Props) {
  const [overview, setOverview] = useState(emptyOverview);
  const [devices, setDevices] = useState<AdminDevice[]>([]);
  const [audit, setAudit] = useState<AdminAuditEvent[]>([]);
  const [accessRequests, setAccessRequests] = useState<LocationAccessRequest[]>([]);
  const [incidents, setIncidents] = useState<AdminIncident[]>([]);
  const [liveDevices, setLiveDevices] = useState<AdminGrantedDeviceLocation[]>([]);
  const [accountSearch, setAccountSearch] = useState('');
  const [accountRoleFilter, setAccountRoleFilter] = useState<AdminUser['role'] | 'ALL'>('ALL');
  const [accountStatusFilter, setAccountStatusFilter] = useState<AdminUser['account_status'] | 'ALL'>('ALL');
  const [deviceSearch, setDeviceSearch] = useState('');
  const [deviceStatusFilter, setDeviceStatusFilter] = useState('ALL');
  const [deviceTypeFilter, setDeviceTypeFilter] = useState('ALL');
  const [deviceLostModeFilter, setDeviceLostModeFilter] = useState<'ALL' | 'LOST' | 'NORMAL'>('ALL');
  const [accessSearch, setAccessSearch] = useState('');
  const [accessStatusFilter, setAccessStatusFilter] = useState<LocationAccessRequest['status'] | 'ALL'>('ALL');
  const [accessScopeFilter, setAccessScopeFilter] = useState('ALL');
  const [accessAccountSearch, setAccessAccountSearch] = useState('');
  const [accessDeviceSearch, setAccessDeviceSearch] = useState('');
  const [accessAccountChoices, setAccessAccountChoices] = useState<AdminUser[]>([]);
  const [accessDeviceChoices, setAccessDeviceChoices] = useState<AdminDevice[]>([]);
  const [selectedAccessAccount, setSelectedAccessAccount] = useState<AdminUser | null>(null);
  const [auditSearch, setAuditSearch] = useState('');
  const [auditActionFilter, setAuditActionFilter] = useState('ALL');
  const [userPage, setUserPage] = useState<AdminPage<AdminUser>>({ items: [], total: 0, offset: 0, limit: PAGE_SIZE });
  const [devicePage, setDevicePage] = useState<AdminPage<AdminDevice>>({ items: [], total: 0, offset: 0, limit: PAGE_SIZE });
  const [auditPage, setAuditPage] = useState<AdminPage<AdminAuditEvent>>({ items: [], total: 0, offset: 0, limit: PAGE_SIZE });
  const [userPageIndex, setUserPageIndex] = useState(0);
  const [devicePageIndex, setDevicePageIndex] = useState(0);
  const [auditPageIndex, setAuditPageIndex] = useState(0);
  const [tableRevision, setTableRevision] = useState(0);
  const [userSortBy, setUserSortBy] = useState('created_at');
  const [deviceSortBy, setDeviceSortBy] = useState('created_at');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [incidentFilter, setIncidentFilter] = useState('OPEN');
  const [accountSessions, setAccountSessions] = useState<{ user: AdminUser; sessions: AdminSession[] } | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [role, setRole] = useState<'USER' | 'ADMIN'>('USER');
  const [targetUserId, setTargetUserId] = useState('');
  const [targetDeviceId, setTargetDeviceId] = useState('');
  const [accessScope, setAccessScope] = useState<'LOCATION_READ' | 'DEVICE_CONTROL'>('LOCATION_READ');
  const [accessReason, setAccessReason] = useState('');
  const [accessDuration, setAccessDuration] = useState(60);
  const [liveSearch, setLiveSearch] = useState('');
  const [liveFilter, setLiveFilter] = useState('ALL');
  const [commandNotice, setCommandNotice] = useState('');
  const [selectedGrant, setSelectedGrant] = useState<string | null>(null);
  const [grantedLocations, setGrantedLocations] = useState<AdminGrantedDeviceLocation[]>([]);
  const [history, setHistory] = useState<{ deviceName: string; locations: Location[] } | null>(null);
  const [provisioned, setProvisioned] = useState<AdminSecretNotice | null>(null);
  const [busy, setBusy] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [error, setError] = useState('');
  const [serviceHealth, setServiceHealth] = useState<{ status: string; database: string; checkedAt: string; detail?: string } | null>(null);

  const refresh = useCallback(async () => {
    setError('');
    try {
      const summary = await adminAPI.overview();
      const requestRows = await adminAPI.accessRequests();
      const incidentRows = await adminAPI.incidents('ALL');
      try {
        const health = await healthAPI.check();
        setServiceHealth({ ...health, checkedAt: new Date().toISOString() });
      } catch (healthError: unknown) {
        setServiceHealth({
          status: 'unavailable',
          database: 'unknown',
          checkedAt: new Date().toISOString(),
          detail: healthError instanceof Error ? healthError.message : 'Health check failed.',
        });
      }
      const activeLocationRequests = requestRows.filter(request =>
        request.scope === 'LOCATION_READ'
        && request.status === 'APPROVED'
        && !!request.expires_at
        && new Date(request.expires_at).getTime() > Date.now(),
      );
      const locationGroups = await Promise.all(
        activeLocationRequests.map(request => adminAPI.grantedDeviceLocations(request.id)),
      );
      setOverview(summary);
      setAccessRequests(requestRows);
      setIncidents(incidentRows);
      setLiveDevices(locationGroups.flat());
      setTableRevision(revision => revision + 1);
    } catch (loadError: unknown) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load administrator data.');
    }
  }, [user.id]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setPageLoading(true);
      Promise.all([
        adminAPI.usersPage({
          offset: userPageIndex * PAGE_SIZE,
          limit: PAGE_SIZE,
          search: accountSearch,
          role: accountRoleFilter,
          status: accountStatusFilter,
          sort_by: userSortBy,
          sort_direction: sortDirection,
        }),
        adminAPI.devicesPage({
          offset: devicePageIndex * PAGE_SIZE,
          limit: PAGE_SIZE,
          search: deviceSearch,
          status: deviceStatusFilter,
          device_type: deviceTypeFilter,
          lost_mode: deviceLostModeFilter,
          sort_by: deviceSortBy,
          sort_direction: sortDirection,
        }),
        adminAPI.auditPage({
          offset: auditPageIndex * PAGE_SIZE,
          limit: PAGE_SIZE,
          search: auditSearch,
          action: auditActionFilter,
          sort_direction: sortDirection,
        }),
      ]).then(([nextUsers, nextDevices, nextAudit]) => {
        if (!active) return;
        setUserPage(nextUsers);
        setDevicePage(nextDevices);
        setAuditPage(nextAudit);
        setDevices(nextDevices.items);
        setAudit(nextAudit.items);
      }).catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Could not load administrator tables.');
      }).finally(() => {
        if (active) setPageLoading(false);
      });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [
    accountRoleFilter, accountSearch, accountStatusFilter, auditActionFilter, auditPageIndex, auditSearch,
    deviceLostModeFilter, devicePageIndex, deviceSearch, deviceSortBy, deviceStatusFilter, deviceTypeFilter,
    sortDirection, userPageIndex, userSortBy,
    tableRevision,
  ]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      Promise.all([
        adminAPI.usersPage({
          offset: 0,
          limit: PAGE_SIZE,
          search: accessAccountSearch,
          status: 'ACTIVE',
          sort_by: 'name',
          sort_direction: 'asc',
        }),
        targetUserId
          ? adminAPI.devicesPage({
            offset: 0,
            limit: PAGE_SIZE,
            owner_user_id: targetUserId,
            search: accessDeviceSearch,
            sort_by: 'name',
            sort_direction: 'asc',
          })
          : Promise.resolve({ items: [], total: 0, offset: 0, limit: PAGE_SIZE }),
      ]).then(([accountResults, deviceResults]) => {
        if (!active) return;
        setAccessAccountChoices(accountResults.items);
        setAccessDeviceChoices(deviceResults.items);
        if (!targetUserId) {
          const firstChoice = accountResults.items.find(account => account.id !== user.id) || null;
          setSelectedAccessAccount(firstChoice);
          setTargetUserId(firstChoice?.id || '');
        }
      }).catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Could not load access-request targets.');
      });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [accessAccountSearch, accessDeviceSearch, targetUserId, user.id]);

  useEffect(() => {
    if (accessScope !== 'DEVICE_CONTROL') return;
    if (accessDeviceChoices.some(device => device.id === targetDeviceId)) return;
    setTargetDeviceId(accessDeviceChoices[0]?.id || '');
  }, [accessDeviceChoices, accessScope, targetDeviceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    wsService.connect(user.id);
    const unsubscribe = wsService.on('ADMIN_LIVE_LOCATION_UPDATE', (message: WSMessage) => {
      if (!message.device_id || !message.access_request_id || !message.data) return;
      const latitude = message.data.latitude;
      const longitude = message.data.longitude;
      if (typeof latitude !== 'number' || typeof longitude !== 'number') return;
      const accuracy = message.data.accuracy;
      const timestamp = message.data.timestamp;
      const source = message.data.source;
      const speed = message.data.speed;
      const movement = message.data.movement_state;
      setLiveDevices(current => current.map(device =>
        device.id === message.device_id && device.access_request_id === message.access_request_id
          ? {
            ...device,
            last_latitude: latitude,
            last_longitude: longitude,
            last_accuracy: typeof accuracy === 'number' ? accuracy : null,
            last_location_source: typeof source === 'string' ? source : null,
            last_location_time: typeof timestamp === 'string' ? timestamp : null,
            last_speed: typeof speed === 'number' ? speed : null,
            movement_state: typeof movement === 'string' ? movement : null,
            status: 'online',
          }
          : device,
      ));
    });
    const unsubscribeCommand = wsService.on('ADMIN_COMMAND_RESULT', (message: WSMessage) => {
      const command = message.data?.command;
      const status = message.data?.status;
      const result = message.data?.result;
      if (typeof command !== 'string' || typeof status !== 'string') return;
      setCommandNotice(
        `${command.replaceAll('_', ' ')} ${status}${typeof result === 'string' && result ? ` · ${result}` : ''}`,
      );
    });
    return () => {
      unsubscribe();
      unsubscribeCommand();
    };
  }, [user.id]);

  const filteredLiveDevices = liveDevices.filter(device => {
    const query = liveSearch.trim().toLocaleLowerCase();
    const matchesQuery = !query
      || `${device.owner_name} ${device.name} ${device.platform || ''} ${device.device_type}`
        .toLocaleLowerCase().includes(query);
    const matchesFilter = liveFilter === 'ALL'
      || (liveFilter === 'ONLINE' && device.status === 'online')
      || (liveFilter === 'OFFLINE' && device.status !== 'online')
      || (liveFilter === 'MOVING' && ['WALKING', 'CYCLING', 'DRIVING'].includes(device.movement_state || ''))
      || (liveFilter === 'LOW_BATTERY' && device.battery_level !== null && device.battery_level <= 20)
      || (liveFilter === 'LOST_MODE' && device.is_lost_mode);
    return matchesQuery && matchesFilter;
  });

  const filteredUsers = userPage.items;
  const filteredDevices = devicePage.items;

  const filteredAccessRequests = accessRequests.filter(accessRequest => {
    const query = accessSearch.trim().toLocaleLowerCase();
    const matchesQuery = !query
      || `${accessRequest.requester_name} ${accessRequest.requester_user_id} ${accessRequest.target_name} ${accessRequest.target_user_id} ${accessRequest.target_device_name || ''} ${accessRequest.reason} ${accessRequest.scope} ${accessRequest.status} ${accessRequest.id}`
        .toLocaleLowerCase().includes(query);
    return matchesQuery
      && (accessStatusFilter === 'ALL' || accessRequest.status === accessStatusFilter)
      && (accessScopeFilter === 'ALL' || accessRequest.scope === accessScopeFilter);
  });

  const filteredAudit = auditPage.items;
  const filteredIncidents = incidents.filter(incident =>
    incidentFilter === 'ALL' || incident.status === incidentFilter,
  );

  const deviceStatuses = [...new Set(devices.map(device => device.status))].sort((a, b) => a.localeCompare(b));
  const deviceTypes = [...new Set(devices.map(device => device.device_type))].sort((a, b) => a.localeCompare(b));
  const accessScopes = [...new Set(accessRequests.map(request => request.scope))].sort((a, b) => a.localeCompare(b));
  const auditActions = [...new Set(audit.map(event => event.action))].sort((a, b) => a.localeCompare(b));

  const addUser = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const normalizedPhone = phone.replace(/[\s().-]/g, '');
      const result = await adminAPI.createUser({ name: name.trim(), phone_number: normalizedPhone, role });
      const invitationUrl = new URL('/unlock', window.location.origin);
      invitationUrl.searchParams.set('invite', result.invitation_token);
      setProvisioned({
        name: result.name,
        invitationToken: result.invitation_token,
        invitationUrl: invitationUrl.toString(),
        invitationExpiresAt: result.invitation_expires_at,
      });
      setName('');
      setPhone('');
      setRole('USER');
      await refresh();
    } catch (createError: unknown) {
      setError(createError instanceof Error ? createError.message : 'Could not create account.');
    } finally {
      setBusy(false);
    }
  };

  const updateAccount = async (
    target: AdminUser,
    patch: { role?: AdminUser['role']; account_status?: AdminUser['account_status'] },
  ) => {
    setBusy(true);
    setError('');
    try {
      await adminAPI.updateUser(target.id, patch);
      await refresh();
    } catch (updateError: unknown) {
      setError(updateError instanceof Error ? updateError.message : 'Could not update account.');
    } finally {
      setBusy(false);
    }
  };

  const resetAuthenticator = async (target: AdminUser) => {
    if (!window.confirm(`Reset ${target.name}'s authenticator? Their current authenticator will stop working.`)) return;
    setBusy(true);
    setError('');
    try {
      const result = await adminAPI.resetAuthenticator(target.id);
      setProvisioned({
        name: target.name,
        totpSecret: result.secret,
        provisioningUri: result.provisioning_uri,
      });
      await refresh();
    } catch (resetError: unknown) {
      setError(resetError instanceof Error ? resetError.message : 'Could not reset authenticator.');
    } finally {
      setBusy(false);
    }
  };

  const issueInvitation = async (target: AdminUser) => {
    setBusy(true);
    setError('');
    try {
      const result = await adminAPI.createInvitation(target.id);
      const invitationUrl = new URL('/unlock', window.location.origin);
      invitationUrl.searchParams.set('invite', result.invitation_token);
      setProvisioned({
        name: target.name,
        invitationToken: result.invitation_token,
        invitationUrl: invitationUrl.toString(),
        invitationExpiresAt: result.invitation_expires_at,
      });
    } catch (inviteError: unknown) {
      setError(inviteError instanceof Error ? inviteError.message : 'Could not issue account invitation.');
    } finally {
      setBusy(false);
    }
  };

  const loadAccountSessions = async (target: AdminUser) => {
    setBusy(true);
    setError('');
    try {
      setAccountSessions({ user: target, sessions: await adminAPI.userSessions(target.id) });
    } catch (sessionError: unknown) {
      setError(sessionError instanceof Error ? sessionError.message : 'Could not load account sessions.');
    } finally {
      setBusy(false);
    }
  };

  const revokeAccountSession = async (session: AdminSession) => {
    if (!accountSessions) return;
    if (!window.confirm(`Revoke this session for ${accountSessions.user.name}? The device will need to sign in again.`)) return;
    setBusy(true);
    setError('');
    try {
      const revoked = await adminAPI.revokeUserSession(accountSessions.user.id, session.id);
      setAccountSessions(current => current
        ? { ...current, sessions: current.sessions.map(item => item.id === revoked.id ? revoked : item) }
        : current);
    } catch (sessionError: unknown) {
      setError(sessionError instanceof Error ? sessionError.message : 'Could not revoke account session.');
    } finally {
      setBusy(false);
    }
  };

  const changeIncidentStatus = async (incident: AdminIncident, status: 'ACKNOWLEDGED' | 'RESOLVED') => {
    setBusy(true);
    setError('');
    try {
      const updated = await adminAPI.updateIncident(incident.id, status);
      setIncidents(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (incidentError: unknown) {
      setError(incidentError instanceof Error ? incidentError.message : 'Could not update incident.');
    } finally {
      setBusy(false);
    }
  };

  const requestLocationAccess = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await adminAPI.requestLocationAccess({
        target_user_id: targetUserId,
        scope: accessScope,
        ...(accessScope === 'DEVICE_CONTROL' ? { target_device_id: targetDeviceId } : {}),
        reason: accessReason.trim(),
        duration_minutes: accessScope === 'DEVICE_CONTROL' ? 15 : accessDuration,
      });
      setAccessReason('');
      await refresh();
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : 'Could not request location access.');
    } finally {
      setBusy(false);
    }
  };

  const controlDevice = async (
    accessRequest: LocationAccessRequest,
    device: AdminDevice,
    command: AdminDeviceCommandType,
  ) => {
    const confirmation = window.prompt(
      `To authorize ${command.replaceAll('_', ' ').toLowerCase()}, type the exact device name: ${device.name}`,
    );
    if (confirmation === null) return;
    setBusy(true);
    setError('');
    try {
      const result = await adminAPI.controlDevice(accessRequest.id, device.id, command, confirmation);
      setError('');
      setCommandNotice(`${result.command.replaceAll('_', ' ')} sent; waiting for device confirmation.`);
      await refresh();
    } catch (commandError: unknown) {
      setError(commandError instanceof Error ? commandError.message : 'Could not send the device command.');
    } finally {
      setBusy(false);
    }
  };

  const revokeLocationAccess = async (accessRequest: LocationAccessRequest) => {
    setBusy(true);
    setError('');
    try {
      await adminAPI.revokeLocationAccess(accessRequest.id);
      if (selectedGrant === accessRequest.id) {
        setSelectedGrant(null);
        setGrantedLocations([]);
        setHistory(null);
      }
      await refresh();
    } catch (revokeError: unknown) {
      setError(revokeError instanceof Error ? revokeError.message : 'Could not revoke location access.');
    } finally {
      setBusy(false);
    }
  };

  const viewGrantedLocations = async (accessRequest: LocationAccessRequest) => {
    setBusy(true);
    setError('');
    try {
      const result = await adminAPI.grantedDeviceLocations(accessRequest.id);
      setSelectedGrant(accessRequest.id);
      setGrantedLocations(result);
      setHistory(null);
    } catch (locationError: unknown) {
      setError(locationError instanceof Error ? locationError.message : 'Could not load granted locations.');
    } finally {
      setBusy(false);
    }
  };

  const viewGrantedHistory = async (accessRequestId: string, device: AdminGrantedDeviceLocation) => {
    setBusy(true);
    setError('');
    try {
      const locations = await adminAPI.grantedDeviceHistory(accessRequestId, device.id);
      setHistory({ deviceName: device.name, locations });
    } catch (historyError: unknown) {
      setError(historyError instanceof Error ? historyError.message : 'Could not load granted location history.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-widest text-emerald-700">Platform controls</p>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">Administrator console</h1>
          <p className="mt-1 text-sm text-slate-600">Signed in as {user.name} · {user.role}</p>
        </div>
        <button className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          onClick={() => void refresh()} disabled={busy}>
          Refresh
        </button>
      </header>

      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        Phone ownership must be verified by SMS before account activation or sign-in. New accounts use expiring, single-use
        invitations so the account holder sets up their own authenticator. Admin device inventory omits coordinates.
        Location access requires owner approval; cross-account controls require a separate short-lived grant and an audit trail.
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}
      {commandNotice && (
        <div role="status" className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          {commandNotice}
        </div>
      )}

      {provisioned && (
        <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-bold text-emerald-950">
                {provisioned.invitationToken ? 'Account invitation — share privately' : 'Authenticator setup key'}
              </h2>
              <p className="mt-1 text-sm text-emerald-900">{provisioned.name} can finish setup from the sign-in page.</p>
            </div>
            <button onClick={() => setProvisioned(null)} className="text-sm font-semibold text-emerald-900 underline">
              Dismiss
            </button>
          </div>
          {provisioned.invitationUrl && (
            <>
              <p className="mt-3 break-all rounded-lg bg-white p-3 font-mono text-sm select-all">{provisioned.invitationUrl}</p>
              <p className="mt-2 text-xs text-emerald-900">
                Invitation expires {new Date(provisioned.invitationExpiresAt || '').toLocaleString()} and can be used once.
                The recipient must verify the invited phone by SMS before setting up their authenticator.
              </p>
            </>
          )}
          {provisioned.totpSecret && (
            <p className="mt-3 break-all rounded-lg bg-white p-3 font-mono text-sm select-all">{provisioned.totpSecret}</p>
          )}
          {provisioned.provisioningUri && (
            <p className="mt-2 break-all text-xs text-emerald-900">Authenticator URI: {provisioned.provisioningUri}</p>
          )}
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="All accounts" value={overview.total_users} />
        <Metric label="Active accounts" value={overview.active_users} />
        <Metric label="Administrators" value={overview.admins} />
        <Metric label="Registered devices" value={overview.total_devices} />
        <Metric label="Online devices" value={overview.online_devices} />
      </section>
      {serviceHealth && (
        <section aria-live="polite" className={`rounded-xl border p-4 text-sm ${serviceHealth.status === 'healthy'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
          : 'border-amber-200 bg-amber-50 text-amber-950'}`}>
          <h2 className="font-semibold">Operational health</h2>
          <p className="mt-1">API: {serviceHealth.status} · Database: {serviceHealth.database} · Checked {new Date(serviceHealth.checkedAt).toLocaleString()}</p>
          {serviceHealth.detail && <p className="mt-1">{serviceHealth.detail}</p>}
        </section>
      )}

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-5">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Platform incident center</h2>
            <p className="mt-1 text-sm text-slate-600">Operational events only; location coordinates remain owner-gated.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={incidentFilter} onChange={event => setIncidentFilter(event.target.value)}
              aria-label="Filter incidents by status" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
              <option value="OPEN">Open</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="RESOLVED">Resolved</option>
              <option value="ALL">All statuses</option>
            </select>
            <button type="button" onClick={() => void refresh()} disabled={busy}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold">Refresh</button>
          </div>
        </div>
        <div className="divide-y divide-slate-100">
          {filteredIncidents.map(incident => (
            <div key={incident.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
              <div className="min-w-56 flex-1">
                <div className="font-semibold text-slate-900">{incident.title}</div>
                <p className="mt-1 text-sm text-slate-600">{incident.message}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {incident.user_name}{incident.device_name ? ` · ${incident.device_name}` : ''}
                  {' · '}{incident.type.replaceAll('_', ' ')} · {new Date(incident.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold">{incident.status}</span>
                {incident.status === 'OPEN' && (
                  <button type="button" disabled={busy} onClick={() => void changeIncidentStatus(incident, 'ACKNOWLEDGED')}
                    className="text-sm font-semibold text-indigo-700 underline">Acknowledge</button>
                )}
                {incident.status !== 'RESOLVED' && (
                  <button type="button" disabled={busy} onClick={() => void changeIncidentStatus(incident, 'RESOLVED')}
                    className="text-sm font-semibold text-emerald-700 underline">Resolve</button>
                )}
              </div>
            </div>
          ))}
          {filteredIncidents.length === 0 && (
            <p className="px-5 py-6 text-sm text-slate-500">No incidents match this status.</p>
          )}
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-800 bg-[#101414] text-white shadow-lg">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 p-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-lime-300">Owner-approved live access</p>
            <h2 className="mt-1 text-xl font-bold">Live command center</h2>
            <p className="mt-1 text-sm text-slate-300">
              Only devices covered by your active location grants appear here. Updates stream in real time.
            </p>
          </div>
          <span className="rounded-full border border-lime-400/30 px-3 py-1 text-xs font-semibold text-lime-300">
            {liveDevices.length} authorized devices
          </span>
        </div>
        <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
          <GoogleLiveMap
            devices={filteredLiveDevices.map(device => ({
              id: device.id,
              name: `${device.owner_name} · ${device.name}`,
              status: device.status,
              last_latitude: device.last_latitude,
              last_longitude: device.last_longitude,
              last_accuracy: device.last_accuracy,
              last_location_source: device.last_location_source,
            }))}
            height="440px"
            className="overflow-hidden rounded-lg"
          />
          <div className="space-y-3">
            <input
              value={liveSearch}
              onChange={event => setLiveSearch(event.target.value)}
              placeholder="Search owner or device"
              aria-label="Search approved live devices"
              className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-400"
            />
            <select
              value={liveFilter}
              onChange={event => setLiveFilter(event.target.value)}
              aria-label="Filter approved live devices"
              className="w-full rounded-lg border border-white/15 bg-[#171d1b] px-3 py-2 text-sm text-white"
            >
              <option value="ALL">All authorized devices</option>
              <option value="ONLINE">Online</option>
              <option value="OFFLINE">Offline</option>
              <option value="MOVING">Moving</option>
              <option value="LOW_BATTERY">Low battery</option>
              <option value="LOST_MODE">Lost mode</option>
            </select>
            <div className="max-h-[370px] divide-y divide-white/10 overflow-y-auto">
              {filteredLiveDevices.map(device => (
                <div key={`${device.access_request_id}:${device.id}`} className="py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{device.name}</span>
                    <span className={device.status === 'online' ? 'text-xs text-lime-300' : 'text-xs text-slate-400'}>
                      {device.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-300">
                    {device.owner_name} · {device.owner_role} · {device.platform || device.device_type}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {device.battery_level == null ? 'Battery unavailable' : `Battery ${device.battery_level}%`}
                    {device.network_type ? ` · ${device.network_type}` : ''}
                    {device.movement_state ? ` · ${device.movement_state.toLowerCase()}` : ''}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {device.last_location_time ? new Date(device.last_location_time).toLocaleString() : 'No location time'}
                    {device.last_accuracy != null ? ` · ±${Math.round(device.last_accuracy)} m` : ''}
                  </p>
                </div>
              ))}
              {filteredLiveDevices.length === 0 && (
                <p className="py-5 text-sm text-slate-400">
                  No devices match. Request location access and wait for the owner to approve it.
                </p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900">Provision an account</h2>
        <p className="mt-1 text-sm text-slate-600">Create a phone-number account and generate its initial authenticator key.</p>
        <form onSubmit={addUser} className="mt-4 grid gap-3 md:grid-cols-4">
          <input className="rounded-lg border border-slate-300 px-3 py-2" value={name}
            onChange={event => setName(event.target.value)} placeholder="Account holder name" required maxLength={120} />
          <input className="rounded-lg border border-slate-300 px-3 py-2" value={phone}
            onChange={event => setPhone(event.target.value)} placeholder="Phone, e.g. +14155550123" required type="tel" />
          <select className="rounded-lg border border-slate-300 px-3 py-2" value={role}
            onChange={event => setRole(event.target.value as 'USER' | 'ADMIN')}>
            <option value="USER">USER</option>
            {user.role === 'SUPER_ADMIN' && <option value="ADMIN">ADMIN</option>}
          </select>
          <button type="submit" disabled={busy}
            className="rounded-lg bg-emerald-700 px-4 py-2 font-semibold text-white disabled:opacity-50">
            Create account
          </button>
        </form>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900">Request scoped user access</h2>
        <p className="mt-1 text-sm text-slate-600">
          Owners approve each scope separately. Location and history access expires within four hours; device-control
          access expires after 15 minutes. Remote shell and arbitrary commands are not available.
        </p>
        <form onSubmit={requestLocationAccess} className="mt-4 grid gap-3 md:grid-cols-4">
          <input
            value={accessAccountSearch}
            onChange={event => setAccessAccountSearch(event.target.value)}
            placeholder="Search accounts by name, phone, or ID"
            aria-label="Search accounts for an access request"
            className="rounded-lg border border-slate-300 px-3 py-2"
          />
          <select value={targetUserId} onChange={event => {
            const nextUserId = event.target.value;
            setTargetUserId(nextUserId);
            setSelectedAccessAccount(accessAccountChoices.find(account => account.id === nextUserId) || null);
            setAccessDeviceSearch('');
            setTargetDeviceId('');
          }} required
            className="rounded-lg border border-slate-300 px-3 py-2">
            <option value="" disabled>Select account</option>
            {selectedAccessAccount
              && selectedAccessAccount.id !== user.id
              && !accessAccountChoices.some(account => account.id === selectedAccessAccount.id)
              && <option value={selectedAccessAccount.id}>{selectedAccessAccount.name} · {selectedAccessAccount.phone_number || 'No phone'}</option>}
            {accessAccountChoices.filter(account => account.id !== user.id).map(account => (
              <option key={account.id} value={account.id}>{account.name} · {account.phone_number || 'No phone'}</option>
            ))}
          </select>
          {accessScope === 'DEVICE_CONTROL' && (
            <>
              <input
                value={accessDeviceSearch}
                onChange={event => setAccessDeviceSearch(event.target.value)}
                placeholder="Search this account's devices"
                aria-label="Search devices for a control request"
                className="rounded-lg border border-slate-300 px-3 py-2"
              />
              <select
                value={targetDeviceId}
                onChange={event => setTargetDeviceId(event.target.value)}
                required
                aria-label="Device to request control for"
                className="rounded-lg border border-slate-300 px-3 py-2"
              >
                <option value="" disabled>Select device</option>
                {accessDeviceChoices.map(device => (
                  <option key={device.id} value={device.id}>{device.name} · {device.device_type}</option>
                ))}
              </select>
            </>
          )}
          <input value={accessReason} onChange={event => setAccessReason(event.target.value)}
            minLength={10} maxLength={500} required placeholder="Reason for access (at least 10 characters)"
            className="rounded-lg border border-slate-300 px-3 py-2 md:col-span-2" />
          <select value={accessScope} onChange={event => {
            const scope = event.target.value as 'LOCATION_READ' | 'DEVICE_CONTROL';
            setAccessScope(scope);
            if (scope === 'DEVICE_CONTROL') {
              setAccessDuration(15);
            } else {
              setTargetDeviceId('');
            }
          }} className="rounded-lg border border-slate-300 px-3 py-2">
            <option value="LOCATION_READ">Location + history</option>
            <option value="DEVICE_CONTROL">Device controls (15 min)</option>
          </select>
          <div className="flex gap-2">
            <select value={accessDuration} onChange={event => setAccessDuration(Number(event.target.value))}
              disabled={accessScope === 'DEVICE_CONTROL'}
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2">
              <option value={15}>15 minutes</option>
              <option value={60}>1 hour</option>
              <option value={240}>4 hours</option>
            </select>
            <button type="submit" disabled={busy || !targetUserId || (accessScope === 'DEVICE_CONTROL' && !targetDeviceId)}
              className="rounded-lg bg-emerald-700 px-4 py-2 font-semibold text-white disabled:opacity-50">
              Request
            </button>
          </div>
        </form>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <input
            value={accessSearch}
            onChange={event => setAccessSearch(event.target.value)}
            placeholder="Search requester, account, device, reason, or ID"
            aria-label="Search access requests"
            className="min-w-56 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <select value={accessStatusFilter} onChange={event => setAccessStatusFilter(event.target.value as LocationAccessRequest['status'] | 'ALL')}
            aria-label="Filter access requests by status"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All statuses</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved</option>
            <option value="DENIED">Denied</option>
            <option value="REVOKED">Revoked</option>
            <option value="EXPIRED">Expired</option>
          </select>
          <select value={accessScopeFilter} onChange={event => setAccessScopeFilter(event.target.value)}
            aria-label="Filter access requests by scope"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All scopes</option>
            {accessScopes.map(scope => <option key={scope} value={scope}>{scope.replaceAll('_', ' ')}</option>)}
          </select>
          <button type="button" disabled={filteredAccessRequests.length === 0}
            onClick={() => downloadCsv('access-requests.csv',
              ['Request ID', 'Requester ID', 'Requester', 'Target Account ID', 'Target Account', 'Device ID', 'Device', 'Scope', 'Status', 'Reason', 'Duration Minutes', 'Created At', 'Decided At', 'Expires At'],
              filteredAccessRequests.map(request => [
                request.id, request.requester_user_id, request.requester_name, request.target_user_id,
                request.target_name, request.target_device_id, request.target_device_name, request.scope,
                request.status, request.reason, request.duration_minutes, request.created_at,
                request.decided_at, request.expires_at,
              ]))}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">
            Export CSV ({filteredAccessRequests.length})
          </button>
          <span className="text-xs text-slate-500">Showing {filteredAccessRequests.length} of {accessRequests.length}</span>
        </div>
        <div className="mt-5 divide-y divide-slate-100">
          {filteredAccessRequests.map(accessRequest => {
            const active = accessRequest.status === 'APPROVED'
              && !!accessRequest.expires_at
              && new Date(accessRequest.expires_at).getTime() > Date.now();
            return (
              <div key={accessRequest.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-60 flex-1">
                  <div className="font-semibold text-slate-800">
                    {accessRequest.target_name} · {accessRequest.status}
                  </div>
                  <div className="text-sm text-slate-600">{accessRequest.reason}</div>
                  <div className="text-xs text-slate-500">
                    {accessRequest.duration_minutes} min requested
                    {accessRequest.expires_at ? ` · expires ${new Date(accessRequest.expires_at).toLocaleString()}` : ''}
                  </div>
                  {active && accessRequest.scope === 'DEVICE_CONTROL' && (
                    <div className="mt-3 w-full rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <p className="text-xs font-semibold text-amber-950">
                        Owner-approved controls for {accessRequest.target_device_name || 'the selected device'}
                        {' · '}online only · exact-name confirmation required
                      </p>
                      <div className="mt-2 space-y-2">
                        {devices.filter(device => device.id === accessRequest.target_device_id).map(device => (
                          <div key={device.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                            <span>{device.name} · {device.status}</span>
                            <div className="flex flex-wrap gap-2">
                              {([
                                ...(device.platform?.toLowerCase().startsWith('windows')
                                  ? [
                                    ['LOCK', 'Lock'],
                                    ['SLEEP', 'Sleep'],
                                    ['RESTART', 'Restart'],
                                    ['SHUTDOWN', 'Shut down'],
                                  ] as const
                                  : []),
                                ...(
                                  device.device_type === 'android'
                                  || (
                                    ['laptop', 'desktop'].includes(device.device_type)
                                    && device.platform?.toLowerCase().startsWith('windows')
                                  )
                                  ? [[
                                    device.is_lost_mode ? 'DISABLE_LOST_MODE' : 'ENABLE_LOST_MODE',
                                    device.is_lost_mode ? 'Disable lost mode' : 'Enable lost mode',
                                  ]] as const
                                  : []),
                              ] as const).map(([command, label]) => (
                                <button
                                  key={command}
                                  disabled={busy || device.status !== 'online'}
                                  onClick={() => void controlDevice(accessRequest, device, command)}
                                  className="rounded border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 disabled:opacity-40"
                                >
                                  {label}
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                        {!devices.some(device => device.id === accessRequest.target_device_id) && (
                          <p className="text-xs text-slate-600">The approved device is no longer available.</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex gap-3">
                  {active && accessRequest.scope === 'LOCATION_READ' && <button disabled={busy} onClick={() => void viewGrantedLocations(accessRequest)}
                    className="text-sm font-semibold text-indigo-700 underline">View approved locations</button>}
                  {(active || accessRequest.status === 'PENDING') && (
                    <button disabled={busy} onClick={() => void revokeLocationAccess(accessRequest)}
                      className="text-sm font-semibold text-red-700 underline">Revoke</button>
                  )}
                </div>
              </div>
            );
          })}
          {filteredAccessRequests.length === 0 && (
            <p className="py-4 text-sm text-slate-500">
              {accessRequests.length === 0 ? 'No location access requests.' : 'No access requests match these filters.'}
            </p>
          )}
        </div>
        {selectedGrant && (
          <div className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50 p-4">
            <h3 className="font-semibold text-indigo-950">Owner-approved device locations</h3>
            <div className="mt-3 divide-y divide-indigo-100">
              {grantedLocations.map(device => (
                <div key={device.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                  <div>
                    <div className="font-semibold">{device.name} · {device.status}</div>
                    {device.last_latitude != null && device.last_longitude != null
                      ? <div>{device.last_latitude.toFixed(6)}, {device.last_longitude.toFixed(6)}
                        {device.last_accuracy != null ? ` · ±${Math.round(device.last_accuracy)} m` : ''}</div>
                      : <div>No location reported.</div>}
                    <div className="text-xs text-slate-600">
                      {device.last_location_time ? new Date(device.last_location_time).toLocaleString() : 'Location time unavailable'}
                    </div>
                  </div>
                  <button disabled={busy} onClick={() => void viewGrantedHistory(selectedGrant, device)}
                    className="font-semibold text-indigo-700 underline">View 7-day history</button>
                </div>
              ))}
              {grantedLocations.length === 0 && <p className="py-3 text-sm">No devices are registered to this account.</p>}
            </div>
            {history && (
              <div className="mt-4 rounded bg-white p-3">
                <h4 className="font-semibold">{history.deviceName} · last 7 days</h4>
                <div className="mt-2 max-h-56 space-y-2 overflow-y-auto text-xs">
                  {history.locations.map(location => (
                    <div key={location.id}>
                      {new Date(location.timestamp).toLocaleString()} · {location.latitude.toFixed(6)}, {location.longitude.toFixed(6)}
                    </div>
                  ))}
                  {history.locations.length === 0 && <p>No location history in this period.</p>}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-xl font-bold text-slate-900">Accounts</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-5 py-4">
          <input value={accountSearch}
            placeholder="Search name, email, phone, or ID" aria-label="Search accounts"
            onChange={event => { setAccountSearch(event.target.value); setUserPageIndex(0); }}
            className="min-w-56 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <select value={accountRoleFilter} onChange={event => { setAccountRoleFilter(event.target.value as AdminUser['role'] | 'ALL'); setUserPageIndex(0); }}
            aria-label="Filter accounts by role" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All roles</option>
            <option value="USER">USER</option>
            <option value="ADMIN">ADMIN</option>
            <option value="SUPER_ADMIN">SUPER_ADMIN</option>
          </select>
          <select value={accountStatusFilter} onChange={event => { setAccountStatusFilter(event.target.value as AdminUser['account_status'] | 'ALL'); setUserPageIndex(0); }}
            aria-label="Filter accounts by status" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All statuses</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="SUSPENDED">SUSPENDED</option>
          </select>
          <select aria-label="Sort accounts by" value={userSortBy} onChange={event => setUserSortBy(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="created_at">Sort: created</option>
            <option value="name">Sort: name</option>
            <option value="last_login_at">Sort: last login</option>
          </select>
          <select aria-label="Sort direction" value={sortDirection} onChange={event => setSortDirection(event.target.value as 'asc' | 'desc')}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="desc">Newest / descending</option>
            <option value="asc">Oldest / ascending</option>
          </select>
          <button type="button" disabled={filteredUsers.length === 0}
            onClick={() => downloadCsv('accounts.csv',
              ['Account ID', 'Name', 'Email', 'Phone', 'Phone Verified At', 'Role', 'Status', 'Device Count', 'Created At', 'Last Login At'],
              filteredUsers.map(account => [
                account.id, account.name, account.email, account.phone_number, account.phone_verified_at,
                account.role,
                account.account_status, account.device_count, account.created_at, account.last_login_at,
              ]))}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">
            Export CSV ({filteredUsers.length})
          </button>
          <span className="text-xs text-slate-500">Showing {filteredUsers.length} of {userPage.total}{pageLoading ? ' · loading' : ''}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[850px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-5 py-3">Account</th>
                <th className="px-5 py-3">Phone</th>
                <th className="px-5 py-3">Role</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Devices</th>
                <th className="px-5 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredUsers.map(account => (
                <tr key={account.id}>
                  <td className="px-5 py-3">
                    <div className="font-semibold text-slate-900">{account.name}</div>
                    <div className="text-xs text-slate-500">{account.email}</div>
                  </td>
                  <td className="px-5 py-3">
                    <div>{account.phone_number || 'Not set'}</div>
                    {account.phone_number && (
                      <div className={`text-xs ${account.phone_verified_at ? 'text-emerald-700' : 'text-amber-700'}`}>
                        {account.phone_verified_at ? 'SMS verified' : 'Not verified'}
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    {user.role === 'SUPER_ADMIN' && account.id !== user.id ? (
                      <select aria-label={`Role for ${account.name}`} value={account.role} disabled={busy}
                        onChange={event => void updateAccount(account, { role: event.target.value as AdminUser['role'] })}
                        className="rounded border border-slate-300 px-2 py-1">
                        <option value="USER">USER</option>
                        <option value="ADMIN">ADMIN</option>
                        <option value="SUPER_ADMIN">SUPER_ADMIN</option>
                      </select>
                    ) : account.role}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${account.account_status === 'ACTIVE'
                      ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>
                      {account.account_status}
                    </span>
                  </td>
                  <td className="px-5 py-3">{account.device_count}</td>
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap gap-2">
                      {account.id !== user.id && account.role !== 'SUPER_ADMIN' && (
                        <button disabled={busy} onClick={() => void updateAccount(account, {
                          account_status: account.account_status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE',
                        })} className="text-xs font-semibold text-indigo-700 underline">
                          {account.account_status === 'ACTIVE' ? 'Suspend' : 'Reactivate'}
                        </button>
                      )}
                      {account.id !== user.id && (
                        <button disabled={busy} onClick={() => void loadAccountSessions(account)}
                          className="text-xs font-semibold text-indigo-700 underline">
                          Sessions
                        </button>
                      )}
                      {account.id !== user.id && (
                        <button disabled={busy} onClick={() => void issueInvitation(account)}
                          className="text-xs font-semibold text-emerald-700 underline">
                          Issue / reissue invite
                        </button>
                      )}
                      {user.role === 'SUPER_ADMIN' && account.id !== user.id && (
                        <button disabled={busy} onClick={() => void resetAuthenticator(account)}
                          className="text-xs font-semibold text-indigo-700 underline">
                          Reset authenticator
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filteredUsers.length === 0 && <tr><td className="px-5 py-6 text-slate-500" colSpan={6}>
                {userPage.total === 0 ? 'No accounts found.' : 'No accounts match these filters.'}
              </td></tr>}
            </tbody>
          </table>
        </div>
        <TablePagination
          pageIndex={userPageIndex}
          pageSize={PAGE_SIZE}
          total={userPage.total}
          onPageChange={setUserPageIndex}
        />
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-xl font-bold text-slate-900">Platform devices</h2>
          <p className="mt-1 text-sm text-slate-600">Inventory and health only; exact location data is intentionally excluded.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-5 py-4">
          <input value={deviceSearch} onChange={event => { setDeviceSearch(event.target.value); setDevicePageIndex(0); }}
            placeholder="Search device, owner, platform, model, or ID" aria-label="Search platform devices"
            className="min-w-56 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <select value={deviceStatusFilter} onChange={event => { setDeviceStatusFilter(event.target.value); setDevicePageIndex(0); }}
            aria-label="Filter devices by status" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All statuses</option>
            {deviceStatuses.map(status => <option key={status} value={status}>{status}</option>)}
          </select>
          <select value={deviceTypeFilter} onChange={event => { setDeviceTypeFilter(event.target.value); setDevicePageIndex(0); }}
            aria-label="Filter devices by type" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All device types</option>
            {deviceTypes.map(type => <option key={type} value={type}>{type}</option>)}
          </select>
          <select value={deviceLostModeFilter} onChange={event => { setDeviceLostModeFilter(event.target.value as 'ALL' | 'LOST' | 'NORMAL'); setDevicePageIndex(0); }}
            aria-label="Filter devices by lost mode" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All lost mode states</option>
            <option value="LOST">Lost mode</option>
            <option value="NORMAL">Normal mode</option>
          </select>
          <select aria-label="Sort devices by" value={deviceSortBy} onChange={event => setDeviceSortBy(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="created_at">Sort: registered</option>
            <option value="name">Sort: name</option>
            <option value="last_seen">Sort: last seen</option>
          </select>
          <button type="button" disabled={filteredDevices.length === 0}
            onClick={() => downloadCsv('devices.csv',
              ['Device ID', 'Device', 'Type', 'Platform', 'Model', 'Owner ID', 'Owner', 'Owner Phone', 'Status', 'Lost Mode', 'Battery Level', 'Last Seen', 'Created At'],
              filteredDevices.map(device => [
                device.id, device.name, device.device_type, device.platform, device.model,
                device.owner_user_id, device.owner_name, device.owner_phone_number, device.status,
                device.is_lost_mode ? 'Yes' : 'No', device.battery_level, device.last_seen, device.created_at,
              ]))}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">
            Export CSV ({filteredDevices.length})
          </button>
          <span className="text-xs text-slate-500">Showing {filteredDevices.length} of {devicePage.total}{pageLoading ? ' · loading' : ''}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-5 py-3">Device</th>
                <th className="px-5 py-3">Owner</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Battery</th>
                <th className="px-5 py-3">Last seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredDevices.map(device => (
                <tr key={device.id}>
                  <td className="px-5 py-3">
                    <div className="font-semibold text-slate-900">{device.name}</div>
                    <div className="text-xs text-slate-500">{device.platform || device.device_type}{device.model ? ` · ${device.model}` : ''}</div>
                  </td>
                  <td className="px-5 py-3">{device.owner_name}<div className="text-xs text-slate-500">{device.owner_phone_number}</div></td>
                  <td className="px-5 py-3">{device.status}{device.is_lost_mode ? ' · Lost mode' : ''}</td>
                  <td className="px-5 py-3">{device.battery_level == null ? '—' : `${device.battery_level}%`}</td>
                  <td className="px-5 py-3">{device.last_seen ? new Date(device.last_seen).toLocaleString() : '—'}</td>
                </tr>
              ))}
              {filteredDevices.length === 0 && <tr><td className="px-5 py-6 text-slate-500" colSpan={5}>
                {devicePage.total === 0 ? 'No devices registered.' : 'No devices match these filters.'}
              </td></tr>}
            </tbody>
          </table>
        </div>
        <TablePagination
          pageIndex={devicePageIndex}
          pageSize={PAGE_SIZE}
          total={devicePage.total}
          onPageChange={setDevicePageIndex}
        />
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-xl font-bold text-slate-900">Administrator audit log</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-5 py-4">
          <input value={auditSearch} onChange={event => { setAuditSearch(event.target.value); setAuditPageIndex(0); }}
            placeholder="Search action, details, IDs, or IP address" aria-label="Search audit log"
            className="min-w-56 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <select value={auditActionFilter} onChange={event => { setAuditActionFilter(event.target.value); setAuditPageIndex(0); }}
            aria-label="Filter audit log by action" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="ALL">All actions</option>
            {auditActions.map(action => <option key={action} value={action}>{action}</option>)}
          </select>
          <button type="button" disabled={filteredAudit.length === 0}
            onClick={() => downloadCsv('administrator-audit.csv',
              ['Event ID', 'Created At', 'Action', 'Actor User ID', 'Target User ID', 'Target Device ID', 'Details', 'IP Address'],
              filteredAudit.map(event => [
                event.id, event.created_at, event.action, event.actor_user_id, event.target_user_id,
                event.target_device_id, event.details, event.ip_address,
              ]))}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">
            Export CSV ({filteredAudit.length})
          </button>
          <span className="text-xs text-slate-500">Showing {filteredAudit.length} of {auditPage.total}{pageLoading ? ' · loading' : ''}</span>
        </div>
        <div className="divide-y divide-slate-100">
          {filteredAudit.map(event => (
            <div key={event.id} className="flex flex-wrap justify-between gap-2 px-5 py-3 text-sm">
              <div><span className="font-semibold text-slate-800">{event.action}</span>
                {event.details && <span className="ml-2 text-slate-500">{event.details}</span>}
                <div className="text-xs text-slate-500">Actor: {event.actor_user_id || 'unknown'}{event.target_user_id ? ` · Account: ${event.target_user_id}` : ''}</div>
              </div>
              <time className="text-xs text-slate-500">{new Date(event.created_at).toLocaleString()}</time>
            </div>
          ))}
          {filteredAudit.length === 0 && (
            <p className="px-5 py-6 text-sm text-slate-500">
              {auditPage.total === 0 ? 'No administrator events recorded.' : 'No audit events match these filters.'}
            </p>
          )}
        </div>
        <TablePagination
          pageIndex={auditPageIndex}
          pageSize={PAGE_SIZE}
          total={auditPage.total}
          onPageChange={setAuditPageIndex}
        />
      </section>

      {accountSessions && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
          <section role="dialog" aria-modal="true" aria-labelledby="account-sessions-title"
            className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="account-sessions-title" className="text-xl font-bold text-slate-900">
                  Active sessions · {accountSessions.user.name}
                </h2>
                <p className="mt-1 text-sm text-slate-600">Revocation takes effect on the next API request.</p>
              </div>
              <button type="button" onClick={() => setAccountSessions(null)}
                className="text-sm font-semibold text-slate-700 underline">Close</button>
            </div>
            <div className="mt-4 divide-y divide-slate-100">
              {accountSessions.sessions.map(session => (
                <div key={session.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0 text-sm">
                    <p className="font-semibold">
                      {session.revoked_at ? 'Revoked' : new Date(session.expires_at).getTime() <= Date.now() ? 'Expired' : 'Active'}
                      {' · '}{new Date(session.created_at).toLocaleString()}
                    </p>
                    <p className="text-xs text-slate-600">
                      Last seen {new Date(session.last_seen_at).toLocaleString()}
                      {session.ip_address ? ` · IP ${session.ip_address}` : ''}
                    </p>
                    {session.user_agent && <p className="break-all text-xs text-slate-500">{session.user_agent}</p>}
                  </div>
                  {!session.revoked_at && new Date(session.expires_at).getTime() > Date.now() && (
                    <button type="button" disabled={busy} onClick={() => void revokeAccountSession(session)}
                      className="text-sm font-semibold text-red-700 underline">Revoke</button>
                  )}
                </div>
              ))}
              {accountSessions.sessions.length === 0 && <p className="py-4 text-sm text-slate-500">No session records.</p>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function TablePagination({
  pageIndex,
  pageSize,
  total,
  onPageChange,
}: {
  pageIndex: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between border-t border-slate-200 px-5 py-3 text-sm">
      <span className="text-slate-500">Page {Math.min(pageIndex + 1, pages)} of {pages}</span>
      <div className="flex gap-2">
        <button type="button" disabled={pageIndex <= 0}
          onClick={() => onPageChange(Math.max(0, pageIndex - 1))}
          className="rounded border border-slate-300 px-3 py-1 font-semibold disabled:opacity-40">Previous</button>
        <button type="button" disabled={(pageIndex + 1) * pageSize >= total}
          onClick={() => onPageChange(pageIndex + 1)}
          className="rounded border border-slate-300 px-3 py-1 font-semibold disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
