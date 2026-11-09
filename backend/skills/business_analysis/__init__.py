"""Deterministic business calculations from owner-supplied assumptions; no external data."""
import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from app.core.tool_registry import failed


def _number(value, name):
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = Decimal(str(value))
        if not number.is_finite() or not 0 <= number <= Decimal("1e12"):
            raise ValueError()
        return number
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be a finite number from 0 to 1 trillion.") from None


def unit_economics(price: float, variable_cost: float, fixed_cost: float,
                   units: int = 0, target_profit: float = 0) -> str:
    try:
        price, variable, fixed, target = (_number(v, n) for v, n in (
            (price, "price"), (variable_cost, "variable_cost"),
            (fixed_cost, "fixed_cost"), (target_profit, "target_profit")))
        if isinstance(units, bool) or not isinstance(units, int) or not 0 <= units <= 1_000_000_000:
            raise ValueError("units must be a whole number from 0 to 1 billion.")
    except ValueError as e:
        return failed(f"Error: {e}")
    contribution = price - variable
    def rounded(v):
        return float(round(v, 4))
    def required(amount):
        return int((amount / contribution).to_integral_value(rounding=ROUND_CEILING)) if contribution > 0 else None
    result = {
        "revenue": rounded(price * units),
        "total_cost": rounded(fixed + variable * units),
        "operating_profit": rounded(contribution * units - fixed),
        "contribution_per_unit": rounded(contribution),
        "contribution_margin_percent": rounded(contribution / price * 100) if price else None,
        "break_even_units": required(fixed),
        "target_profit_units": required(fixed + target),
        "assumptions": "All amounts use the same currency and period; constant price/cost per unit. Excludes tax, financing and capacity constraints.",
    }
    if contribution <= 0:
        result["note"] = "No positive contribution per unit; sales cannot cover positive fixed costs or a positive target profit. Required-unit estimates are undefined."
    return json.dumps(result, indent=2)


def campaign_metrics(spend: float, impressions: int, clicks: int,
                     conversions: int, revenue: float = 0) -> str:
    try:
        spend, revenue = _number(spend, "spend"), _number(revenue, "revenue")
        if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 1_000_000_000
               for v in (impressions, clicks, conversions)):
            raise ValueError("impressions, clicks and conversions must be whole numbers from 0 to 1 billion.")
        if not conversions <= clicks <= impressions:
            raise ValueError("For this click-through funnel, conversions <= clicks <= impressions is required.")
    except ValueError as e:
        return failed(f"Error: {e}")
    def ratio(a, b, scale=1):
        return float(round(Decimal(a) / Decimal(b) * scale, 4)) if b else None
    return json.dumps({
        "click_through_rate_percent": ratio(clicks, impressions, 100),
        "click_conversion_rate_percent": ratio(conversions, clicks, 100),
        "cost_per_click": ratio(spend, clicks),
        "cost_per_conversion": ratio(spend, conversions),
        "cost_per_thousand_impressions": ratio(spend, impressions, 1000),
        "return_on_ad_spend": ratio(revenue, spend),
        "revenue_minus_ad_spend": float(revenue - spend),
        "assumptions": "One click-through funnel and reporting period, same currency. Null means undefined (zero denominator). Revenue minus ad spend is not profit; product and operating costs are excluded. Attribution and data quality are not verified.",
    }, indent=2)
