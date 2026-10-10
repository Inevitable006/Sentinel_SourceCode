"""Portfolio Advisor: analysis and suggestions; the owner makes every transaction.

- No bank or broker logins, no order placement, ever.
- Every number comes from the deterministic code in this file; the language model only explains.
- Projections are ranges with stated assumptions, never promises.
- Market data is read-only and fetched only when the owner asks, through the egress guard.
This is educational analysis, not licensed investment advice.
"""
import csv
import io
import math
import re
from datetime import date, datetime
from typing import Dict, List, Optional

DISCLAIMER = ("Educational analysis based on your data and stated assumptions, not licensed investment advice. "
              "Markets can fall; past returns do not guarantee future returns. You decide and place every investment yourself.")

# Long-run annual return assumptions used for ranges (pessimistic, expected, optimistic).
# Deliberately conservative round numbers; shown to the owner with every projection.
RETURN_ASSUMPTIONS = {
    "equity": (0.06, 0.10, 0.13),
    "hybrid": (0.05, 0.08, 0.10),
    "debt": (0.05, 0.065, 0.075),
    "gold": (0.03, 0.07, 0.10),
}

# Target equity share by risk comfort (rest in debt), adjusted by time horizon below.
RISK_TARGETS = {"conservative": 0.30, "moderate": 0.60, "aggressive": 0.80}


# ── import ──────────────────────────────────────────────────────
HEADER_ALIASES = {
    "name": ["instrument", "stock name", "scheme name", "scheme", "fund name", "security name", "name", "company name", "symbol"],
    "symbol": ["symbol", "trading symbol", "tradingsymbol", "nse symbol", "scheme code", "amfi code"],
    "isin": ["isin", "isin code"],
    "units": ["qty.", "qty", "quantity", "units", "balance units", "closing units", "no. of units", "shares"],
    "avg_cost": ["avg. cost", "avg cost", "average price", "average buy price", "avg. price", "avg price", "average cost", "buy price", "purchase nav", "avg nav"],
    "invested": ["invested", "invested value", "invested amount", "cost value", "purchase value", "amount invested", "total cost"],
    "price": ["ltp", "current price", "nav", "current nav", "market price", "close price", "last price"],
    "buy_date": ["buy date", "purchase date", "date"],
    "category": ["category", "asset class", "fund category", "type"],
}


def _norm(header: str) -> str:
    return re.sub(r"\s+", " ", str(header or "").strip().lower().replace("₹", "").replace("(rs)", "").replace("(inr)", "")).strip()


