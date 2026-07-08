"""
Unit tests for comp math — budget, equity, band, submit flow.
Run: pytest tests/
Requires: DB seeded via  python scripts/seed_data.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///comp_data.db")

from mcp_server.server import (
    check_budget,
    check_equity,
    find_employee,
    get_pay_band,
    submit_proposal,
    cycle_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def seed_db():
    """Seed a fresh DB before the test session."""
    from scripts.seed_data import main as seed_main
    seed_main()


def _emp(name: str) -> dict:
    matches = find_employee(name)
    assert matches, f"Employee '{name}' not found in DB"
    return matches[0]


# ---------------------------------------------------------------------------
# find_employee
# ---------------------------------------------------------------------------

def test_find_employee_exact():
    result = find_employee("Kim Johnson")
    assert len(result) == 1
    assert result[0]["name"] == "Kim Johnson"


def test_find_employee_partial():
    result = find_employee("kim")
    assert any(e["name"] == "Kim Johnson" for e in result)


def test_find_employee_no_match():
    result = find_employee("Zzznotaname")
    assert result == []


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------

def test_budget_within_limit():
    """Alex's team has ample budget; 5% raise for David Park should pass."""
    david = _emp("David Park")
    result = check_budget(david["manager_id"], david["id"], 5.0)
    assert result["ok"] is True
    assert result["over_budget"] is False
    assert result["overage"] == 0.0


def test_budget_dana_tight_triggers_guardrail():
    """Dana Whitfield pool: $38k total / $35.5k used. Any ~3% raise should be blocked."""
    andrew = _emp("Andrew Mitchell")  # $142k under Dana
    result = check_budget(andrew["manager_id"], andrew["id"], 3.0)
    # 3% of $142k = $4,260 > $2,500 remaining
    assert result["ok"] is False
    assert result["over_budget"] is True
    assert result["overage"] > 0


def test_budget_pool_remaining_math():
    andrew = _emp("Andrew Mitchell")
    result = check_budget(andrew["manager_id"], andrew["id"], 1.0)
    expected_remaining = 38_000 - 35_500  # $2,500
    assert abs(result["pool_remaining"] - expected_remaining) < 1.0


def test_budget_raise_amount_math():
    david = _emp("David Park")
    result = check_budget(david["manager_id"], david["id"], 8.0)
    expected = david["current_salary"] * 0.08
    assert abs(result["raise_amount"] - expected) < 0.01


# ---------------------------------------------------------------------------
# check_equity
# ---------------------------------------------------------------------------

def test_equity_flag_kim_johnson():
    """Kim Johnson SE L4 SF $152k — 5% raise keeps her below peer median."""
    kim = _emp("Kim Johnson")
    proposed = kim["current_salary"] * 1.05  # $159,600
    result = check_equity(kim["id"], proposed)
    assert result["equity_flagged"] is True
    assert result["pct_vs_median"] < -5.0


def test_equity_flag_nina_garcia():
    """Nina Garcia DS L4 Austin $133k — 5% raise keeps her below peer median."""
    nina = _emp("Nina Garcia")
    proposed = nina["current_salary"] * 1.05
    result = check_equity(nina["id"], proposed)
    assert result["equity_flagged"] is True


def test_equity_flag_lily_lopez():
    """Lily Lopez PM L3 NY $116k — 5% raise still below peer median."""
    lily = _emp("Lily Lopez")
    proposed = lily["current_salary"] * 1.05
    result = check_equity(lily["id"], proposed)
    assert result["equity_flagged"] is True


def test_equity_no_flag_above_threshold():
    """David Park SE L4 SF $186k — large raise takes him above peer median, no flag."""
    david = _emp("David Park")
    # Propose $200k — above peer median for SE L4 SF
    result = check_equity(david["id"], 200_000)
    assert result["equity_flagged"] is False
    assert result["pct_vs_median"] > 0


def test_equity_recommendation_present_when_flagged():
    kim = _emp("Kim Johnson")
    result = check_equity(kim["id"], kim["current_salary"] * 1.04)
    assert result["equity_flagged"] is True
    assert result["recommendation"] is not None
    assert result["recommended_min"] is not None
    assert result["recommended_max"] is not None


