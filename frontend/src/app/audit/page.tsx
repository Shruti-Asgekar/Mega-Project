'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

export default function AuditPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/audit/logs?limit=50`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => { setLogs(d.logs || []); setTotal(d.total || 0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Audit Trail</h1>
          <p className="text-gray-500 mt-1">{total} events recorded · Append-only · PII masked</p>
        </div>
        <div className="card overflow-auto">
          {loading ? (
            <div className="text-center py-12 text-gray-400">Loading logs…</div>
          ) : logs.length === 0 ? (
            <div className="text-center py-12 text-gray-400">No audit events yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-3 pr-4 font-medium">Time</th>
                  <th className="pb-3 pr-4 font-medium">User</th>
                  <th className="pb-3 pr-4 font-medium">Role</th>
                  <th className="pb-3 pr-4 font-medium">Action</th>
                  <th className="pb-3 font-medium">Application</th>
                </tr>
              </thead>
              <tbody>
                {logs.map(log => (
                  <tr key={log.id} className="border-b last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="py-2 pr-4 text-gray-400 whitespace-nowrap">{new Date(log.createdAt).toLocaleString('en-IN')}</td>
                    <td className="py-2 pr-4 font-medium">{log.user?.name}</td>
                    <td className="py-2 pr-4 text-gray-500">{log.user?.role}</td>
                    <td className="py-2 pr-4"><span className="font-mono text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">{log.action}</span></td>
                    <td className="py-2 text-gray-400 text-xs">{log.applicationId ? log.applicationId.slice(0, 8) + '…' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