def _number(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("₹", "").strip()
    if text in ("", "-", "--", "NA", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def guess_kind(name: str, isin: str = "", symbol: str = "") -> str:
    lowered = (name or "").lower()
    if (isin or "").upper().startswith("INF") or any(w in lowered for w in ("fund", "scheme", "growth", "idcw", "direct plan", "regular plan", "etf")):
        return "mf"
    return "stock"


def guess_category(name: str, kind: str) -> str:
    lowered = (name or "").lower()
    if any(w in lowered for w in ("gold", "silver")):
        return "gold"
    if any(w in lowered for w in ("liquid", "debt", "bond", "gilt", "overnight", "money market", "corporate", "banking & psu", "short duration", "fd")):
        return "debt"
    if any(w in lowered for w in ("hybrid", "balanced", "asset allocation", "multi asset", "equity savings", "arbitrage")):
        return "hybrid"
    return "equity"


def parse_holdings_csv(text: str) -> Dict:
    """Reads a holdings export (Zerodha, Groww, CAMS/KFintech statements saved as CSV, or any
    sheet with similar columns). Returns {"holdings": [...], "skipped": [...], "columns": {...}}."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    # Exports often have title lines above the real header: use the first row that names a holding and a quantity.
    header_index, mapping = None, {}
    for i, row in enumerate(rows[:30]):
        normalized = [_norm(c) for c in row]
        found = {}
        for field, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                if alias in normalized and field not in found and normalized.index(alias) not in found.values():
                    found[field] = normalized.index(alias)
                    break
        if "name" in found and "units" in found:
            header_index, mapping = i, found
            break
    if header_index is None:
        raise ValueError("Could not find columns for the investment name and quantity/units. "
                         "Export holdings as CSV, or add them by hand.")
    holdings, skipped = [], []
    for n, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        get = lambda f: row[mapping[f]].strip() if f in mapping and mapping[f] < len(row) else ""
        name = get("name")
        units = _number(get("units"))
        if not name or not units or units <= 0 or name.lower() in ("total", "grand total"):
            if any(cell.strip() for cell in row):
                skipped.append(n)
            continue
        avg_cost = _number(get("avg_cost"))
        invested = _number(get("invested"))
        if avg_cost is None and invested is not None:
            avg_cost = invested / units
        isin, symbol = get("isin"), get("symbol")
        if symbol == name:
            symbol = re.sub(r"[^A-Z0-9&\-]", "", name.upper()) if " " not in name.strip() else ""
        kind = guess_kind(name, isin, symbol)
        if not symbol and kind == "stock" and re.fullmatch(r"[A-Z0-9&\-]{1,20}", name.strip()):
            symbol = name.strip()     # e.g. Zerodha's "Instrument" column is the NSE symbol
        category = (get("category") or guess_category(name, kind)).lower()
        category = category if category in RETURN_ASSUMPTIONS else guess_category(category + " " + name, kind)
        holdings.append({"kind": kind, "name": name, "symbol": symbol, "isin": isin, "units": units,
                         "avg_cost": round(avg_cost or 0.0, 4), "buy_date": get("buy_date") or None,
                         "last_price": _number(get("price")), "category": category})
    return {"holdings": holdings, "skipped": skipped,
            "columns": {f: rows[header_index][i] for f, i in mapping.items()}}


# ── calculations ────────────────────────────────────────────────
def _years_since(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%Y/%m/%d"):
        try:
            then = datetime.strptime(iso[:11].strip(), fmt).date()
            days = (date.today() - then).days
            return days / 365.25 if days > 0 else None
        except ValueError:
            continue
    return None


def summarize(holdings: List[dict]) -> dict:
    """Value, gain, allocation and concentration from holdings (dicts with units, avg_cost, last_price...)."""
    rows, invested_total, value_total = [], 0.0, 0.0
    by_category: Dict[str, float] = {}
    priced = 0
    for h in holdings:
        invested = h["units"] * (h.get("avg_cost") or 0.0)
        price = h.get("last_price")
        value = h["units"] * price if price is not None else invested
        priced += price is not None
        gain = value - invested
        years = _years_since(h.get("buy_date"))
        cagr = ((value / invested) ** (1 / years) - 1) if years and years >= 1 and invested > 0 and value > 0 else None
        rows.append({**h, "invested": round(invested, 2), "value": round(value, 2), "gain": round(gain, 2),
                     "gain_pct": round(gain / invested * 100, 2) if invested else None,
                     "cagr_pct": round(cagr * 100, 2) if cagr is not None else None, "priced": price is not None})
        invested_total += invested
        value_total += value
        cat = h.get("category") or "equity"
        by_category[cat] = by_category.get(cat, 0.0) + value
    for r in rows:
        r["weight_pct"] = round(r["value"] / value_total * 100, 2) if value_total else 0.0
    allocation = {k: round(v / value_total * 100, 2) for k, v in sorted(by_category.items())} if value_total else {}
    return {"holdings": sorted(rows, key=lambda r: -r["value"]),
            "invested": round(invested_total, 2), "value": round(value_total, 2),
            "gain": round(value_total - invested_total, 2),
            "gain_pct": round((value_total - invested_total) / invested_total * 100, 2) if invested_total else None,
            "allocation_pct": allocation, "priced": priced, "count": len(rows)}


def future_value(monthly: float, lumpsum: float, years: float, annual_rate: float) -> float:
    """Monthly SIP (paid at the start of each month) plus a lumpsum, compounded monthly."""
    r, n = annual_rate / 12, int(round(years * 12))
    fv_lump = lumpsum * (1 + r) ** n
    fv_sip = monthly * n if r == 0 else monthly * (((1 + r) ** n - 1) / r) * (1 + r)
    return fv_lump + fv_sip


def project(monthly: float, years: float, lumpsum: float = 0.0, category: str = "equity") -> dict:
    if monthly < 0 or lumpsum < 0 or not (0 < years <= 50):
        raise ValueError("Use a non-negative amount and a period between 1 month and 50 years.")
    low, mid, high = RETURN_ASSUMPTIONS.get(category, RETURN_ASSUMPTIONS["equity"])
    paid = monthly * int(round(years * 12)) + lumpsum
    return {"monthly": monthly, "lumpsum": lumpsum, "years": years, "category": category, "total_paid": round(paid, 2),
            "range": {"pessimistic": round(future_value(monthly, lumpsum, years, low)),
                      "expected": round(future_value(monthly, lumpsum, years, mid)),
                      "optimistic": round(future_value(monthly, lumpsum, years, high))},
            "assumed_annual_returns_pct": [round(x * 100, 1) for x in (low, mid, high)],
            "note": "Assumed long-run yearly returns, not predictions. A bad year can still show a loss.",
            "disclaimer": DISCLAIMER}


# ── suggestions (rule-based, explainable) ───────────────────────
def target_equity(profile: dict) -> float:
    base = RISK_TARGETS.get(profile.get("risk", "moderate"), 0.6)
    horizon = float(profile.get("horizon_years") or 5)
    if horizon < 3:
        base = min(base, 0.2)       # money needed soon should not ride the stock market
    elif horizon < 5:
        base = min(base, 0.4)
    return base


def advise(profile: dict, summary: dict) -> List[dict]:
    """Returns suggestions, each with a reason. Never names a "sure" winner."""
    out = []
    monthly = float(profile.get("monthly_amount") or 0)
    expenses = float(profile.get("monthly_expenses") or 0)
    emergency = float(profile.get("emergency_fund") or 0)
    if expenses and emergency < 6 * expenses:
        gap = 6 * expenses - emergency
        out.append({"priority": 1, "title": "Build an emergency fund first",
                    "detail": f"Keep about 6 months of expenses (₹{6 * expenses:,.0f}) in a savings account or liquid fund. "
                              f"You are ₹{gap:,.0f} short.",
                    "reason": "Without a buffer you may have to sell investments at a loss when something unexpected happens."})
    value = summary.get("value") or 0
    if value:
        equity = sum(v for k, v in summary["allocation_pct"].items() if k in ("equity",)) / 100
        hybrid = summary["allocation_pct"].get("hybrid", 0) / 100
        equity_like = equity + hybrid / 2
        target = target_equity(profile)
        if abs(equity_like - target) > 0.10:
            direction = "more" if equity_like < target else "less"
            out.append({"priority": 2, "title": f"Rebalance towards about {target * 100:.0f}% equity",
                        "detail": f"You hold about {equity_like * 100:.0f}% in equity. Direct new money to "
                                  f"{'equity index funds' if direction == 'more' else 'debt or liquid funds'} until closer to target, "
                                  "instead of selling (selling may be taxed).",
                        "reason": f"Your risk level ({profile.get('risk', 'moderate')}) and {profile.get('horizon_years', 5)}-year horizon suggest this mix."})
        top = summary["holdings"][0] if summary["holdings"] else None
        if top and top["weight_pct"] > 25 and summary["count"] > 1:
            out.append({"priority": 2, "title": f"{top['name']} is {top['weight_pct']:.0f}% of your portfolio",
                        "detail": "Consider not adding more to it and spreading new money across other holdings or a diversified index fund.",
                        "reason": "One investment falling sharply would hurt the whole portfolio."})
        stocks = [h for h in summary["holdings"] if h["kind"] == "stock"]
        if 0 < len(stocks) < 5 and sum(h["weight_pct"] for h in stocks) > 40:
            out.append({"priority": 3, "title": "Few individual shares carry a lot of weight",
                        "detail": "A Nifty 50 or Nifty Next 50 index fund gives broad diversification at low cost.",
                        "reason": "Fewer than 5 stocks make up a large share of your money."})
        regular = [h["name"] for h in summary["holdings"] if h["kind"] == "mf" and "regular" in h["name"].lower()]
        if regular:
            out.append({"priority": 3, "title": "Check 'Direct' plans of your Regular funds",
                        "detail": "Regular plans include a distributor commission (often ~0.5–1% a year). Direct plans of the same fund cost less: "
                                  + ", ".join(regular[:3]) + ("…" if len(regular) > 3 else ""),
                        "reason": "Lower yearly costs compound into noticeably more money over long periods. Check exit load and tax before switching."})
    if monthly > 0:
        target = target_equity(profile)
        eq, debt = round(monthly * target / 100) * 100, None
        eq = max(0, min(monthly, eq))
        debt = monthly - eq
        horizon = float(profile.get("horizon_years") or 5)
        proj = project(monthly, horizon, 0, "equity" if target >= 0.5 else "hybrid")
        out.append({"priority": 4, "title": f"Monthly plan for ₹{monthly:,.0f}",
                    "detail": f"About ₹{eq:,.0f} a month in a low-cost equity index fund (e.g. Nifty 50, direct plan) and ₹{debt:,.0f} in a debt or liquid fund. "
                              f"Over {horizon:g} years that could become roughly ₹{proj['range']['pessimistic']:,} – ₹{proj['range']['optimistic']:,} "
                              f"(you pay in ₹{proj['total_paid']:,.0f}).",
                    "reason": "Index funds are diversified and cheap; a SIP averages out the price you pay over time.",
                    "steps": ["Open your broker/fund app (you do this yourself; Sentinel never logs in).",
                              "Search for a Nifty 50 index fund, choose the 'Direct' plan, compare expense ratios (lower is better).",
                              f"Start a monthly SIP of ₹{eq:,.0f} on a date after your salary arrives.",
                              f"Start a ₹{debt:,.0f} SIP in a liquid or short-duration debt fund." if debt else "Keep your emergency fund separate.",
                              "Add the units to Sentinel (import or by hand) so it can track them."]})
    if not out:
        out.append({"priority": 5, "title": "Nothing urgent", "detail": "Your mix matches your profile. Review again in 6 months or when your goals change.",
                    "reason": "Frequent changes usually cost more than they help."})
    return sorted(out, key=lambda s: s["priority"])


# ── market data (read-only, owner-initiated) ────────────────────
AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"


def parse_amfi_navs(text: str) -> Dict[str, dict]:
    """AMFI NAVAll.txt. Column positions are read from the header line, because AMFI has changed
    the layout (newer files add 'Plan' and 'Option' columns)."""
    navs = {}
    col = {"code": 0, "isin1": 1, "isin2": 2, "name": 3, "nav": 4, "date": 5, "plan": None, "option": None}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(";")]
        lowered = [p.lower() for p in parts]
        if lowered and lowered[0] == "scheme code":
            for i, h in enumerate(lowered):
                if "growth" in h or "payout" in h: col["isin1"] = i
                elif "reinvest" in h: col["isin2"] = i
                elif h == "scheme name": col["name"] = i
                elif h == "plan": col["plan"] = i
                elif h == "option": col["option"] = i
                elif "asset value" in h or h == "nav": col["nav"] = i
                elif h == "date": col["date"] = i
            continue
        if len(parts) <= max(v for v in col.values() if v is not None) or not parts[0].isdigit():
            continue
        nav = _number(parts[col["nav"]])
        if nav is None:
            continue
        name = parts[col["name"]]
        extras = [parts[col[k]] for k in ("plan", "option") if col[k] is not None and parts[col[k]]]
        entry = {"nav": nav, "date": parts[col["date"]], "name": " - ".join([name] + extras)}
        navs[parts[col["code"]]] = entry
        for isin in (parts[col["isin1"]], parts[col["isin2"]]):
            if isin and isin != "-":
                navs[isin] = entry
    return navs


_FILLER = {"fund", "plan", "option", "the", "of", "scheme", "-", "mutual", "mf"}


def _tokens(name: str) -> frozenset:
    words = re.findall(r"[a-z0-9&]+", (name or "").lower().replace("idcw", "dividend"))
    return frozenset(w for w in words if w not in _FILLER)


def match_fund(name: str, navs: Dict[str, dict]) -> Optional[dict]:
    """Finds a fund by name only when the match is near-exact (same words, ignoring filler words
    like 'fund', 'plan', 'option'). Direct vs Regular and Growth vs IDCW must agree, so a similar
    but different plan is never used."""
    wanted = _tokens(name)
    if len(wanted) < 2:
        return None
    best, best_score = None, 0.0
    for entry in {id(e): e for e in navs.values()}.values():
        have = _tokens(entry["name"])
        if ("direct" in wanted) != ("direct" in have) or ("dividend" in wanted) != ("dividend" in have):
            continue
        score = len(wanted & have) / len(wanted | have)
        if score > best_score:
            best, best_score = entry, score
    return best if best_score >= 0.85 else None


async def _fetch_text(url: str, max_bytes: int) -> str:
    from app.core.network_utils import SafeAsyncClient
    async with SafeAsyncClient() as client:
        response = await client.safe_request("GET", url, timeout=20.0, max_bytes=max_bytes,
                                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    if response.status_code != 200:
        raise ValueError(f"{url.split('/')[2]} answered {response.status_code}")
    return response.text


async def _stock_price(symbol: str) -> Optional[float]:
    import json as _json
    sym = symbol.upper().strip()
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
        return None
    text = await _fetch_text(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS?interval=1d&range=5d", 512 * 1024)
    meta = (_json.loads(text).get("chart", {}).get("result") or [{}])[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    return float(price) if isinstance(price, (int, float)) else None


async def fetch_prices(holdings: List[dict]) -> Dict[str, dict]:
    """Returns {holding_id: {price, date, source}} and never raises for a single failure."""
    from app.core.egress import tool_context
    results: Dict[str, dict] = {}
    errors: List[str] = []
    with tool_context("portfolio_prices", True):     # owner pressed "Refresh prices"
        funds = [h for h in holdings if h["kind"] == "mf"]
        if funds:
            try:
                navs = parse_amfi_navs(await _fetch_text(AMFI_URL, 12 * 1024 * 1024))
                for h in funds:
                    entry = navs.get(h.get("symbol") or "") or navs.get(h.get("isin") or "")
                    if entry is None:
                        entry = match_fund(h["name"], navs)
                    if entry:
                        results[h["id"]] = {"price": entry["nav"], "date": entry["date"], "source": "AMFI NAV"}
            except Exception as e:
                errors.append(f"Fund NAVs: {type(e).__name__}")
        for h in holdings:
            if h["kind"] == "stock" and h.get("symbol"):
                try:
                    price = await _stock_price(h["symbol"])
                    if price is not None:
                        results[h["id"]] = {"price": price, "date": date.today().isoformat(), "source": "Yahoo Finance (NSE)"}
                except Exception as e:
                    errors.append(f"{h['symbol']}: {type(e).__name__}")
    return {"prices": results, "errors": errors}
