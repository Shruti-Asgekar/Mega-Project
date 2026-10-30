'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

const DEMO_ACCOUNTS = [
  { role: 'Applicant', email: 'applicant@kyc.local', password: 'Demo@1234', emoji: '🙋', description: 'Apply for a loan, upload documents, track status' },
  { role: 'Loan Officer', email: 'officer@kyc.local', password: 'Demo@1234', emoji: '👤', description: 'Review applications, submit recommendations' },
  { role: 'Credit Manager', email: 'manager@kyc.local', password: 'Demo@1234', emoji: '👔', description: 'Final approval / rejection (maker-checker)' },
  { role: 'Fraud Analyst', email: 'fraud@kyc.local', password: 'Demo@1234', emoji: '🔎', description: 'Inspect fraud ring graph, flag clusters' },
  { role: 'Auditor', email: 'auditor@kyc.local', password: 'Demo@1234', emoji: '📋', description: 'Read-only audit trail and masked logs' },
  { role: 'Admin', email: 'admin@kyc.local', password: 'Demo@1234', emoji: '⚙️', description: 'Manage users and roles' },
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleLogin(e?: React.FormEvent, overrideEmail?: string, overridePassword?: string) {
    e?.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: overrideEmail ?? email, password: overridePassword ?? password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Login failed');
      const role = data.user.role;
      if (role === 'APPLICANT') router.push('/my-application');
      else if (role === 'OFFICER') router.push('/officer/queue');
      else if (role === 'MANAGER') router.push('/manager/approvals');
      else if (role === 'FRAUD_ANALYST') router.push('/fraud/graph');
      else if (role === 'AUDITOR') router.push('/audit');
      else router.push('/admin/users');
    } catch (err: any) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-accent-50 to-blue-100 dark:from-gray-950 dark:to-gray-900 p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-accent-700 dark:text-accent-400 mb-2">KYC Loan Platform</h1>
          <p className="text-gray-600 dark:text-gray-400">Sign in to continue</p>
        </div>

        {/* Login Form */}
        <div className="card mb-6">
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2" htmlFor="email">Email address</label>
              <input
                id="email" type="email" required value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="input" autoComplete="email"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2" htmlFor="password">Password</label>
              <input
                id="password" type="password" required value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="input" autoComplete="current-password"
              />
            </div>
            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm p-3 rounded-xl">
                {error}
              </div>
            )}
            <button type="submit" className="btn-primary w-full" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        {/* Demo Accounts */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-lg">🧪</span>
            <h2 className="font-semibold text-sm">Demo accounts — synthetic data only</h2>
          </div>
          <div className="space-y-2">
            {DEMO_ACCOUNTS.map(acc => (
              <button
                key={acc.email}
                onClick={() => handleLogin(undefined, acc.email, acc.password)}
                disabled={loading}
                className="w-full flex items-start gap-3 p-3 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left group border border-transparent hover:border-gray-200 dark:hover:border-gray-700"
              >
                <span className="text-2xl mt-0.5">{acc.emoji}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{acc.role}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{acc.description}</div>
                  <div className="text-xs text-accent-600 dark:text-accent-400 mt-0.5">{acc.email}</div>
                </div>
                <span className="text-gray-400 group-hover:text-accent-600 dark:group-hover:text-accent-400 text-sm mt-1">→</span>
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-600 mt-3 text-center">Password for all demo accounts: Demo@1234</p>
        </div>
      </div>
    </div>
  );
}
