import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';

type Fund = { id: string; name: string; ter_pct: number; checked_on: string | null; yearly_cost: number;
  cost_over_10y: number; high: boolean; direct_plan_could_save?: number };
type Costs = { funds: Fund[]; missing: string[]; yearly_total: number; total_cost_over_10y: number;
  overlap_warnings: string[]; note: string };
type HoldingRef = { id: string; name: string; kind: string };

const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;

// What fund fees cost you, from expense ratios you enter (no reliable free bulk source exists).
const CostPanel: React.FC<{ holdings: HoldingRef[]; refreshKey: unknown }> = ({ holdings, refreshKey }) => {
  const [costs, setCosts] = useState<Costs | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  useEffect(() => { apiGet<Costs>('/api/portfolio/costs').then(setCosts).catch(() => setCosts(null)); }, [refreshKey]);
  if (!costs) return null;
  const funds = holdings.filter(h => h.kind === 'mf');
  if (funds.length === 0) return null;
  const known = Object.fromEntries(costs.funds.map(f => [f.id, f]));

  const save = async (id: string) => {
    try { setCosts(await apiPost<Costs>(`/api/portfolio/costs/${id}`, { ter_pct: Number(edit[id]) })); setMessage('Saved.'); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Use a number between 0 and 3.'); }
  };

  return (
    <section>
      <h3>Fund costs</h3>
      <p className="ws-muted">Enter each fund's expense ratio (TER, % a year) from your fund app or the fund's factsheet. Check it every few months; funds change it.</p>
      {costs.funds.length > 0 && (
        <p>Your funds cost about <strong>{inr(costs.yearly_total)} a year</strong>, roughly <strong>{inr(costs.total_cost_over_10y)}</strong> of growth over 10 years.
          <span className="ws-muted"> {costs.note}</span></p>
      )}
      <ul className="ws-list">
        {funds.map(f => {
          const c = known[f.id];
          return (
            <li key={f.id} className={`ws-item ${c?.high ? 'ws-sev-warning' : ''}`}>
              <div className="ws-item-head">
                <span>{f.name}</span>
                <input style={{ width: '5rem' }} type="number" min={0} max={3} step={0.01} placeholder="TER %"
                       value={edit[f.id] ?? (c ? String(c.ter_pct) : '')} onChange={e => setEdit({ ...edit, [f.id]: e.target.value })} />
                <button type="button" disabled={!edit[f.id]} onClick={() => save(f.id)}>Save</button>
              </div>
              {c && <span className="ws-muted">{inr(c.yearly_cost)} a year · about {inr(c.cost_over_10y)} over 10 years{c.checked_on ? ` · checked ${c.checked_on}` : ''}
                {c.high ? ' · high for this type of fund' : ''}</span>}
              {c?.direct_plan_could_save !== undefined && (
                <span>A Direct plan of the same fund could leave you about <strong>{inr(c.direct_plan_could_save)}</strong> more after 10 years. Check exit load and tax before switching.</span>
              )}
            </li>
          );
        })}
      </ul>
      {costs.overlap_warnings.map((w, i) => <p key={i} className="ws-bad">{w}</p>)}
      <p className="ws-muted">{message}</p>
    </section>
  );
};

export default CostPanel;
