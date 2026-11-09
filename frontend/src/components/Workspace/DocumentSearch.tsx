import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../../lib/backend';

type Result = { id: string; title: string; excerpt: string };
type IndexStatus = { installed: boolean; documents: number; indexed: number; pending: number; busy: boolean };

const DocumentSearch: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Result[] | null>(null);
  const [selected, setSelected] = useState<{ title: string; content: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [semanticBusy, setSemanticBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [mode, setMode] = useState('keyword');
  const [index, setIndex] = useState<IndexStatus | null>(null);
  const refresh = () => apiGet<IndexStatus>('/api/workspace/documents-index/status').then(setIndex).catch(() => setIndex(null));
  useEffect(() => { refresh(); }, []);
  const indexNext = async () => {
    setBusy(true); setSemanticBusy(true); setMessage('Preparing one document for meaning search…');
    try {
      setIndex(await apiPost<IndexStatus>('/api/workspace/documents-index/next'));
      setMessage('Document index updated.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Indexing failed.'); }
    finally { setBusy(false); setSemanticBusy(false); refresh(); }
  };

  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true); setMessage(''); setSelected(null); setResults(null);
    setSemanticBusy(mode === 'semantic');
    try { setResults(await apiPost<Result[]>('/api/workspace/documents/search', { query, mode })); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Search failed.'); }
    finally { setBusy(false); setSemanticBusy(false); refresh(); }
  };
  const open = async (id: string) => {
    setBusy(true); setMessage(''); setSelected(null);
    try { setSelected(await apiGet(`/api/workspace/documents/${encodeURIComponent(id)}`)); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not open the document.'); }
    finally { setBusy(false); }
  };

  return <section aria-label="Search saved documents">
    <p className="ws-muted">Search saved documents by words or meaning. Search stays on this PC; the index stays encrypted.</p>
    {index && <div className="ws-actions">
      <span>{index.indexed} of {index.documents} documents ready for meaning search (English).</span>
      <button type="button" disabled={busy || !index.installed || !index.pending} onClick={indexNext}>Prepare next document</button>
      <button type="button" disabled={busy} onClick={refresh}>Check index</button>
      {!index.installed && <span>Local search model missing. See the setup guide.</span>}
    </div>}
    {semanticBusy && <button type="button" onClick={async () => {
      try { await apiPost('/api/workspace/documents-index/cancel'); setMessage('Cancellation requested. Finishing the current local operation.'); }
      catch (e) { setMessage(e instanceof Error ? e.message : 'Could not cancel.'); }
    }}>Cancel search or indexing</button>}
    <form onSubmit={search} className="ws-actions">
      <label>Search method <select value={mode} disabled={busy} onChange={e => { setMode(e.target.value); setResults(null); setSelected(null); }}>
        <option value="keyword">All words</option><option value="semantic">Meaning (English)</option>
      </select></label>
      <label>Search documents <input value={query} maxLength={300} disabled={busy}
        onChange={e => setQuery(e.target.value)} placeholder="Words from the title or content" /></label>
      <button type="submit" disabled={busy || !query.trim()}>{busy ? 'Loading…' : 'Search'}</button>
      {results && <button type="button" disabled={busy} onClick={() => { setResults(null); setSelected(null); setQuery(''); }}>Clear results</button>}
    </form>
    {mode === 'semantic' && <p className="ws-muted">Meaning search covers prepared documents only and can return weak matches. Check the source before relying on it. Editing a document requires preparing it again.</p>}
    <p role="status" aria-live="polite">{message || (results ? `${results.length} matches${results.length === 20 ? ' (first 20 shown)' : ''}.` : '')}</p>
    {results && <ul className="ws-list">{results.map(result => <li key={result.id} className="ws-item">
      <button type="button" className="ws-link" disabled={busy} onClick={() => open(result.id)}>{result.title}</button>
      <p style={{ whiteSpace: 'pre-wrap' }}>{result.excerpt}</p>
    </li>)}</ul>}
    {selected && <div className="ws-item">
      <h3>{selected.title}</h3><pre className="ws-content">{selected.content}</pre>
      <button type="button" onClick={() => setSelected(null)}>Close document</button>
    </div>}
  </section>;
};

export default DocumentSearch;
