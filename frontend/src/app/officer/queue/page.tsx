'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

const ROUTING_STYLES: Record<string, { label: string; chip: string }> = {
  FAST_TRACK:     { label: '⚡ Fast Track',     chip: 'chip-green' },
  OFFICER_REVIEW: { label: '👤 Officer Review', chip: 'chip-amber' },
  ESCALATE:       { label: '🚨 Escalate',       chip: 'chip-red' },
};

export default function OfficerQueuePage() {
  const [applications, setApplications] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/applications/queue`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => { setApplications(d.applications || []); setTotal(d.total || 0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">Review Queue</h1>
            <p className="text-gray-500 mt-1">{total} application{total !== 1 ? 's' : ''} awaiting review</p>
          </div>
        </div>

        {loading ? (
          <div className="card text-center py-16">
            <div className="w-10 h-10 border-4 border-accent-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-gray-500">Loading queue…</p>
          </div>
        ) : applications.length === 0 ? (
          <div className="card text-center py-16">
            <div className="text-6xl mb-4">✅</div>
            <h2 className="text-xl font-semibold mb-2">All clear!</h2>
            <p className="text-gray-500">No applications are currently waiting for review.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {applications.map((app: any) => {
              const routing = app.routing ? ROUTING_STYLES[app.routing] : null;
              return (
                <Link key={app.id} href={`/applications/${app.id}`} className="card flex items-center gap-6 hover:shadow-md transition-shadow cursor-pointer no-underline group">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="font-semibold text-sm">{app.applicant?.name || 'Unknown'}</span>
                      {routing && <span className={routing.chip}>{routing.label}</span>}
                      <span className="chip-amber text-xs">{app.status.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="text-xs text-gray-400">{app.applicant?.email} · Submitted {new Date(app.createdAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {app.documents?.map((d: any) => (
                      <span key={d.id} className="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded-full">{d.type.replace('_', ' ')}</span>
                    ))}
                  </div>
                  <span className="text-gray-400 group-hover:text-accent-600 dark:group-hover:text-accent-400 text-lg">→</span>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
