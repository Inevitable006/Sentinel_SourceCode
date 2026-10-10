"""Indian capital-gains tax ESTIMATES for planning (not filing advice).

Rates live in backend/tax-rules-in.json so they can be updated after a Budget without code changes.
Sales are matched to the earliest purchases first (FIFO), as Indian tax rules require for units.
Surcharge, grandfathering (pre-2018 equity), indexation for very old debt and set-off of losses
against other income are not modelled; the result always says so.
"""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

RULES_FILE = Path(__file__).resolve().parents[2] / "tax-rules-in.json"


def load_rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def fy_bounds(today: date):
    start_year = today.year if today.month >= 4 else today.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31), f"FY {start_year}-{str(start_year + 1)[-2:]}"


def _months_between(a: date, b: date) -> float:
    return (b - a).days / 30.4375


@dataclass
class Lot:
    day: date
    units: float
    cost_per_unit: float


def _bucket(category: str, buy_day: date, sell_day: date, rules: dict) -> tuple:
    """Returns (bucket, rate_pct or None for slab). bucket: equity_st | equity_lt | slab | other_lt"""
    held = _months_between(buy_day, sell_day)
    cat = rules["hybrid_treated_as"] if category == "hybrid" else category
    if cat == "equity":
        r = rules["equity"]
        return ("equity_lt", r["long_term_pct"]) if held > r["long_term_after_months"] else ("equity_st", r["short_term_pct"])
    if cat == "debt":
        if buy_day >= date(2023, 4, 1):
            return ("slab", None)
        r = rules["debt_before_2023_04_01"]
        return ("other_lt", r["long_term_pct"]) if held > r["long_term_after_months"] else ("slab", None)
    r = rules["gold"]
    return ("other_lt", r["long_term_pct"]) if held > r["long_term_after_months"] else ("slab", None)


def fifo(transactions: List[dict]):
    """Returns (remaining lots, realised [(buy_day, sell_day, units, gain)]). Needs units on buys/sells."""
    from app.core.portfolio import _to_date
    lots: List[Lot] = []
    realised = []
    for t in sorted(transactions, key=lambda x: (x["day"], 0 if x["kind"] == "buy" else 1)):
        d = _to_date(t["day"])
        if d is None or not t.get("units"):
            continue
        if t["kind"] == "buy":
            lots.append(Lot(d, t["units"], t["amount"] / t["units"]))
        elif t["kind"] == "sell":
            left, price = t["units"], t["amount"] / t["units"]
            while left > 1e-9 and lots:
                lot = lots[0]
                take = min(left, lot.units)
                realised.append((lot.day, d, take, take * (price - lot.cost_per_unit)))
                lot.units -= take
                left -= take
                if lot.units <= 1e-9:
                    lots.pop(0)
    return lots, realised


def estimate(holdings: List[dict], transactions: Dict[str, List[dict]], slab_pct: float, today: Optional[date] = None) -> dict:
    rules = load_rules()
    today = today or date.today()
    fy_start, fy_end, fy_label = fy_bounds(today)
    cess = 1 + rules["cess_pct"] / 100
    realised = {"equity_st": 0.0, "equity_lt": 0.0, "slab": 0.0, "other_lt": 0.0}
    per_holding, notes = [], []
    for h in holdings:
        tx = transactions.get(h["id"], [])
        price = h.get("last_price")
        lots, sold = fifo(tx) if tx else ([], [])
        for buy_day, sell_day, _units, gain in sold:
            if fy_start <= sell_day <= fy_end:
                bucket, _ = _bucket(h.get("category") or "equity", buy_day, sell_day, rules)
                realised[bucket] += gain
        if not tx:
            # No transactions: one lot at the average cost, dated by buy_date if known.
            from app.core.portfolio import _to_date
            d = _to_date(h.get("buy_date") or "")
            if d and h.get("units"):
                lots = [Lot(d, h["units"], h.get("avg_cost") or 0.0)]
        if price is None or not lots:
            per_holding.append({"id": h["id"], "name": h["name"], "available": False,
                                "note": "Needs a current price and purchase dates (transactions or buy date)."})
            continue
        st = lt = 0.0
        tax = 0.0
        lt_equity = 0.0
        for lot in lots:
            gain = lot.units * (price - lot.cost_per_unit)
            bucket, rate = _bucket(h.get("category") or "equity", lot.day, today, rules)
            if bucket in ("equity_lt", "other_lt"):
                lt += gain
            else:
                st += gain
            if bucket == "equity_lt":
                lt_equity += gain
            elif gain > 0:
                tax += gain * ((rate if rate is not None else slab_pct) / 100)
        per_holding.append({"id": h["id"], "name": h["name"], "available": True, "short_term_gain": round(st, 2),
                            "long_term_gain": round(lt, 2), "long_term_equity_gain": round(lt_equity, 2),
                            "tax_if_sold_excl_equity_ltcg": round(tax * cess, 2)})
    eq = rules["equity"]
    exemption_left = max(0.0, eq["yearly_exemption"] - max(0.0, realised["equity_lt"]))
    taxable_ltcg = max(0.0, realised["equity_lt"] - eq["yearly_exemption"])
    tax_realised = (max(0.0, realised["equity_st"]) * eq["short_term_pct"] / 100
                    + taxable_ltcg * eq["long_term_pct"] / 100
                    + max(0.0, realised["other_lt"]) * rules["gold"]["long_term_pct"] / 100
                    + max(0.0, realised["slab"]) * slab_pct / 100) * cess
    unrealised_lt_equity = sum(max(0.0, h.get("long_term_equity_gain", 0)) for h in per_holding if h.get("available"))
    harvest = min(exemption_left, unrealised_lt_equity)
    if harvest >= 1000:
        notes.append(f"You could sell and buy back equity units with up to ₹{harvest:,.0f} of long-term gains this financial year "
                     f"without tax (unused ₹{exemption_left:,.0f} of the ₹{eq['yearly_exemption']:,.0f} exemption). "
                     "This resets your purchase price higher, lowering future tax. Check exit loads first.")
    if any(v < 0 for v in realised.values()):
        notes.append("You have realised losses this year; they can reduce gains of the same kind. This estimate offsets only within each bucket.")
    notes.append("Not modelled: surcharge, pre-2018 grandfathering, indexation, set-off across income heads. "
                 "Units are needed on transactions for exact matching.")
    return {"fy": fy_label, "rules": rules["label"], "verify_note": rules["verify_note"], "slab_pct": slab_pct,
            "realised": {k: round(v, 2) for k, v in realised.items()}, "estimated_tax_realised": round(tax_realised, 2),
            "ltcg_exemption_left": round(exemption_left, 2), "holdings": per_holding, "notes": notes}
