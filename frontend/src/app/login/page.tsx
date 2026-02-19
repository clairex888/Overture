'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Activity, LogIn, UserPlus, AlertTriangle, Loader2 } from 'lucide-react';
import { useAuth } from '@/components/providers/AuthProvider';

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register(email, password, displayName || undefined);
      }
      router.push('/');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Authentication failed';
      // Extract detail from API error
      try {
        const parsed = JSON.parse(msg.replace(/^API error \d+: /, ''));
        setError(parsed.detail || msg);
      } catch {
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-900 px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-info to-accent flex items-center justify-center mb-4">
            <Activity className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-text-primary">Overture</h1>
          <p className="text-sm text-text-muted mt-1">AI Hedge Fund Platform</p>
        </div>

        {/* Card */}
        <div className="bg-dark-800 border border-white/[0.08] rounded-2xl p-8">
          {/* Tab toggle */}
          <div className="flex gap-1 mb-6 p-1 bg-dark-700 rounded-lg">
            <button
              onClick={() => { setMode('login'); setError(null); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                mode === 'login'
                  ? 'bg-dark-600 text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setMode('register'); setError(null); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                mode === 'register'
                  ? 'bg-dark-600 text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-1.5">
                  Display Name
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name (optional)"
                  className="w-full bg-dark-700 border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50 transition-colors"
                />
              </div>
            )}

            <div>
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-1.5">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-dark-700 border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50 transition-colors"
                autoComplete="email"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-1.5">
                Password
              </label>
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min 6 characters"
                className="w-full bg-dark-700 border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50 transition-colors"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-loss/10 border border-loss/20">
                <AlertTriangle className="w-4 h-4 text-loss flex-shrink-0" />
                <span className="text-xs text-loss">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                submitting
                  ? 'bg-info/50 text-white/70 cursor-not-allowed'
                  : 'bg-info hover:bg-info/90 text-white shadow-lg shadow-info/20'
              }`}
            >
              {submitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : mode === 'login' ? (
                <LogIn className="w-4 h-4" />
              ) : (
                <UserPlus className="w-4 h-4" />
              )}
              {submitting
                ? 'Please wait...'
                : mode === 'login'
                ? 'Sign In'
                : 'Create Account'}
            </button>
          </form>

          {mode === 'login' && (
            <div className="mt-6 pt-4 border-t border-white/[0.06]">
              <p className="text-xs text-text-muted text-center">
                Master account:{' '}
                <button
                  type="button"
                  onClick={() => {
                    setEmail('admin@overture.ai');
                    setPassword('admin123');
                  }}
                  className="text-info hover:underline"
                >
                  auto-fill credentials
                </button>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
