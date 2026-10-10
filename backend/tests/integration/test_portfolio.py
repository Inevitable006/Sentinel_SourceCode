"""Phase 9 Portfolio Advisor: import, calculations, suggestions, API. Offline only."""
import pytest
from fastapi.testclient import TestClient

from app.core import portfolio as pf

ZERODHA = """Instrument,Qty.,Avg. cost,LTP,Cur. val,P&L,Net chg.,Day chg.
INFY,10,1400.50,1500,15000,995,7.1,0.4
TCS,2,3500,3400,6800,-200,-2.86,-0.1
"""
GROWW_MF = """Scheme Name,AMC,Category,Sub-category,Folio No.,Units,Invested Value,Current Value,Returns,XIRR
Parag Parikh Flexi Cap Fund Direct Growth,PPFAS,Equity,Flexi Cap,123,100.5,6000,7000,1000,12%
HDFC Liquid Fund Regular Growth,HDFC,Debt,Liquid,456,2,9000,9100,100,6%
"""
CAMS = """Consolidated Account Statement
Investor: (removed)

Scheme,ISIN,Closing Units,NAV,Cost Value,Market Value
Nippon India Nifty 50 Index Fund - Direct Plan - Growth,INF204KB1882,250.123,40.12,9000,10035
Total,,,,9000,10035
"""


def test_imports_common_exports():
    z = pf.parse_holdings_csv(ZERODHA)["holdings"]
    assert [(h["name"], h["kind"], h["units"], h["avg_cost"]) for h in z] == [("INFY", "stock", 10, 1400.5), ("TCS", "stock", 2, 3500)]
    assert z[0]["symbol"] == "INFY" and z[0]["last_price"] == 1500

    g = pf.parse_holdings_csv(GROWW_MF)["holdings"]
    assert [h["kind"] for h in g] == ["mf", "mf"]
    assert g[0]["avg_cost"] == pytest.approx(6000 / 100.5, rel=1e-4)
    assert [h["category"] for h in g] == ["equity", "debt"]

    c = pf.parse_holdings_csv(CAMS)                    # title lines above the header, a Total row below
    assert len(c["holdings"]) == 1 and c["holdings"][0]["isin"] == "INF204KB1882"
    assert c["holdings"][0]["last_price"] == 40.12


def test_unreadable_file_is_explained():
    with pytest.raises(ValueError, match="name and quantity"):
        pf.parse_holdings_csv("a,b,c\n1,2,3\n")


def test_summary_numbers():
    s = pf.summarize([
        {"name": "A", "kind": "stock", "units": 10, "avg_cost": 100, "last_price": 150, "category": "equity"},
        {"name": "B", "kind": "mf", "units": 100, "avg_cost": 10, "last_price": None, "category": "debt"},
    ])
    assert (s["invested"], s["value"], s["gain"], s["gain_pct"]) == (2000, 2500, 500, 25.0)
    assert s["allocation_pct"] == {"debt": 40.0, "equity": 60.0}
    assert s["priced"] == 1


def test_sip_future_value_matches_the_formula():
    # ₹1,000 a month for 10 years at 12% a year, paid at the start of each month: about ₹2,32,339.
    assert pf.future_value(1000, 0, 10, 0.12) == pytest.approx(232339, abs=1)
    assert pf.future_value(0, 10000, 1, 0.0) == 10000


def test_projection_is_a_range_with_assumptions():
    p = pf.project(1000, 5)
    assert p["total_paid"] == 60000
    assert p["range"]["pessimistic"] < p["range"]["expected"] < p["range"]["optimistic"]
    assert "not licensed" in p["disclaimer"]
    with pytest.raises(ValueError):
        pf.project(1000, 0)


def titles(s):
    return " | ".join(x["title"] for x in s)


def test_suggestions_have_reasons_and_follow_the_rules():
    profile = {"risk": "aggressive", "horizon_years": 10, "monthly_amount": 1000, "monthly_expenses": 20000, "emergency_fund": 10000}
    summary = pf.summarize([
        {"name": "Only Stock", "kind": "stock", "units": 1, "avg_cost": 90000, "last_price": 90000, "category": "equity"},
        {"name": "XYZ Fund Regular Growth", "kind": "mf", "units": 1, "avg_cost": 10000, "last_price": 10000, "category": "debt"},
    ])
    s = pf.advise(profile, summary)
    t = titles(s)
    assert s[0]["title"] == "Build an emergency fund first"
    assert "Only Stock is 90%" in t and "Direct" in t and "Monthly plan for ₹1,000" in t
    assert all(x["reason"] for x in s)
    plan = next(x for x in s if x["title"].startswith("Monthly plan"))
    assert any("never logs in" in step for step in plan["steps"])


