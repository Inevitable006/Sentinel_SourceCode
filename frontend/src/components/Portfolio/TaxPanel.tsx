import React, { useEffect, useState } from 'react';
import { apiGet } from '../../lib/backend';

type Tax = {
  fy: string; rules: string; verify_note: string; slab_pct: number;
  realised: { equity_st: number; equity_lt: number; slab: number; other_lt: number };
  estimated_tax_realised: number; ltcg_exemption_left: number; notes: string[];
  holdings: { id: string; name: string; available: boolean; short_term_gain?: number; long_term_gain?: number; note?: string }[];
};

const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;

// Capital-gains tax ESTIMATE for planning. Re-reads whenever the portfolio changes (refreshKey).
const TaxPanel: React.FC<{ refreshKey: unknown }> = ({ refreshKey }) => {
  const [tax, setTax] = useState<Tax | null>(null);
  useEffect(() => { apiGet<Tax>('/api/portfolio/tax').then(setTax).catch(() => setTax(null)); }, [refreshKey]);
  if (!tax) return null;
  const r = tax.realised;
  return (
    <section>
      <h3>Tax estimate ({tax.fy})</h3>
      <p className="ws-muted">{tax.rules}. {tax.verify_note} Estimate for planning only, not tax filing advice.</p>
      <dl className="ws-facts">
        <dt>Short-term equity gains</dt><dd>{inr(r.equity_st)}</dd>
        <dt>Long-term equity gains</dt><dd>{inr(r.equity_lt)} <span className="ws-muted">(₹1.25 lakh a year is tax-free; {inr(tax.ltcg_exemption_left)} unused)</span></dd>
        <dt>Debt / slab-taxed gains</dt><dd>{inr(r.slab)} <span className="ws-muted">at your {tax.slab_pct}% slab</span></dd>
        <dt>Other long-term gains</dt><dd>{inr(r.other_lt)}</dd>
        <dt>Estimated tax on sales this year</dt><dd><strong>{inr(tax.estimated_tax_realised)}</strong> <span className="ws-muted">incl. 4% cess</span></dd>
      </dl>
      <details>
        <summary>If you sold today</summary>
        <ul className="ws-list">{tax.holdings.map(h => (
          <li key={h.id} className="ws-item">{h.name}: {h.available
            ? <>short-term {inr(h.short_term_gain ?? 0)} · long-term {inr(h.long_term_gain ?? 0)}</>
            : <span className="ws-muted">{h.note}</span>}</li>))}</ul>
      </details>
      <ul>{tax.notes.map((n, i) => <li key={i} className="ws-muted">{n}</li>)}</ul>
    </section>
  );
};

export default TaxPanel;
