import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import { usePinAction } from './usePinAction';
import './Workspace.css';

type Memory = { id: string; content: string; category: string | null };
type Thread = { id: string; title: string | null; created_at: string };
type Msg = { id: number; role: string; content: string };

// Memories Sentinel keeps about you, and past conversations (read-only).
const MemoryView: React.FC<{ onResume: (threadId: string) => void }> = ({ onResume }) => {
  const [tab, setTab] = useState<'memory' | 'history'>('memory');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [query, setQuery] = useState('');
  const [newMemory, setNewMemory] = useState('');
  const [threads, setThreads] = useState<Thread[]>([]);
  const [openThread, setOpenThread] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [message, setMessage] = useState('');
  const { run, prompt } = usePinAction(setMessage);

  const loadMemories = useCallback(async () => {
    try { setMemories(await apiGet<Memory[]>(`/api/workspace/memory?q=${encodeURIComponent(query)}`)); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not load memories.'); }
  }, [query]);

  useEffect(() => { if (tab === 'memory') loadMemories(); }, [tab, loadMemories]);
  useEffect(() => {
    if (tab === 'history') apiGet<Thread[]>('/api/workspace/history').then(setThreads).catch(e => setMessage(e.message));
  }, [tab]);
  useEffect(() => {
    if (openThread) apiGet<Msg[]>(`/api/workspace/history/${openThread}`).then(setMessages).catch(e => setMessage(e.message));
  }, [openThread]);

  return (
    <div className="ws-container glass-panel">
      <div className="ws-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'memory'} className={tab === 'memory' ? 'active' : ''} onClick={() => setTab('memory')}>Memories</button>
        <button role="tab" aria-selected={tab === 'history'} className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>Chat history</button>
      </div>
      <div role="status" aria-live="polite" className="ws-message">{message}</div>
      {prompt}
      {tab === 'memory' ? (
        <>
          <form className="ws-row" onSubmit={async e => {
            e.preventDefault();
            try { await apiPost('/api/workspace/memory', { content: newMemory }); setNewMemory(''); setMessage('Remembered.'); loadMemories(); }
            catch (err) { setMessage(err instanceof Error ? err.message : 'Not saved.'); }
          }}>
            <input placeholder="Something Sentinel should remember" value={newMemory} maxLength={4000} onChange={e => setNewMemory(e.target.value)} />
            <button type="submit" disabled={!newMemory.trim()}>Remember</button>
          </form>
          <input className="ws-search" placeholder="Search memories" value={query} onChange={e => setQuery(e.target.value)} />
          {memories.length === 0 && <p className="ws-muted">No memories.</p>}
          <ul className="ws-list">
            {memories.map(m => (
              <li key={m.id} className="ws-item">
                <span>{m.content}</span>
                <button type="button" onClick={() => run(async (pin?: string) => {
                  await apiPost(`/api/workspace/memory/${m.id}/delete`, { pin }); setMessage('Forgotten.'); loadMemories();
                })}>Forget</button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <ul className="ws-list">
          {threads.length === 0 && <p className="ws-muted">No conversations yet.</p>}
          {threads.map(t => (
            <li key={t.id} className="ws-item">
              <div className="ws-item-head">
                <button type="button" className="ws-link" onClick={() => setOpenThread(openThread === t.id ? null : t.id)}>
                  {t.title || 'Conversation'}</button>
                <span className="ws-muted">{new Date(t.created_at).toLocaleString()}</span>
                <button type="button" onClick={() => onResume(t.id)}>Continue in Console</button>
              </div>
              {openThread === t.id && (
                <div className="ws-item-body">
                  {messages.filter(m => m.role !== 'system').map(m => (
                    <p key={m.id} className={`ws-msg ws-msg-${m.role}`}><strong>{m.role === 'user' ? 'You' : 'Sentinel'}:</strong> {m.content}</p>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default MemoryView;
