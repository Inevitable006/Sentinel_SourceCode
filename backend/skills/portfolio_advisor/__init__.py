"""
Skill: portfolio_advisor
Lets the chat model read the owner's portfolio analysis and run projections.
Read-only: no bank or broker access, no orders. All numbers come from app.core.portfolio.
Risk Tier: 2 (reads personal financial data; confirmation required)
"""
import json

from app.core import portfolio
from app.core.tool_registry import failed


def portfolio_overview() -> str:
    from app.portfolio_routes import portfolio_snapshot
    try:
        snap = portfolio_snapshot()
    except Exception as e:
        return failed(f"Error: could not read the portfolio ({type(e).__name__}). Is Sentinel unlocked?")
    s = snap["summary"]
    compact = {
        "profile": {k: snap["profile"].get(k) for k in ("risk", "horizon_years", "monthly_amount", "monthly_expenses", "emergency_fund", "goal")},
        "totals": {k: s[k] for k in ("invested", "value", "gain", "gain_pct", "count", "priced")},
        "allocation_pct": s["allocation_pct"],
        "holdings": [{k: h[k] for k in ("name", "kind", "category", "units", "invested", "value", "gain_pct", "weight_pct")}
                     for h in s["holdings"][:25]],
        "suggestions": [{k: x.get(k) for k in ("title", "detail", "reason", "steps")} for x in snap["suggestions"]],
        "disclaimer": snap["disclaimer"],
    }
    return json.dumps(compact, ensure_ascii=False)


def project_investment(monthly: float = 0, years: float = 5, lumpsum: float = 0, category: str = "equity") -> str:
    try:
        return json.dumps(portfolio.project(float(monthly), float(years), float(lumpsum), str(category)))
    except (ValueError, TypeError) as e:
        return failed(f"Error: {e}")
