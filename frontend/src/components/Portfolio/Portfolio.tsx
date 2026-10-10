import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost, backendInfo } from '../../lib/backend';
import { usePinAction } from '../Workspace/usePinAction';
import '../Workspace/Workspace.css';

type Profile = { risk: 'conservative' | 'moderate' | 'aggressive'; horizon_years: number; monthly_amount: number;
  monthly_expenses: number; emergency_fund: number; goal: string; set?: boolean };
type HoldingIn = { kind: 'mf' | 'stock' | 'other'; name: string; symbol: string; isin: string; units: number; avg_cost: number;
  buy_date: string | null; category: 'equity' | 'debt' | 'hybrid' | 'gold' };
type HoldingRow = HoldingIn & { id: string; invested: number; value: number; gain: number; gain_pct: number | null;
  weight_pct: number; priced: boolean; price_date: string | null; price_source: string | null };
type Suggestion = { title: string; detail: string; reason: string; steps?: string[] };
type Snapshot = { profile: Profile; disclaimer: string; suggestions: Suggestion[];
  summary: { holdings: HoldingRow[]; invested: number; value: number; gain: number; gain_pct: number | null;
    allocation_pct: Record<string, number>; priced: number; count: number } };
type Projection = { total_paid: number; range: { pessimistic: number; expected: number; optimistic: number };
  assumed_annual_returns_pct: number[]; note: string };

const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;
const EMPTY: HoldingIn = { kind: 'mf', name: '', symbol: '', isin: '', units: 0, avg_cost: 0, buy_date: null, category: 'equity' };

