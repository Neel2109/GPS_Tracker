import { useState } from 'react';
import type { AuthResponse, User } from '../types';
import { authAPI, setTokens } from '../services/api';

interface Props { onUnlock: (user: User) => void; }

export default function Unlock({ onUnlock }: Props) {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res: AuthResponse = await authAPI.unlock(pin);
      setTokens(res.access_token, res.refresh_token);
      onUnlock(res.user);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not unlock TrackGuard');
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = !loading && pin.length >= 6;

  return (
    <div
      style={{
        width: '100%',
        flex: 1,
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        backgroundImage: 'url(/auth-bg.png)',
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        position: 'relative',
      }}
    >
      {/* Dark overlay for readability */}
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.15)' }} />

      <div style={{ width: '100%', maxWidth: '420px', position: 'relative', zIndex: 1 }}>
        {/* Glass Card */}
        <div
          style={{
            background: 'rgba(255, 255, 255, 0.12)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            border: '1px solid rgba(255, 255, 255, 0.25)',
            borderRadius: '24px',
            padding: '40px 36px',
            boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          }}
          className="animate-in"
        >
          <h1 style={{ fontFamily: "'Poppins', sans-serif", fontSize: '28px', fontWeight: 700, color: '#fff', marginBottom: '6px' }}>
            TrackGuard
          </h1>
          <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.7)', marginBottom: '32px' }}>
            Enter your PIN to continue.
          </p>

          {error && (
            <div style={{
              padding: '12px 16px', borderRadius: '14px', marginBottom: '20px',
              background: 'rgba(215, 65, 65, 0.4)', border: '1px solid rgba(255, 100, 100, 0.3)',
              color: '#FFF', fontSize: '14px', fontWeight: 500,
            }} className="animate-scale">
              {error}
            </div>
          )}
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '24px' }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                background: '#FFFFFF', border: '1px solid rgba(255,255,255,0.8)',
                borderRadius: '14px', padding: '0 16px', transition: 'all 0.2s',
              }}>
                <input
                  id="unlock-phone-number"
                  type="password"
                  inputMode="numeric"
                  autoComplete="current-password"
                  pattern="[0-9]{6,12}"
                  maxLength={12}
                  value={pin}
                  onChange={e => setPin(e.target.value.replace(/\D/g, '').slice(0, 12))}
                  required
                  placeholder="Enter PIN"
                  aria-label="PIN"
                  style={{
                    flex: 1, background: 'transparent', border: 'none', outline: 'none',
                    padding: '14px 0', fontSize: '14px', color: '#1A1A1A',
                    fontFamily: "'Inter', sans-serif", letterSpacing: '0.2em',
                  }}
                />
              </div>
            </div>
            <button
              id="unlock-submit"
              type="submit"
              disabled={!canSubmit}
              style={{
                width: '100%', padding: '15px', borderRadius: '14px',
                background: '#688A4E',
                border: 'none',
                color: '#fff', fontSize: '15px', fontWeight: 600,
                cursor: canSubmit ? 'pointer' : 'not-allowed',
                opacity: canSubmit ? 1 : 0.6,
                transition: 'all 0.2s ease',
                fontFamily: "'Inter', sans-serif",
              }}
            >
              {loading ? 'Verifying...' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
