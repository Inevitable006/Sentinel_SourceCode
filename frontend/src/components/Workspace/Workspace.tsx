import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import { usePinAction } from './usePinAction';
import './Workspace.css';

type Kind = 'task' | 'plan' | 'email_draft' | 'calendar_draft' | 'document';
type Step = { tool: string; args: Record<string, unknown> };
type Item = {
  id: string; kind: Kind; title: string; content: string; status: string; due_at: string | null;
  revision: string; payload: { steps?: Step[]; next?: number; results?: { status: string; data?: string; message?: string }[] };
};
type Tool = { name: string; description: string; risk_tier: number };

const LABELS: Record<Kind, string> = {
  task: 'Tasks', plan: 'Plans', email_draft: 'Email drafts', calendar_draft: 'Calendar drafts', document: 'Documents',
};

// Local "datetime-local" value -> ISO string with the user's timezone offset (the backend requires one).
function withTimezone(local: string): string | null {
  if (!local) return null;
  const d = new Date(local);
  return isNaN(d.getTime()) ? null : d.toISOString();
}
function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const Editor: React.FC<{ kind: Kind; item?: Item; tools: Tool[]; onSaved: () => void; onCancel: () => void; setMessage: (m: string) => void }> =
  ({ kind, item, tools, onSaved, onCancel, setMessage }) => {
  const [title, setTitle] = useState(item?.title ?? '');
  const [content, setContent] = useState(item?.content ?? '');
  const [due, setDue] = useState(toLocalInput(item?.due_at ?? null));
  const [steps, setSteps] = useState<{ tool: string; args: string }[]>(
    (item?.payload.steps ?? []).map(s => ({ tool: s.tool, args: JSON.stringify(s.args) })));

  const save = async () => {
    let parsed: Step[] = [];
    try {
      parsed = steps.map(s => ({ tool: s.tool, args: s.args.trim() ? JSON.parse(s.args) : {} }));
    } catch {
      setMessage('Each action needs its arguments as JSON, for example {"operation": "echo_text", "target": "hi"}.');
      return;
    }
    const body = { title, content, due_at: withTimezone(due), steps: parsed };
    try {
      if (item) await apiPost(`/api/workspace/items/${item.id}/update`, body);
      else await apiPost(`/api/workspace/items/${kind}`, body);
      setMessage('Saved.');
      onSaved();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not save.');
    }
  };

  return (
    <div className="ws-editor">
      <label>Title <input value={title} maxLength={160} onChange={e => setTitle(e.target.value)} /></label>
      {kind !== 'plan' && (
        <label>{kind === 'task' ? 'Notes' : 'Content'} <textarea rows={6} value={content} onChange={e => setContent(e.target.value)} /></label>
      )}
      {(kind === 'task' || kind === 'calendar_draft') && (
        <label>{kind === 'task' ? 'Remind me at' : 'When'} <input type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label>
      )}
      {kind === 'plan' && (
        <div className="ws-steps">
          <p className="ws-muted">Each action runs only when you approve it, one at a time.</p>
          {steps.map((s, i) => (
            <div key={i} className="ws-step">
              <select value={s.tool} onChange={e => setSteps(steps.map((x, j) => j === i ? { ...x, tool: e.target.value } : x))}>
                <option value="">Choose a tool…</option>
                {tools.map(t => <option key={t.name} value={t.name}>{t.name} (risk {t.risk_tier})</option>)}
              </select>
              <input placeholder='Arguments as JSON, e.g. {"query": "weather"}' value={s.args}
                     onChange={e => setSteps(steps.map((x, j) => j === i ? { ...x, args: e.target.value } : x))} />
              <button type="button" onClick={() => setSteps(steps.filter((_, j) => j !== i))}>Remove</button>
            </div>
          ))}
          <button type="button" onClick={() => setSteps([...steps, { tool: '', args: '' }])}>Add action</button>
        </div>
      )}
      <div className="ws-actions">
        <button type="button" onClick={save} disabled={!title.trim()}>Save</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
};

const PlanRunner: React.FC<{ item: Item; onDone: () => void; setMessage: (m: string) => void }> = ({ item, onDone, setMessage }) => {
  const [prepared, setPrepared] = useState<{ step: Step; risk: number; token: string; revision: string } | null>(null);
  const { run, prompt } = usePinAction(setMessage);
  const steps = item.payload.steps ?? [];
  const next = item.payload.next ?? 0;

  const prepare = async () => {
    try { setPrepared(await apiPost(`/api/workspace/plans/${item.id}/prepare`)); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not prepare the action.'); }
  };
  const approve = () => run(async (pin?: string) => {
    if (!prepared) return;
    const result = await apiPost<Item>(`/api/workspace/plans/${item.id}/run`, { token: prepared.token, revision: prepared.revision, pin });
    setPrepared(null);
    const last = result.payload.results?.[result.payload.results.length - 1];
    setMessage(last?.status === 'success' ? 'Action completed.' : `Action failed: ${last?.message ?? 'unknown error'}`);
    onDone();
  });

  return (
    <div className="ws-plan">
      <ol>
        {steps.map((s, i) => {
          const r = item.payload.results?.[i];
          return <li key={i} className={i < next ? 'ws-done' : ''}><code>{s.tool}</code> {JSON.stringify(s.args)}
            {r && <span className={r.status === 'success' ? 'ws-ok' : 'ws-bad'}> — {r.status === 'success' ? 'done' : `failed: ${r.message ?? ''}`}</span>}</li>;
        })}
      </ol>
      {item.status === 'interrupted' && (
        <p className="ws-bad">This plan was interrupted while an action was running; its outcome is unknown. Check before resuming.
          <button type="button" onClick={async () => { await apiPost(`/api/workspace/items/${item.id}/state`, { status: 'open' }); onDone(); }}>I checked, resume</button></p>
      )}
      {['open', 'ready'].includes(item.status) && next < steps.length && !prepared && (
        <button type="button" onClick={prepare}>Review next action</button>
      )}
      {prepared && (
        <div className="ws-approve">
          <p>Next: <code>{prepared.step.tool}</code> (risk {prepared.risk})</p>
          <pre>{JSON.stringify(prepared.step.args, null, 2)}</pre>
          <button type="button" onClick={approve}>Approve and run</button>
          <button type="button" onClick={() => setPrepared(null)}>Not now</button>
        </div>
      )}
      {prompt}
    </div>
  );
};

const Workspace: React.FC = () => {
  const [kind, setKind] = useState<Kind>('task');
  const [items, setItems] = useState<Item[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [editing, setEditing] = useState<Item | 'new' | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const { run, prompt } = usePinAction(setMessage);

  const load = useCallback(async () => {
    try { setItems(await apiGet<Item[]>(`/api/workspace/items/${kind}`)); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not load items.'); }
  }, [kind]);

  useEffect(() => { load(); setEditing(null); setOpen(null); }, [load]);
  useEffect(() => { apiGet<Tool[]>('/api/workspace/tools').then(setTools).catch(() => setTools([])); }, []);

  const setState = async (item: Item, status: 'open' | 'done' | 'cancelled') => {
    try { await apiPost(`/api/workspace/items/${item.id}/state`, { status }); load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not update.'); }
  };
  const remove = (item: Item) => run(async (pin?: string) => {
    await apiPost(`/api/workspace/items/${item.id}/delete`, { pin });
    setMessage('Deleted.'); load();
  });

  return (
    <div className="ws-container glass-panel">
      <div className="ws-tabs" role="tablist">
        {(Object.keys(LABELS) as Kind[]).map(k => (
          <button key={k} role="tab" aria-selected={k === kind} className={k === kind ? 'active' : ''} onClick={() => setKind(k)}>{LABELS[k]}</button>
        ))}
      </div>
      <div role="status" aria-live="polite" className="ws-message">{message}</div>
      {kind.endsWith('_draft') && <p className="ws-muted">Drafts stay on this PC. Sentinel never sends email or creates calendar events.</p>}
      {prompt}
      {editing ? (
        <Editor kind={kind} item={editing === 'new' ? undefined : editing} tools={tools} setMessage={setMessage}
                onSaved={() => { setEditing(null); load(); }} onCancel={() => setEditing(null)} />
      ) : (
        <>
          <button type="button" onClick={() => setEditing('new')}>New {LABELS[kind].replace(/s$/, '').toLowerCase()}</button>
          {items.length === 0 && <p className="ws-muted">Nothing here yet.</p>}
          <ul className="ws-list">
            {items.map(item => (
              <li key={item.id} className={`ws-item status-${item.status}`}>
                <div className="ws-item-head">
                  <button type="button" className="ws-link" onClick={() => setOpen(open === item.id ? null : item.id)}>{item.title}</button>
                  <span className="ws-badge">{item.status}</span>
                  {item.due_at && <span className="ws-muted">{new Date(item.due_at).toLocaleString()}</span>}
                </div>
                {open === item.id && (
                  <div className="ws-item-body">
                    {item.kind === 'plan' ? <PlanRunner item={item} onDone={load} setMessage={setMessage} />
                      : <pre className="ws-content">{item.content || '(empty)'}</pre>}
                    <div className="ws-actions">
                      {item.status !== 'running' && <button type="button" onClick={() => setEditing(item)}>Edit</button>}
                      {item.kind !== 'plan' && item.status !== 'done' && <button type="button" onClick={() => setState(item, 'done')}>Mark done</button>}
                      {item.kind !== 'plan' && item.status === 'done' && <button type="button" onClick={() => setState(item, 'open')}>Reopen</button>}
                      {!['cancelled', 'running', 'done'].includes(item.status) && <button type="button" onClick={() => setState(item, 'cancelled')}>Cancel</button>}
                      {item.status !== 'running' && <button type="button" onClick={() => remove(item)}>Delete</button>}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
};

export default Workspace;
