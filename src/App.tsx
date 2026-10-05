import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import type { User } from './types';
import { getAccessToken, clearTokens, authAPI } from './services/api';
import Unlock from './pages/Unlock';
import Dashboard from './pages/Dashboard';
import DeviceDetails from './pages/DeviceDetails';
import History from './pages/History';
import AppLayout from './components/AppLayout';

export default function App() {
  const [user, setUser] = useState<User | null>(() => {
    const stored = localStorage.getItem('user');
    return stored ? JSON.parse(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getAccessToken();
    if (token && !user) {
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
    <Routes>
      <Route path="/unlock" element={!user ? <Unlock onUnlock={handleUnlock} /> : <Navigate to="/dashboard" />} />
      <Route element={user ? <AppLayout user={user} onLogout={handleLogout} /> : <Navigate to="/unlock" />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/devices/:id" element={<DeviceDetails />} />
        <Route path="/history" element={<History />} />
      </Route>
      <Route path="*" element={<Navigate to={user ? "/dashboard" : "/unlock"} />} />
    </Routes>
  );
}
