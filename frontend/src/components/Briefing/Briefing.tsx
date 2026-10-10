import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import '../Workspace/Workspace.css';

type Brief = {
  greeting: string; date: string;
  reminders: { due_today: { title: string; due_at: string; overdue: boolean }[]; open_tasks: number };
  plans: { title: string; status: string; note: string }[];
  portfolio: { available: boolean; value?: number; gain?: number; change?: number; change_pct?: number | null; previous_day?: string; note?: string };
  health: { summary: string; critical: number; alerts: number; top: string[] };
  backup: { due: boolean; note: string };
};

const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;

// What matters today, in one place. Read-only: nothing here acts on its own.
const Briefing: React.FC<{ go: (tab: string) => void }> = ({ go }) => {
  const [b, setB] = useState<Brief | null>(null);
  const [message, setMessage] = useState('');
  const load = useCallback(() => {
    apiGet<Brief>('/api/briefing').then(setB).catch(e => setMessage(e.message));
  }, []);
  useEffect(() => { load(); const id = window.setInterval(load, 60000); return () => window.clearInterval(id); }, [load]);
  if (!b) return <div className="ws-container glass-panel"><p className="ws-muted">{message || 'Preparing your briefing…'}</p></div>;

  const p = b.portfolio;
  return (
    <div className="ws-container glass-panel">
      <h2 style={{ margin: 0 }}>{b.greeting}</h2>
      <p className="ws-muted">{b.date}</p>
      <div className="ws-actions">
        <button type="button" onClick={() => apiPost('/api/briefing/read-aloud').then(() => setMessage('Reading aloud…')).catch(e => setMessage(e.message))}>Read aloud</button>
        <button type="button" onClick={load}>Refresh</button>
      </div>
      <div role="status" aria-live="polite" className="ws-message">{message}</div>

      <section className="ws-item">
        <strong>Today</strong>
        {b.reminders.due_today.length === 0 ? <span className="ws-muted">No reminders due today.</span> : (
          <ul>{b.reminders.due_today.map((r, i) => (
            <li key={i} className={r.overdue ? 'ws-bad' : ''}>{r.title} · {new Date(r.due_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}{r.overdue ? ' (overdue)' : ''}</li>))}</ul>
        )}
        <span className="ws-muted">{b.reminders.open_tasks} open task(s) in total.</span>
        <div className="ws-actions"><button type="button" onClick={() => go('workspace')}>Open Workspace</button></div>
      </section>

      {b.plans.length > 0 && (
        <section className="ws-item">
          <strong>Plans needing you</strong>
          <ul>{b.plans.map((pl, i) => <li key={i}>{pl.title}: {pl.note}</li>)}</ul>
        </section>
      )}

      <section className="ws-item">
        <strong>Money</strong>
        {!p.available ? <span className="ws-muted">{p.note}</span> : (
          <>
            <span>Portfolio {inr(p.value!)} · overall {p.gain! >= 0 ? 'gain' : 'loss'} <span className={p.gain! >= 0 ? 'ws-ok' : 'ws-bad'}>{inr(p.gain!)}</span></span>
            {p.change !== undefined && <span>Since {p.previous_day}: <span className={p.change >= 0 ? 'ws-ok' : 'ws-bad'}>{p.change >= 0 ? '+' : '−'}{inr(Math.abs(p.change))} ({p.change_pct}%)</span></span>}
            {p.note && <span className="ws-muted">{p.note}</span>}
          </>
        )}
        <div className="ws-actions"><button type="button" onClick={() => go('portfolio')}>Open Portfolio</button></div>
      </section>

      <section className={`ws-item ${b.health.critical ? 'ws-sev-critical' : b.health.alerts ? 'ws-sev-warning' : ''}`}>
        <strong>PC health</strong>
        <span>{b.health.summary}</span>
        {b.health.top.length > 0 && <ul>{b.health.top.map((t, i) => <li key={i}>{t}</li>)}</ul>}
        <div className="ws-actions"><button type="button" onClick={() => go('security')}>Open Security</button></div>
      </section>

      <section className={`ws-item ${b.backup.due ? 'ws-sev-warning' : ''}`}>
        <strong>Backup</strong>
        <span>{b.backup.note}</span>
        <div className="ws-actions"><button type="button" onClick={() => go('settings')}>Open Backup settings</button></div>
      </section>
    </div>
  );
};

export default Briefing;
