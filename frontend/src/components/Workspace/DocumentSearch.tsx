import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';

type Result = { id: string; title: string; excerpt: string };

const DocumentSearch: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Result[] | null>(null);
  const [selected, setSelected] = useState<{ title: string; content: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true); setMessage(''); setSelected(null); setResults(null);
    try { setResults(await apiPost<Result[]>('/api/workspace/documents/search', { query })); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Search failed.'); }
    finally { setBusy(false); }
  };
  const open = async (id: string) => {
    setBusy(true); setMessage(''); setSelected(null);
    try { setSelected(await apiGet(`/api/workspace/documents/${encodeURIComponent(id)}`)); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not open the document.'); }
    finally { setBusy(false); }
  };

  return <section aria-label="Search saved documents">
    <p className="ws-muted">Search the documents saved here. All search words must match. The index stays in your encrypted storage.</p>
    <form onSubmit={search} className="ws-actions">
      <label>Search documents <input value={query} maxLength={300} disabled={busy}
        onChange={e => setQuery(e.target.value)} placeholder="Words from the title or content" /></label>
      <button type="submit" disabled={busy || !query.trim()}>{busy ? 'Loading…' : 'Search'}</button>
      {results && <button type="button" disabled={busy} onClick={() => { setResults(null); setSelected(null); setQuery(''); }}>Clear results</button>}
    </form>
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