def test_equity_peer_median_math():
    """
    Kim's peers for SE L4 SF: Maria Smith ($158k) and David Park ($186k).
    Median of [158k, 186k] = $172k.
    """
    kim = _emp("Kim Johnson")
    result = check_equity(kim["id"], kim["current_salary"])
    assert result["peer_count"] == 2
    expected_median = (158_000 + 186_000) / 2  # $172,000
    assert abs(result["peer_median"] - expected_median) < 500  # within rounding


# ---------------------------------------------------------------------------
# get_pay_band
# ---------------------------------------------------------------------------

def test_pay_band_sf_se_l4():
    result = get_pay_band("Software Engineer", "L4", "San Francisco")
    assert result["ok"] is True
    assert result["min_salary"] == 150_000
    assert result["mid_salary"] == 190_000
    assert result["max_salary"] == 230_000


def test_pay_band_austin_multiplier():
    sf_band = get_pay_band("Software Engineer", "L4", "San Francisco")
    austin_band = get_pay_band("Software Engineer", "L4", "Austin")
    assert austin_band["ok"] is True
    ratio = austin_band["mid_salary"] / sf_band["mid_salary"]
    assert abs(ratio - 0.80) < 0.01


def test_pay_band_missing_returns_error():
    result = get_pay_band("Astronaut", "L9", "Mars")
    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# submit_proposal
# ---------------------------------------------------------------------------

def test_submit_proposal_within_budget_no_equity_flag():
    """Propose a healthy raise for David Park (budget OK, no equity flag)."""
    david = _emp("David Park")
    result = submit_proposal(
        employee_id=david["id"],
        manager_id=david["manager_id"],
        proposed_salary=194_000,   # ~4.3% raise
        notes="Strong Q1 performance",
    )
    assert result["ok"] is True
    assert result["budget_ok"] is True
    assert result["equity_flagged"] is False
    assert result["status"] == "pending"
    assert result["proposal_id"] is not None


def test_submit_proposal_over_budget_escalates():
    """Large raise for Andrew Mitchell (Dana's team) should escalate."""
    andrew = _emp("Andrew Mitchell")
    result = submit_proposal(
        employee_id=andrew["id"],
        manager_id=andrew["manager_id"],
        proposed_salary=andrew["current_salary"] * 1.05,
        notes="Test escalation path",
    )
    assert result["ok"] is True
    assert result["budget_ok"] is False
    assert result["status"] == "escalated"


def test_submit_proposal_equity_flag_recorded():
    """Propose 4% for Kim Johnson — equity flag should be set on the proposal."""
    kim = _emp("Kim Johnson")
    result = submit_proposal(
        employee_id=kim["id"],
        manager_id=kim["manager_id"],
        proposed_salary=kim["current_salary"] * 1.04,
        notes="Annual review",
    )
    assert result["ok"] is True
    assert result["equity_flagged"] is True


def test_submit_proposal_increase_pct_math():
    david = _emp("David Park")
    new_sal = david["current_salary"] * 1.06
    result = submit_proposal(
        employee_id=david["id"],
        manager_id=david["manager_id"],
        proposed_salary=new_sal,
        notes="",
    )
    assert abs(result["increase_pct"] - 6.0) < 0.1


# ---------------------------------------------------------------------------
# cycle_status
# ---------------------------------------------------------------------------

def test_cycle_status_global():
    result = cycle_status()
    assert result["ok"] is True
    assert result["total_budget"] > 0
    assert result["total_allocated"] >= 0
    assert isinstance(result["managers"], list)
    assert len(result["managers"]) == 6


def test_cycle_status_dana_high_utilization():
    dana = _emp("Dana Whitfield")
    result = cycle_status(manager_id=dana["id"])
    assert result["ok"] is True
    mgrs = result["managers"]
    assert len(mgrs) == 1
    assert mgrs[0]["utilization_pct"] > 90