def test_short_horizon_keeps_money_out_of_stocks():
    assert pf.target_equity({"risk": "aggressive", "horizon_years": 2}) == 0.2


def test_amfi_parser():
    text = ("Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n\n"
            "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n\n"
            "120716;INF204KB1882;-;Nippon India Nifty 50 Index Fund - Direct Plan - Growth;40.5512;09-Oct-2026\n")
    navs = pf.parse_amfi_navs(text)
    assert navs["120716"]["nav"] == 40.5512 and navs["INF204KB1882"]["date"] == "09-Oct-2026"


# ── API ──────────────────────────────────────────────────────────
TOKEN = "pf-token"
H = {"X-Sentinel-Session": TOKEN}


@pytest.fixture
def web(monkeypatch):
    from app.main import app
    from app import portfolio_routes as routes
    from app.db.database import SessionLocal
    from app.db.models import Holding, InvestorProfile
    with SessionLocal() as db:
        db.query(Holding).delete(); db.query(InvestorProfile).delete(); db.commit()
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    monkeypatch.setattr(routes.vault, "is_unlocked", lambda: True)
    monkeypatch.setattr(routes.vault, "pin_fresh", lambda: True)
    return TestClient(app), routes


def test_api_flow(web, monkeypatch):
    client, routes = web
    preview = client.post("/api/portfolio/import/preview", headers={**H, "Content-Type": "text/csv"}, content=ZERODHA.encode())
    assert preview.status_code == 200 and len(preview.json()["holdings"]) == 2
    holdings = [{k: v for k, v in h.items() if k != "last_price"} for h in preview.json()["holdings"]]
    snap = client.post("/api/portfolio/import", headers=H, json={"holdings": holdings}).json()
    assert snap["summary"]["count"] == 2 and snap["summary"]["invested"] == pytest.approx(21005)
    client.post("/api/portfolio/profile", headers=H, json={"risk": "moderate", "horizon_years": 7, "monthly_amount": 1000})

    async def fake_fetch(holdings):
        return {"prices": {h["id"]: {"price": 1600.0, "date": "2026-10-10", "source": "test"} for h in holdings}, "errors": []}
    monkeypatch.setattr(routes.portfolio, "fetch_prices", fake_fetch)
    refreshed = client.post("/api/portfolio/refresh-prices", headers=H).json()
    assert refreshed["updated"] == 2 and refreshed["summary"]["value"] == pytest.approx(19200)

    hid = refreshed["summary"]["holdings"][0]["id"]
    monkeypatch.setattr(routes.vault, "pin_fresh", lambda: False)
    assert client.post(f"/api/portfolio/holdings/{hid}/delete", headers=H, json={}).status_code == 403
    assert client.post("/api/portfolio/project", headers=H, json={"monthly": 1000, "years": 10}).json()["total_paid"] == 120000


def test_api_needs_unlock(web, monkeypatch):
    client, routes = web
    monkeypatch.setattr(routes.vault, "is_unlocked", lambda: False)
    assert client.get("/api/portfolio", headers=H).status_code == 423


def test_chat_skill_reads_real_numbers(web):
    client, _ = web
    client.post("/api/portfolio/holdings", headers=H, json={"kind": "stock", "name": "INFY", "symbol": "INFY",
                                                            "units": 10, "avg_cost": 1000, "category": "equity"})
    from app.core.skill_router import skill_router
    if "portfolio_advisor" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()
    from app.core.secure_runner import secure_runner
    first = secure_runner.execute("skill_portfolio_overview", {}, "pf-chat", force_confirmation=True)
    result = secure_runner.execute("skill_portfolio_overview", {}, "pf-chat", token=first["token"])
    assert result["status"] == "success" and '"invested": 10000.0' in result["data"]


NEW_AMFI = ("Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date\r\n \r\n"
            "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)\r\n \r\n"
            "122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;88.9258;09-Oct-2026\r\n"
            "122640;INF879O01019;-;Parag Parikh Flexi Cap Fund;Regular Plan;Growth;80.9756;09-Oct-2026\r\n")


def test_amfi_new_layout_and_safe_name_matching():
    navs = pf.parse_amfi_navs(NEW_AMFI)
    assert navs["INF879O01027"]["nav"] == 88.9258
    assert pf.match_fund("Parag Parikh Flexi Cap Fund Direct Growth", navs)["nav"] == 88.9258
    assert pf.match_fund("Parag Parikh Flexi Cap Fund Regular Growth", navs)["nav"] == 80.9756
    assert pf.match_fund("Parag Parikh Flexi Cap Fund Direct IDCW", navs) is None     # different option: no guess
    assert pf.match_fund("Some Other Fund Direct Growth", navs) is None
