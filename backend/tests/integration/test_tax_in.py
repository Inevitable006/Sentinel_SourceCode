"""Indian capital-gains ESTIMATES: FIFO, short/long term, exemption, debt rules, FY boundaries."""
from datetime import date

import pytest

from app.core import tax_in

TODAY = date(2026, 10, 10)          # FY 2026-27


def h(id="h1", category="equity", price=200.0, **kw):
    return {"id": id, "name": id, "category": category, "last_price": price, "units": kw.get("units", 0),
            "avg_cost": kw.get("avg_cost", 0), "buy_date": kw.get("buy_date")}


def test_fy_bounds():
    assert tax_in.fy_bounds(date(2026, 10, 10))[2] == "FY 2026-27"
    assert tax_in.fy_bounds(date(2027, 3, 31))[2] == "FY 2026-27"
    assert tax_in.fy_bounds(date(2026, 3, 31))[2] == "FY 2025-26"


def test_fifo_matches_earliest_purchases_first():
    lots, sold = tax_in.fifo([
        {"day": "2024-01-01", "kind": "buy", "units": 10, "amount": 1000},
        {"day": "2025-06-01", "kind": "buy", "units": 10, "amount": 1500},
        {"day": "2026-05-01", "kind": "sell", "units": 15, "amount": 3000},
    ])
    assert [(s[0].isoformat(), round(s[2], 2), round(s[3], 2)) for s in sold] == [
        ("2024-01-01", 10, 1000.0),       # 10 units bought at 100, sold at 200
        ("2025-06-01", 5, 250.0)]         # 5 units bought at 150, sold at 200
    assert len(lots) == 1 and lots[0].units == pytest.approx(5)


def test_equity_short_and_long_term_with_exemption():
    tx = {"h1": [
        {"day": "2024-01-01", "kind": "buy", "units": 1000, "amount": 100000},   # held > 12 months at sale
        {"day": "2026-08-01", "kind": "buy", "units": 100, "amount": 18000},     # held < 12 months at sale
        {"day": "2026-09-01", "kind": "sell", "units": 1100, "amount": 440000},  # price 400
    ]}
    r = tax_in.estimate([h(price=400)], tx, slab_pct=30, today=TODAY)
    assert r["realised"]["equity_lt"] == pytest.approx(300000)      # 1000 × (400 − 100)
    assert r["realised"]["equity_st"] == pytest.approx(22000)       # 100 × (400 − 180)
    # tax = (22000 × 20% + (300000 − 125000) × 12.5%) × 1.04
    assert r["estimated_tax_realised"] == pytest.approx((4400 + 21875) * 1.04)
    assert r["ltcg_exemption_left"] == 0


def test_sales_in_an_earlier_year_do_not_count_this_year():
    tx = {"h1": [{"day": "2020-01-01", "kind": "buy", "units": 10, "amount": 1000},
                 {"day": "2025-12-01", "kind": "sell", "units": 10, "amount": 5000}]}
    r = tax_in.estimate([h()], tx, slab_pct=30, today=TODAY)
    assert r["realised"]["equity_lt"] == 0 and r["estimated_tax_realised"] == 0


def test_new_debt_funds_use_the_slab_rate_regardless_of_holding_period():
    tx = {"d1": [{"day": "2023-06-01", "kind": "buy", "units": 100, "amount": 10000},
                 {"day": "2026-09-01", "kind": "sell", "units": 100, "amount": 12000}]}
    r = tax_in.estimate([h("d1", "debt", 120)], tx, slab_pct=20, today=TODAY)
    assert r["realised"]["slab"] == pytest.approx(2000)
    assert r["estimated_tax_realised"] == pytest.approx(2000 * 0.20 * 1.04)


def test_unrealised_estimate_and_harvesting_hint():
    tx = {"h1": [{"day": "2024-01-01", "kind": "buy", "units": 1000, "amount": 100000}]}
    r = tax_in.estimate([h(price=150)], tx, slab_pct=30, today=TODAY)
    row = r["holdings"][0]
    assert row["long_term_equity_gain"] == pytest.approx(50000) and row["short_term_gain"] == 0
    assert r["ltcg_exemption_left"] == 125000
    assert any("without tax" in n and "₹50,000" in n for n in r["notes"])


def test_missing_data_is_reported_not_guessed():
    r = tax_in.estimate([h(price=None)], {}, slab_pct=30, today=TODAY)
    assert r["holdings"][0]["available"] is False
    assert "verify" in r["verify_note"].lower() or "check" in r["verify_note"].lower()


def test_api(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import portfolio_routes as routes
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "tax-token")
    monkeypatch.setattr(routes.vault, "is_unlocked", lambda: True)
    body = TestClient(app).get("/api/portfolio/tax", headers={"X-Sentinel-Session": "tax-token"}).json()
    assert body["fy"].startswith("FY ") and "notes" in body
