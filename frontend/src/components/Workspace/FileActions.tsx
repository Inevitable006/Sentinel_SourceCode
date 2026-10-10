import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import { usePinAction } from './usePinAction';

type Action = { id: string; summary: string; status: 'done' | 'undone' | 'final'; created: number; undo_seconds_left: number };

// Recent file changes Sentinel made with your approval, with Undo while the window is open.
const FileActions: React.FC = () => {
  const [data, setData] = useState<{ folder: string; undo_minutes: number; actions: Action[] } | null>(null);
  const [message, setMessage] = useState('');
  const { run, prompt } = usePinAction(setMessage);
  const load = useCallback(() => {
    apiGet<typeof data>('/api/files/actions').then(setData).catch(e => setMessage(e.message));
  }, []);
  useEffect(() => { load(); const id = window.setInterval(load, 5000); return () => window.clearInterval(id); }, [load]);

  return (
    <>
      <p className="ws-muted">Sentinel can only change files in <code>{data?.folder}</code>. Every change is shown before you approve it and can be undone for {data?.undo_minutes} minutes; after that it is final.</p>
      <div role="status" aria-live="polite" className="ws-message">{message}</div>
      {prompt}
      {data?.actions.length === 0 && <p className="ws-muted">No file changes yet. Ask in chat, e.g. "Create notes/shopping.txt with milk and eggs".</p>}
      <ul className="ws-list">
        {data?.actions.map(a => (
          <li key={a.id} className="ws-item">
            <div className="ws-item-head">
              <span>{a.summary}</span>
              <span className="ws-badge">{a.status === 'done' ? `undo ${Math.floor(a.undo_seconds_left / 60)}:${String(a.undo_seconds_left % 60).padStart(2, '0')}` : a.status}</span>
              <span className="ws-muted">{new Date(a.created * 1000).toLocaleTimeString()}</span>
              {a.status === 'done' && a.undo_seconds_left > 0 && (
                <button type="button" onClick={() => run(async (pin?: string) => {
                  const r = await apiPost<{ message: string }>(`/api/files/actions/${a.id}/undo`, { pin });
                  setMessage(r.message); load();
                })}>Undo</button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
};

export default FileActions;
