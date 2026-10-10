import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import { usePinAction } from './usePinAction';

type Alert = { id: string; severity: 'info' | 'warning' | 'critical'; title: string; detail: string; steps: string[]; first_seen: string };
type WatchStatus = {
  summary: string; alerts: Alert[]; last_run: number | null; collect_error: string | null; note: string;
  defender_scan: { running: boolean; result: string | null };
};

// Shows what System Watch noticed, with plain steps. It never claims the PC is safe.
const SystemWatchPanel: React.FC = () => {
  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [message, setMessage] = useState('');
  const [checking, setChecking] = useState(false);
  const { run, prompt } = usePinAction(setMessage);

  const load = useCallback(async () => {
    try { setStatus(await apiGet<WatchStatus>('/api/watch/status')); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not load System Watch.'); }
  }, []);
  useEffect(() => {
    load();
    const id = window.setInterval(load, 30000);
    return () => window.clearInterval(id);
  }, [load]);

  const checkNow = async () => {
    setChecking(true);
    try { await apiPost('/api/watch/check'); setMessage('Check finished.'); await load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Check failed.'); }
    finally { setChecking(false); }
  };

  const critical = status?.alerts.some(a => a.severity === 'critical');
  return (
    <section className={`ws-watch ${critical ? 'ws-watch-critical' : ''}`}>
      <h3>System Watch</h3>
      <p><strong>{status?.summary ?? 'Loading…'}</strong>
        {status?.last_run ? <span className="ws-muted"> · last check {new Date(status.last_run * 1000).toLocaleTimeString()}</span> : null}</p>
      {status?.collect_error && <p className="ws-bad">Some checks could not run: {status.collect_error}</p>}
      <div role="status" aria-live="polite" className="ws-message">{message}</div>
      {prompt}
      <div className="ws-actions">
        <button type="button" onClick={checkNow} disabled={checking}>{checking ? 'Checking…' : 'Check now'}</button>
        <button type="button" disabled={status?.defender_scan.running} onClick={() => run(async (pin?: string) => {
          await apiPost('/api/watch/defender-scan', { pin });
          setMessage('Windows Defender quick scan started. This can take a few minutes.'); load();
        })}>{status?.defender_scan.running ? 'Defender scan running…' : 'Run Defender quick scan'}</button>
      </div>
      {status?.defender_scan.result && <p className="ws-muted">{status.defender_scan.result}</p>}
      <ul className="ws-list">
        {status?.alerts.map(a => (
          <li key={a.id} className={`ws-item ws-sev-${a.severity}`}>
            <div className="ws-item-head"><span className="ws-badge">{a.severity}</span><strong>{a.title}</strong></div>
            {a.detail && <pre className="ws-content">{a.detail}</pre>}
            <ol>{a.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            <div className="ws-actions">
              <button type="button" onClick={() => run(async (pin?: string) => {
                await apiPost(`/api/watch/alerts/${encodeURIComponent(a.id)}/accept`, { pin });
                setMessage('Marked as fine.'); load();
              })}>This is fine</button>
            </div>
          </li>
        ))}
      </ul>
      <p className="ws-muted">{status?.note}</p>
    </section>
  );
};

export default SystemWatchPanel;
