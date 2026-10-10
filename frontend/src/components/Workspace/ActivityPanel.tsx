import React, { useCallback, useEffect, useState } from 'react';
import { apiGet } from '../../lib/backend';

type Item = { time: number; action: string; from: string; approval: string; status: 'done' | 'failed' | 'blocked' | 'not_approved'; outcome: string };
type Activity = { days: number; items: Item[]; counts: Record<string, number>; integrity: { ok: boolean; message: string } };

const ICON: Record<Item['status'], string> = { done: '✓', failed: '✗', blocked: '⛔', not_approved: '–' };

// "What did Sentinel do?" — every action, who asked, whether you approved, how it ended.
const ActivityPanel: React.FC = () => {
  const [days, setDays] = useState(7);
  const [filter, setFilter] = useState<'all' | Item['status']>('all');
  const [data, setData] = useState<Activity | null>(null);
  const [message, setMessage] = useState('');
  const load = useCallback(() => {
    apiGet<Activity>(`/api/watch/activity?days=${days}`).then(setData).catch(e => setMessage(e.message));
  }, [days]);
  useEffect(() => { load(); }, [load]);

  const items = data?.items.filter(i => filter === 'all' || i.status === filter) ?? [];
  return (
    <section>
      <h3>What Sentinel did</h3>
      {data && <p className={data.integrity.ok ? 'ws-muted' : 'ws-bad'}>{data.integrity.message}</p>}
      <div className="ws-actions">
        <select value={days} onChange={e => setDays(Number(e.target.value))}>
          <option value={1}>Last 24 hours</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option>
        </select>
        <select value={filter} onChange={e => setFilter(e.target.value as typeof filter)}>
          <option value="all">Everything</option>
          <option value="done">Done ({data?.counts.done ?? 0})</option>
          <option value="failed">Failed ({data?.counts.failed ?? 0})</option>
          <option value="blocked">Blocked ({data?.counts.blocked ?? 0})</option>
          <option value="not_approved">Not approved ({data?.counts.not_approved ?? 0})</option>
        </select>
        <button type="button" onClick={load}>Refresh</button>
      </div>
      <div className="ws-message">{message}</div>
      {items.length === 0 && <p className="ws-muted">Nothing in this period.</p>}
      <ul className="ws-list">
        {items.map((i, n) => (
          <li key={n} className={`ws-item ${i.status === 'failed' || i.status === 'blocked' ? 'ws-sev-warning' : ''}`}>
            <div className="ws-item-head">
              <span aria-label={i.status}>{ICON[i.status]}</span>
              <strong>{i.action}</strong>
              <span className="ws-muted">{new Date(i.time * 1000).toLocaleString()}</span>
            </div>
            <span className="ws-muted">From {i.from} · {i.approval} · {i.outcome}</span>
          </li>
        ))}
      </ul>
      <p className="ws-muted">Only action names and results are recorded, never your search terms or file contents.</p>
    </section>
  );
};

export default ActivityPanel;
