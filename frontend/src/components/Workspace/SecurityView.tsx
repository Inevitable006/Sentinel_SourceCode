import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost, notifyLockStateChanged } from '../../lib/backend';
import { usePinAction } from './usePinAction';
import SystemWatchPanel from './SystemWatchPanel';
import './Workspace.css';

type Skill = { name: string; description: string; enabled: boolean; execution: string; capabilities: string[] };
type Privacy = {
  counts: Record<string, number>; storage: string; audio: string; integrations: string;
  network: { offline: boolean; allowed_total: number; blocked_total: number };
};

// What Sentinel stores, which skills may run, and an emergency stop.
const SecurityView: React.FC = () => {
  const [privacy, setPrivacy] = useState<Privacy | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [message, setMessage] = useState('');
  const [confirmStop, setConfirmStop] = useState(false);
  const { run, prompt } = usePinAction(setMessage);

  const load = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([apiGet<Privacy>('/api/workspace/privacy'), apiGet<Skill[]>('/api/workspace/skills')]);
      setPrivacy(p); setSkills(s);
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Could not load.'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="ws-container glass-panel">
      <SystemWatchPanel />
      <h3>Privacy</h3>
      <div role="status" aria-live="polite" className="ws-message">{message}</div>
      {prompt}
      {privacy && (
        <dl className="ws-facts">
          {Object.entries(privacy.counts).map(([k, v]) => <React.Fragment key={k}><dt>{k.replace('_', ' ')}</dt><dd>{v}</dd></React.Fragment>)}
          <dt>Storage</dt><dd>{privacy.storage}</dd>
          <dt>Audio</dt><dd>{privacy.audio}</dd>
          <dt>Internet</dt><dd>{privacy.network.offline ? 'Offline mode (all outbound requests blocked)' : `Allowed for approved tools · ${privacy.network.allowed_total} allowed, ${privacy.network.blocked_total} blocked`}</dd>
          <dt>Accounts</dt><dd>{privacy.integrations}</dd>
        </dl>
      )}

      <h3>Skills</h3>
      <p className="ws-muted">Skills run inside the Sentinel backend; turning one off blocks all of its tools.</p>
      <ul className="ws-list">
        {skills.map(s => (
          <li key={s.name} className="ws-item">
            <div className="ws-item-head">
              <strong>{s.name}</strong>
              <span className="ws-badge">{s.enabled ? 'on' : 'off'}</span>
              <button type="button" onClick={() => run(async (pin?: string) => {
                await apiPost(`/api/workspace/skills/${s.name}`, { enabled: !s.enabled, pin });
                setMessage(`${s.name} turned ${s.enabled ? 'off' : 'on'}.`); load();
              })}>{s.enabled ? 'Turn off' : 'Turn on'}</button>
            </div>
            <p className="ws-muted">{s.description} {s.capabilities.length ? `Needs: ${s.capabilities.join(', ')}.` : ''}</p>
          </li>
        ))}
      </ul>

      <h3>Emergency stop</h3>
      <p className="ws-muted">Stops running actions, unloads the model, turns on Offline mode, pauses Sentinel and locks it.</p>
      {confirmStop ? (
        <div className="ws-actions">
          <button type="button" className="ws-danger" onClick={async () => {
            try { await apiPost('/api/workspace/emergency-stop'); } catch { /* locking closes the connection */ }
            notifyLockStateChanged();
          }}>Stop everything now</button>
          <button type="button" onClick={() => setConfirmStop(false)}>Cancel</button>
        </div>
      ) : <button type="button" className="ws-danger" onClick={() => setConfirmStop(true)}>Emergency stop…</button>}
    </div>
  );
};

export default SecurityView;
