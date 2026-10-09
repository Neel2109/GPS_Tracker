import { Suspense, lazy, useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import type { User } from './types';
import { getAccessToken, clearTokens, authAPI } from './services/api';
import AppLayout from './components/AppLayout';

const Unlock = lazy(() => import('./pages/Unlock'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const DeviceDetails = lazy(() => import('./pages/DeviceDetails'));
const History = lazy(() => import('./pages/History'));
const Proximity = lazy(() => import('./pages/Proximity'));
const MobileTracker = lazy(() => import('./pages/MobileTracker'));
const Geofences = lazy(() => import('./pages/Geofences'));
const Alerts = lazy(() => import('./pages/Alerts'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));
const AccessRequests = lazy(() => import('./pages/AccessRequests'));
const PrivacySettings = lazy(() => import('./pages/PrivacySettings'));

export default function App() {
  const [user, setUser] = useState<User | null>(() => {
    const stored = localStorage.getItem('user');
    return stored ? JSON.parse(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getAccessToken();
    if (token) {
      authAPI.getMe()
        .then(u => {
          setUser(u as User);
          localStorage.setItem('user', JSON.stringify(u));
        })
        .catch(() => {
          clearTokens();
          setUser(null);
        })
        .finally(() => setLoading(false));
    } else {
      localStorage.removeItem('user');
      setUser(null);
      setLoading(false);
    }
  }, []);

  const handleUnlock = (u: User) => {
    setUser(u);
    localStorage.setItem('user', JSON.stringify(u));
  };

  const handleLogout = () => {
    authAPI.logout().catch(() => {});
    clearTokens();
    setUser(null);
  };

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        background: '#F5F5F7',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: '44px', height: '44px',
            border: '3px solid #E0E0E0',
            borderTopColor: '#6C5CE7',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 16px',
          }} />
          <p style={{ color: '#636E72', fontSize: '14px', fontFamily: "'Inter', sans-serif" }}>
            Loading TrackGuard...
          </p>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading TrackGuard…</div>}>
      <Routes>
        <Route path="/unlock" element={!user ? <Unlock onUnlock={handleUnlock} /> : <Navigate to="/dashboard" />} />
        <Route element={user ? <AppLayout user={user} onLogout={handleLogout} /> : <Navigate to="/unlock" />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/devices/:id" element={<DeviceDetails />} />
          <Route path="/history" element={<History />} />
          <Route path="/proximity" element={<Proximity />} />
          <Route path="/geofences" element={<Geofences />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/access-requests" element={<AccessRequests />} />
          <Route path="/privacy" element={<PrivacySettings />} />
          <Route
            path="/admin"
            element={
              user && (user.role === 'ADMIN' || user.role === 'SUPER_ADMIN')
                ? <AdminPanel user={user} />
                : <Navigate to="/dashboard" replace />
            }
          />
        </Route>
        <Route path="/tracker" element={<MobileTracker />} />
        <Route path="*" element={<Navigate to={user ? "/dashboard" : "/unlock"} />} />
      </Routes>
    </Suspense>
  );
}
