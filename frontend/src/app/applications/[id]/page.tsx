'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

function SeverityChip({ severity }: { severity: 'green' | 'amber' | 'red' }) {
  const cls = { green: 'chip-green', amber: 'chip-amber', red: 'chip-red' }[severity];
  const icons = { green: '✅', amber: '⚠️', red: '🚨' };
  return <span className={cls}>{icons[severity]} {severity.toUpperCase()}</span>;
}

const TABS = ['Summary', 'Documents', 'Extracted Fields', 'Findings', 'Decisions', 'Timeline'];

export default function ApplicationDetailPage() {
  const { id } = useParams();
  const [app, setApp] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('Summary');
  const [showDecisionForm, setShowDecisionForm] = useState(false);
  const [decisionType, setDecisionType] = useState<'recommend' | 'final'>('recommend');
  const [outcome, setOutcome] = useState('APPROVED');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState('');

  async function loadApp() {
    const res = await fetch(`${API_URL}/applications/${id}`, { credentials: 'include' });
    const data = await res.json();
    setApp(data.application);
    setLoading(false);
  }
  useEffect(() => { loadApp(); }, [id]);

  async function submitDecision() {
    setSubmitting(true);
    setMsg('');
    const endpoint = decisionType === 'recommend' ? 'recommend' : 'final';
    const res = await fetch(`${API_URL}/decisions/${endpoint}`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ applicationId: id, outcome, reason }),
    });
    const d = await res.json();
    if (!res.ok) setMsg(`❌ ${d.error}`);
    else { setMsg('✅ Decision recorded.'); setShowDecisionForm(false); loadApp(); }
    setSubmitting(false);
  }

  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="w-10 h-10 border-4 border-accent-500 border-t-transparent rounded-full animate-spin"></div></div>;
  if (!app) return <div className="min-h-screen flex items-center justify-center text-gray-500">Application not found.</div>;

  const reds = app.findings?.filter((f: any) => f.severity === 'red') || [];
  const ambers = app.findings?.filter((f: any) => f.severity === 'amber') || [];
  const greens = app.findings?.filter((f: any) => f.severity === 'green') || [];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="mb-6">
          <div className="text-sm text-gray-400 mb-1">Application · {app.id.slice(0, 8)}…</div>
          <h1 className="text-2xl font-bold">{app.applicant?.name}</h1>
          <p className="text-gray-500">{app.applicant?.email}</p>
        </div>

        {/* Summary Card */}
        <div className="card mb-6">
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <span className="chip-amber">{app.status?.replace(/_/g, ' ')}</span>
            {app.routing && <span className={app.routing === 'ESCALATE' ? 'chip-red' : app.routing === 'FAST_TRACK' ? 'chip-green' : 'chip-amber'}>{app.routing}</span>}
            {app.riskScore != null && <span className="text-sm font-semibold">Risk Score: <strong>{app.riskScore.toFixed(0)}/100</strong></span>}
          </div>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-xl"><div className="text-2xl font-bold text-red-600">{reds.length}</div><div className="text-xs text-red-500">Critical Issues</div></div>
            <div className="bg-amber-50 dark:bg-amber-900/20 p-3 rounded-xl"><div className="text-2xl font-bold text-amber-600">{ambers.length}</div><div className="text-xs text-amber-500">Warnings</div></div>
            <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-xl"><div className="text-2xl font-bold text-green-600">{greens.length}</div><div className="text-xs text-green-500">Checks Passed</div></div>
          </div>
        </div>

        {/* Tab nav */}
        <div className="flex gap-1 mb-6 bg-white dark:bg-gray-900 p-1 rounded-xl border overflow-x-auto">
          {TABS.map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${activeTab === tab ? 'bg-accent-600 text-white' : 'text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}`}>
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'Summary' && (
          <div className="space-y-4">
            {app.findings?.slice(0, 6).map((f: any) => (
              <div key={f.id} className="card">
                <div className="flex items-center gap-3 mb-2">
                  <SeverityChip severity={f.severity} />
                  <span className="font-medium text-sm">{f.check}</span>
                  <span className="text-xs text-gray-400 ml-auto">Module {f.module} · {(f.confidence * 100).toFixed(0)}% confidence</span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400">{f.reasonCode.replace(/_/g, ' ')}</p>
              </div>
            ))}
            {app.findings?.length === 0 && <div className="card text-center text-gray-400 py-8">No findings yet. Processing may still be running.</div>}
          </div>
        )}

        {activeTab === 'Documents' && (
          <div className="space-y-3">
            {app.documents?.map((doc: any) => (
              <div key={doc.id} className="card flex items-center gap-4">
                <div className="text-2xl">📄</div>
                <div className="flex-1">
                  <div className="font-medium">{doc.type.replace('_', ' ')}</div>
                  <div className="text-xs text-gray-400">SHA-256: {doc.sha256?.slice(0, 16)}…</div>
                </div>
                <span className={doc.status === 'VERIFIED' ? 'chip-green' : 'chip-amber'}>{doc.status}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'Extracted Fields' && (
          <div className="card overflow-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b"><th className="text-left pb-2 pr-4">Field</th><th className="text-left pb-2 pr-4">Value</th><th className="text-left pb-2 pr-4">Valid</th><th className="text-left pb-2">Confidence</th></tr></thead>
              <tbody>
                {app.documents?.flatMap((doc: any) => doc.extractedFields || []).map((f: any) => (
                  <tr key={f.id} className="border-b last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="py-2 pr-4 font-medium capitalize">{f.name.replace(/_/g, ' ')}</td>
                    <td className="py-2 pr-4 text-gray-600 dark:text-gray-400 font-mono text-xs">{f.value}</td>
                    <td className="py-2 pr-4">{f.valid ? <span className="chip-green">✓</span> : <span className="chip-red">✗</span>}</td>
                    <td className="py-2 text-gray-500">{(f.confidence * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'Findings' && (
          <div className="space-y-4">
            {app.findings?.map((f: any) => (
              <details key={f.id} className="card group">
                <summary className="flex items-center gap-3 cursor-pointer list-none">
                  <SeverityChip severity={f.severity} />
                  <span className="font-medium flex-1">{f.check}</span>
                  <span className="text-xs text-gray-400">Module {f.module}</span>
                </summary>
                <div className="mt-3 pt-3 border-t space-y-2">
                  <div className="text-sm"><strong>Reason:</strong> {f.reasonCode.replace(/_/g, ' ')}</div>
                  <div className="text-sm"><strong>Confidence:</strong> {(f.confidence * 100).toFixed(0)}%</div>
                  {f.evidenceJson && typeof f.evidenceJson === 'object' && (
                    <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg text-xs font-mono overflow-auto">{JSON.stringify(f.evidenceJson, null, 2)}</div>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}

        {activeTab === 'Decisions' && (
          <div className="space-y-4">
            {app.decisions?.map((d: any) => (
              <div key={d.id} className="card">
                <div className="flex items-center gap-3 mb-2">
                  <span className={d.kind === 'FINAL' ? 'chip-green' : 'chip-amber'}>{d.kind}</span>
                  <span className={d.outcome === 'APPROVED' ? 'chip-green' : d.outcome === 'REJECTED' ? 'chip-red' : 'chip-amber'}>{d.outcome}</span>
                  <span className="text-xs text-gray-400 ml-auto">{d.user?.name} ({d.user?.role})</span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400">{d.reason}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'Timeline' && (
          <div className="card"><p className="text-gray-400 text-sm text-center py-8">Timeline view will be populated as the application progresses.</p></div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-wrap gap-3 mt-6">
          <button onClick={() => { setDecisionType('recommend'); setShowDecisionForm(true); }}
            className="btn-primary">Recommend Approve / Reject</button>
          <button onClick={() => { setDecisionType('final'); setShowDecisionForm(true); }}
            className="bg-green-600 hover:bg-green-700 text-white font-semibold px-6 py-3 rounded-xl transition-colors">Final Decision (Manager)</button>
        </div>

        {msg && <div className="mt-4 p-3 rounded-xl bg-gray-100 dark:bg-gray-800 text-sm">{msg}</div>}

        {/* Decision Form */}
        {showDecisionForm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
            <div className="bg-white dark:bg-gray-900 rounded-2xl p-8 max-w-lg w-full shadow-2xl">
              <h2 className="text-xl font-bold mb-6">{decisionType === 'recommend' ? 'Recommend a Decision' : 'Final Decision'}</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Outcome</label>
                  <select value={outcome} onChange={e => setOutcome(e.target.value)} className="input">
                    <option value="APPROVED">Approve</option>
                    <option value="REJECTED">Reject</option>
                    <option value="MORE_DOCS_REQUESTED">Request More Documents</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Reason (required)</label>
                  <textarea value={reason} onChange={e => setReason(e.target.value)} className="input min-h-24" placeholder="Briefly explain your decision…" />
                </div>
                {decisionType === 'final' && (
                  <div className="bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 text-sm p-3 rounded-xl">
                    ⚠️ This is a final decision. You cannot be the same person who submitted the recommendation (maker-checker rule).
                  </div>
                )}
                <div className="flex gap-3">
                  <button onClick={submitDecision} disabled={submitting || !reason.trim()} className="btn-primary flex-1">
                    {submitting ? 'Submitting…' : 'Confirm Decision'}
                  </button>
                  <button onClick={() => setShowDecisionForm(false)} className="btn-secondary">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
