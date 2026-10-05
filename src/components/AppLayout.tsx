import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import type { User } from '../types';

export interface DashboardSearchContext {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

interface Props {
  user: User;
  onLogout: () => void;
}

export default function AppLayout({ user, onLogout }: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();

  const navItems = [
    { to: '/dashboard', icon: <DashIcon />, label: 'Dashboard' },
    { to: '/history', icon: <HistIcon />, label: 'Location history' },
  ];

  return (
    <div className="tg-app-shell">
      {/* ── Mobile overlay ── */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/20 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      <div className="tg-app-frame">
        <nav className={`tg-sidebar ${mobileOpen ? 'tg-sidebar-open' : ''}`}>
          <button onClick={() => navigate('/dashboard')} className="tg-brand" aria-label="TrackGuard home">
            <span className="tg-brand-mark"><ShieldIcon /></span>
            <span>Track<span>Guard</span></span>
          </button>
          <div className="tg-nav-list">
            {navItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  `tg-nav-link ${isActive ? 'tg-nav-link-active' : ''}`
                }
                title={item.label}
                aria-label={item.label}
              >
                {item.icon}
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
          <button onClick={onLogout} className="tg-nav-link tg-logout-link" title="Lock TrackGuard" aria-label="Lock TrackGuard">
            <LogoutIcon />
            <span>Lock app</span>
          </button>
        </nav>

        <div className="tg-app-content">
          <header className="tg-app-topbar">
            <button onClick={() => setMobileOpen(true)} className="tg-menu-button" aria-label="Open navigation">
              <MenuIcon />
            </button>
            <div className="tg-search-wrap">
              <SearchIcon className="tg-search-icon" />
              <input
                type="search"
                value={searchQuery}
                onChange={event => setSearchQuery(event.target.value)}
                placeholder="Search device name, IP, MAC or location..."
                aria-label="Search devices by name or IP address"
                className="tg-search-input"
              />
            </div>
            <div className="tg-topbar-spacer" />
            <div className="tg-account">
              <button onClick={onLogout} className="tg-notification" title="Lock TrackGuard" aria-label="Lock TrackGuard">
                <BellIcon />
              </button>
              <div className="tg-avatar">
                {user.name.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <span className="tg-account-name">{user.name}<small>Account</small></span>
              <ChevronIcon />
            </div>
          </header>
          <main className="tg-main">
            <Outlet context={{ searchQuery, setSearchQuery } satisfies DashboardSearchContext} />
          </main>
        </div>
      </div>
    </div>
  );
}

/* ─── SVG Icons ─────────────────────────────────────────────── */

function DashIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z" />
    </svg>
  );
}

function HistIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v5h5M4.5 15a8 8 0 1 0 .7-6.8L3 8" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function SearchIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#636E72" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#B2BEC3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}
