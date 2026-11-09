"""Known answers and invalid-input behavior through the real approved skill path."""
import json
import pytest
from app.core.secure_runner import secure_runner


@pytest.fixture(autouse=True)
def registered():
    from app.core.skill_router import skill_router
    if "business_analysis" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()


def run(tool, **args):
    first = secure_runner.execute(tool, args, "calculators", force_confirmation=True)
    assert first["status"] == "needs_confirmation", first
    return secure_runner.execute(tool, args, "calculators", token=first["token"])


def data(tool, **args):
    result = run(tool, **args)
    assert result["status"] == "success", result
    return json.loads(result["data"])


def test_unit_economics_known_answer_and_ceiling():
    out = data("skill_unit_economics", price=10, variable_cost=6, fixed_cost=101, units=30, target_profit=20)
    assert out["operating_profit"] == 19
    assert out["break_even_units"] == 26
    assert out["target_profit_units"] == 31
    assert out["contribution_margin_percent"] == 40
    decimal = data("skill_unit_economics", price=.3, variable_cost=.1, fixed_cost=.6)
    assert decimal["break_even_units"] == 3


def test_nonpositive_margin_is_not_a_break_even_claim():
    out = data("skill_unit_economics", price=0, variable_cost=1, fixed_cost=50, units=10)
    assert out["contribution_margin_percent"] is None
    assert out["break_even_units"] is None and out["target_profit_units"] is None
    assert out["operating_profit"] == -60


def test_campaign_known_answer():
    out = data("skill_campaign_metrics", spend=200, impressions=10000, clicks=400, conversions=20, revenue=800)
    assert out["click_through_rate_percent"] == 4
    assert out["click_conversion_rate_percent"] == 5
    assert out["cost_per_click"] == .5
    assert out["cost_per_conversion"] == 10
    assert out["cost_per_thousand_impressions"] == 20
    assert out["return_on_ad_spend"] == 4
    assert out["revenue_minus_ad_spend"] == 600


def test_zero_denominators_are_undefined():
    out = data("skill_campaign_metrics", spend=0, impressions=0, clicks=0, conversions=0)
    assert all(out[k] is None for k in ("return_on_ad_spend", "cost_per_click", "click_through_rate_percent"))


@pytest.mark.parametrize("value,source,target,expected", [
    (1, "ft", "m", .3048), (1, "lb", "kg", .45359237), (2, "h", "s", 7200),
    (1, "MiB", "B", 1048576), (1, "MB", "B", 1000000), (32, "F", "C", 0),
    (100, "C", "F", 212), (0, "K", "C", -273.15), (1, "kWh", "J", 3600000),
])
def test_unit_conversion_known_answers(value, source, target, expected):
    out = data("skill_convert_units", value=value, from_unit=source, to_unit=target)
    assert out["result"] == pytest.approx(expected, abs=1e-10)


def test_transfer_accounts_for_bits_and_utilization():
    out = data("skill_estimate_transfer", size=1, size_unit="GB", bandwidth_mbps=100, utilization_percent=80)
    assert out["seconds"] == 100 and out["effective_mbps"] == 80
    assert data("skill_estimate_transfer", size=0, size_unit="B", bandwidth_mbps=1)["seconds"] == 0


@pytest.mark.parametrize("tool,args", [
    ("skill_unit_economics", dict(price=-1, variable_cost=0, fixed_cost=0)),
    ("skill_unit_economics", dict(price="NaN", variable_cost=0, fixed_cost=0)),
    ("skill_unit_economics", dict(price=1, variable_cost=0, fixed_cost=0, units=True)),
    ("skill_campaign_metrics", dict(spend=1, impressions=2, clicks=3, conversions=1)),
    ("skill_campaign_metrics", dict(spend=1, impressions=10, clicks=3, conversions=4)),
    ("skill_convert_units", dict(value=1, from_unit="m", to_unit="kg")),
    ("skill_convert_units", dict(value=-1, from_unit="K", to_unit="C")),
    ("skill_convert_units", dict(value=True, from_unit="m", to_unit="ft")),
    ("skill_convert_units", dict(value=1, from_unit="unknown", to_unit="ft")),
    ("skill_estimate_transfer", dict(size=1, size_unit="GB", bandwidth_mbps=0)),
    ("skill_estimate_transfer", dict(size=1, size_unit="m", bandwidth_mbps=100)),
    ("skill_estimate_transfer", dict(size=1, size_unit="GB", bandwidth_mbps=100, utilization_percent=101)),
])
def test_invalid_calculations_fail(tool, args):
    assert run(tool, **args)["status"] == "error"


def test_both_packs_respect_owner_switch(monkeypatch):
    from app import workspace_routes
    monkeypatch.setattr(workspace_routes, "skill_enabled", lambda name: name not in {"business_analysis", "technical_analysis"})
    for tool in ("skill_unit_economics", "skill_campaign_metrics", "skill_convert_units", "skill_estimate_transfer"):
        result = secure_runner.execute(tool, {}, "calculators", force_confirmation=True)
        assert result["status"] == "error" and "turned off" in result["message"]
