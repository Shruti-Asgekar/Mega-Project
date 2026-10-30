'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

type AppStatus = 'DRAFT' | 'SUBMITTED' | 'PROCESSING' | 'NEEDS_REVIEW' | 'RECOMMENDED' | 'APPROVED' | 'REJECTED' | 'MORE_DOCS_REQUESTED';

const STATUS_INFO: Record<AppStatus, { label: string; color: string; desc: string }> = {
  DRAFT:               { label: 'Draft',                color: 'chip-amber', desc: 'Your application is saved but not submitted yet.' },
  SUBMITTED:           { label: 'Submitted',            color: 'chip-amber', desc: 'We received your application and are processing it.' },
  PROCESSING:          { label: 'Processing',           color: 'chip-amber', desc: 'Our system is reading and checking your documents.' },
  NEEDS_REVIEW:        { label: 'Under Review',         color: 'chip-amber', desc: 'A loan officer is reviewing your application.' },
  RECOMMENDED:         { label: 'Recommendation Made',  color: 'chip-amber', desc: 'The officer has made a recommendation. Awaiting final decision.' },
  APPROVED:            { label: 'Approved ✅',           color: 'chip-green', desc: 'Congratulations! Your loan has been approved.' },
  REJECTED:            { label: 'Rejected',             color: 'chip-red',   desc: 'Your loan application was not approved this time.' },
  MORE_DOCS_REQUESTED: { label: 'More Documents Needed', color: 'chip-amber', desc: 'The officer needs additional documents from you.' },
};

export default function MyApplicationPage() {
  const [applications, setApplications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API_URL}/applications/my`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => setApplications(d.applications || []))
      .catch(() => setError('Could not load your application. Please refresh.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-accent-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-500">Loading your application…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">My Loan Application</h1>
          <Link href="/apply" className="btn-primary text-sm py-2 px-4">+ New Application</Link>
        </div>

        {error && <div className="bg-red-50 text-red-700 p-4 rounded-xl mb-6">{error}</div>}

        {applications.length === 0 ? (
          <div className="card text-center py-16">
            <div className="text-6xl mb-4">📄</div>
            <h2 className="text-xl font-semibold mb-2">No application yet</h2>
            <p className="text-gray-500 mb-6">Start your loan application and upload your KYC documents.</p>
            <Link href="/apply" className="btn-primary">Apply Now</Link>
          </div>
        ) : (
          <div className="space-y-4">
            {applications.map((app: any) => {
              const info = STATUS_INFO[app.status as AppStatus] || { label: app.status, color: 'chip-amber', desc: '' };
              return (
                <div key={app.id} className="card">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="text-xs text-gray-400 mb-1">Application ID: {app.id.slice(0, 8)}…</div>
                      <span className={info.color}>{info.label}</span>
                    </div>
                    <div className="text-xs text-gray-400">{new Date(app.createdAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</div>
                  </div>
                  <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">{info.desc}</p>
                  <div>
                    <div className="text-sm font-medium mb-2">Documents uploaded</div>
                    {app.documents.length === 0 ? (
                      <p className="text-sm text-gray-400">No documents uploaded yet.</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {app.documents.map((doc: any) => (
                          <span key={doc.id} className="chip-green">{doc.type.replace('_', ' ')}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