// Advisor, not trader: Sentinel analyses and suggests; you place every investment yourself.
const Portfolio: React.FC = () => {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [adding, setAdding] = useState<HoldingIn | null>(null);
  const [preview, setPreview] = useState<HoldingIn[] | null>(null);
  const [plan, setPlan] = useState({ monthly: 1000, years: 10, lumpsum: 0, category: 'equity' });
  const [projection, setProjection] = useState<Projection | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const { run, prompt } = usePinAction(setMessage);

  const apply = (s: Snapshot) => { setSnap(s); setProfile(s.profile); };
  const load = useCallback(async () => {
    try { apply(await apiGet<Snapshot>('/api/portfolio')); } catch (e) { setMessage(e instanceof Error ? e.message : 'Could not load.'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<Snapshot>, done: string) => {
    setBusy(true);
    try { apply(await fn()); setMessage(done); } catch (e) { setMessage(e instanceof Error ? e.message : 'Failed.'); }
    finally { setBusy(false); }
  };

  const importFile = async (file: File) => {
    const { port, token } = await backendInfo();
    const res = await fetch(`http://127.0.0.1:${port}/api/portfolio/import/preview`, {
      method: 'POST', headers: { 'X-Sentinel-Session': token, 'Content-Type': 'text/csv' }, body: file });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) { setMessage(String(body.detail || 'Could not read that file.')); return; }
    setPreview(body.holdings.map((h: HoldingIn & { last_price?: number }) => {
      const { last_price: _ignored, ...rest } = h; void _ignored;
      return { ...rest, symbol: rest.symbol || '', isin: rest.isin || '' };
    }));
    setMessage(`Found ${body.holdings.length} holding(s)${body.skipped.length ? `, skipped ${body.skipped.length} row(s)` : ''}. Check them, then confirm.`);
  };

  const s = snap?.summary;
  return (
    <div className="ws-container glass-panel">
      <h3>Portfolio Advisor</h3>
      <p className="ws-muted">{snap?.disclaimer}</p>
      <div role="status" aria-live="polite" className="ws-message">{message}</div>
      {prompt}

      {s && (
        <dl className="ws-facts">
          <dt>Invested</dt><dd>{inr(s.invested)}</dd>
          <dt>Current value</dt><dd>{inr(s.value)} {s.priced < s.count && <span className="ws-muted">({s.count - s.priced} without a current price; shown at cost)</span>}</dd>
          <dt>Gain / loss</dt><dd className={s.gain >= 0 ? 'ws-ok' : 'ws-bad'}>{inr(s.gain)} {s.gain_pct !== null && `(${s.gain_pct}%)`}</dd>
          <dt>Mix</dt><dd>{Object.entries(s.allocation_pct).map(([k, v]) => `${k} ${v}%`).join(' · ') || '—'}</dd>
        </dl>
      )}
      <div className="ws-actions">
        <button type="button" disabled={busy} onClick={() => act(async () => {
          const r = await apiPost<Snapshot & { updated: number; errors: string[] }>('/api/portfolio/refresh-prices');
          setTimeout(() => setMessage(`Updated ${r.updated} price(s).${r.errors.length ? ' Problems: ' + r.errors.join(', ') : ''}`), 0);
          return r;
        }, 'Prices updated.')}>{busy ? 'Working…' : 'Refresh prices (goes online)'}</button>
        <label className="ws-file">Import CSV <input type="file" accept=".csv,text/csv" onChange={e => e.target.files?.[0] && importFile(e.target.files[0])} /></label>
        <button type="button" onClick={() => setAdding({ ...EMPTY })}>Add by hand</button>
      </div>

      {preview && (
        <div className="ws-editor">
          <strong>Import preview</strong>
          <ul className="ws-list">{preview.map((h, i) => <li key={i} className="ws-item">{h.name} · {h.kind} · {h.category} · {h.units} units @ {inr(h.avg_cost)}</li>)}</ul>
          <div className="ws-actions">
            <button type="button" onClick={() => act(() => apiPost('/api/portfolio/import', { holdings: preview }), 'Imported.').then(() => setPreview(null))}>Add these</button>
            <button type="button" onClick={() => run(async (pin?: string) => {
              apply(await apiPost('/api/portfolio/import', { holdings: preview, replace: true, pin })); setPreview(null); setMessage('Replaced all holdings.');
            })}>Replace all holdings with these</button>
            <button type="button" onClick={() => setPreview(null)}>Cancel</button>
          </div>
        </div>
      )}

      {adding && (
        <div className="ws-editor">
          <div className="ws-row">
            <select value={adding.kind} onChange={e => setAdding({ ...adding, kind: e.target.value as HoldingIn['kind'] })}>
              <option value="mf">Mutual fund</option><option value="stock">Share</option><option value="other">Other</option>
            </select>
            <input placeholder="Name (as in your app)" value={adding.name} onChange={e => setAdding({ ...adding, name: e.target.value })} />
            <input placeholder={adding.kind === 'stock' ? 'NSE symbol, e.g. INFY' : 'ISIN (optional)'} value={adding.kind === 'stock' ? adding.symbol : adding.isin}
                   onChange={e => setAdding(adding.kind === 'stock' ? { ...adding, symbol: e.target.value.toUpperCase() } : { ...adding, isin: e.target.value.toUpperCase() })} />
          </div>
          <div className="ws-row">
            <label>Units <input type="number" min="0" step="any" value={adding.units || ''} onChange={e => setAdding({ ...adding, units: Number(e.target.value) })} /></label>
            <label>Average buy price ₹ <input type="number" min="0" step="any" value={adding.avg_cost || ''} onChange={e => setAdding({ ...adding, avg_cost: Number(e.target.value) })} /></label>
            <label>Bought on <input type="date" value={adding.buy_date ?? ''} onChange={e => setAdding({ ...adding, buy_date: e.target.value || null })} /></label>
            <select value={adding.category} onChange={e => setAdding({ ...adding, category: e.target.value as HoldingIn['category'] })}>
              <option value="equity">Equity</option><option value="debt">Debt</option><option value="hybrid">Hybrid</option><option value="gold">Gold</option>
            </select>
          </div>
          <div className="ws-actions">
            <button type="button" disabled={!adding.name || adding.units <= 0} onClick={() => act(() => apiPost('/api/portfolio/holdings', adding), 'Added.').then(() => setAdding(null))}>Save</button>
            <button type="button" onClick={() => setAdding(null)}>Cancel</button>
          </div>
        </div>
      )}

      {s && s.holdings.length > 0 && (
        <table className="pf-table">
          <thead><tr><th>Holding</th><th>Units</th><th>Invested</th><th>Value</th><th>Gain</th><th>Weight</th><th /></tr></thead>
          <tbody>{s.holdings.map(h => (
            <tr key={h.id}>
              <td>{h.name}<div className="ws-muted">{h.kind === 'mf' ? 'Fund' : h.kind === 'stock' ? 'Share' : 'Other'} · {h.category}{h.price_date ? ` · price ${h.price_date}` : ' · no price yet'}</div></td>
              <td>{h.units}</td><td>{inr(h.invested)}</td><td>{inr(h.value)}</td>
              <td className={h.gain >= 0 ? 'ws-ok' : 'ws-bad'}>{h.gain_pct !== null ? `${h.gain_pct}%` : '—'}</td>
              <td>{h.weight_pct}%</td>
              <td><button type="button" onClick={() => run(async (pin?: string) => {
                apply(await apiPost(`/api/portfolio/holdings/${h.id}/delete`, { pin })); setMessage('Removed.');
              })}>Remove</button></td>
            </tr>))}</tbody>
        </table>
      )}

      <h3>Suggestions</h3>
      {!profile?.set && <p className="ws-bad">Fill in "About you" below for suggestions that fit you.</p>}
      <ul className="ws-list">
        {snap?.suggestions.map((x, i) => (
          <li key={i} className="ws-item">
            <strong>{x.title}</strong>
            <span>{x.detail}</span>
            <span className="ws-muted">Why: {x.reason}</span>
            {x.steps && <ol>{x.steps.map((st, j) => <li key={j}>{st}</li>)}</ol>}
          </li>
        ))}
      </ul>

      <h3>What if I invest…</h3>
      <div className="ws-row">
        <label>Monthly ₹ <input type="number" min="0" value={plan.monthly} onChange={e => setPlan({ ...plan, monthly: Number(e.target.value) })} /></label>
        <label>One-time ₹ <input type="number" min="0" value={plan.lumpsum} onChange={e => setPlan({ ...plan, lumpsum: Number(e.target.value) })} /></label>
        <label>Years <input type="number" min="1" max="50" value={plan.years} onChange={e => setPlan({ ...plan, years: Number(e.target.value) })} /></label>
        <select value={plan.category} onChange={e => setPlan({ ...plan, category: e.target.value })}>
          <option value="equity">Equity fund</option><option value="hybrid">Hybrid fund</option><option value="debt">Debt fund</option><option value="gold">Gold</option>
        </select>
        <button type="button" onClick={async () => {
          try { setProjection(await apiPost<Projection>('/api/portfolio/project', plan)); } catch (e) { setMessage(e instanceof Error ? e.message : 'Failed.'); }
        }}>Calculate</button>
      </div>
      {projection && (
        <p>You pay in {inr(projection.total_paid)}. After {plan.years} years it could be about <strong>{inr(projection.range.pessimistic)}</strong> (weak markets),
          <strong> {inr(projection.range.expected)}</strong> (typical) or <strong>{inr(projection.range.optimistic)}</strong> (strong markets).
          <span className="ws-muted"> Assumed yearly returns {projection.assumed_annual_returns_pct.join('% / ')}%. {projection.note}</span></p>
      )}

      {profile && (
        <>
          <h3>About you</h3>
          <div className="ws-row">
            <label>Comfort with ups and downs
              <select value={profile.risk} onChange={e => setProfile({ ...profile, risk: e.target.value as Profile['risk'] })}>
                <option value="conservative">Low (safety first)</option><option value="moderate">Medium</option><option value="aggressive">High (long-term growth)</option>
              </select></label>
            <label>Years until you need the money <input type="number" min="1" max="50" value={profile.horizon_years} onChange={e => setProfile({ ...profile, horizon_years: Number(e.target.value) })} /></label>
            <label>Can invest per month ₹ <input type="number" min="0" value={profile.monthly_amount} onChange={e => setProfile({ ...profile, monthly_amount: Number(e.target.value) })} /></label>
            <label>Monthly expenses ₹ <input type="number" min="0" value={profile.monthly_expenses} onChange={e => setProfile({ ...profile, monthly_expenses: Number(e.target.value) })} /></label>
            <label>Emergency savings ₹ <input type="number" min="0" value={profile.emergency_fund} onChange={e => setProfile({ ...profile, emergency_fund: Number(e.target.value) })} /></label>
          </div>
          <input placeholder="Goal (optional), e.g. house down payment in 2031" value={profile.goal} maxLength={300} onChange={e => setProfile({ ...profile, goal: e.target.value })} />
          <div className="ws-actions"><button type="button" onClick={() => act(() => apiPost('/api/portfolio/profile', profile), 'Saved.')}>Save</button></div>
        </>
      )}
    </div>
  );
};

export default Portfolio;
