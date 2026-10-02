"""R3.1 economics, causal funnel and fail-closed acceptance tests."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config.r3_feasibility import R3FeasibilityConfig, load_r3_feasibility_config
from src.data.calendar import TradingCalendar
from src.data.canonical_historical import CanonicalDailyBar
from src.data.trusted_historical import SecurityMembershipInterval
from src.research.r3_feasibility import build_r3_feasibility_report


def _sessions(count: int = 260) -> tuple[date, ...]:
    start = date(2025, 1, 2)
    return tuple(
        start + timedelta(days=offset)
        for offset in range(500)
        if (start + timedelta(days=offset)).weekday() < 5
    )[:count]


def _ledger(signal: date, execution: date) -> dict[str, Any]:
    return {
        "initial_capital_gbp": 3000.0,
        "initial_capital_usd": 3750.0,
        "fractional": False,
        "invalid_evidence": True,
        "points": [
            {
                "date": signal.isoformat(),
                "equity_gbp": 3000.0,
                "equity_usd": 3750.0,
                "gross_exposure": 0.0,
                "regime": "risk_on",
                "hard_halted": False,
                "soft_active": False,
            },
            {
                "date": execution.isoformat(),
                "equity_gbp": 2980.0,
                "equity_usd": 3725.0,
                "gross_exposure": 0.2,
                "regime": "risk_on",
                "hard_halted": False,
                "soft_active": False,
            },
        ],
        "fills": [
            {
                "date": execution.isoformat(),
                "signal_date": signal.isoformat(),
                "shares": 10.0,
                "execution_price": 20.01,
                "gbp_per_usd": 0.8,
                "commission_gbp": 0.8,
                "commission_usd": 1.0,
                "slippage_gbp": 0.08,
                "slippage_usd": 0.1,
                "fx_friction_gbp": 0.08,
                "fx_friction_usd": 0.1,
                "side": "buy",
                "reason": "monthly_selection",
            }
        ],
        "conversions": [
            {"date": execution.isoformat(), "fee_gbp": 0.05, "fee_usd": 0.0625}
        ],
        "fees": [{"date": signal.isoformat(), "amount_gbp": 3.0}],
        "closed_lots": [],
        "episodes": [],
        "issues": [],
        "decisions": [
            {
                "signal_date": signal.isoformat(),
                "execution_date": execution.isoformat(),
                "reason": "monthly_selection",
                "status": "applied",
                "skips": [{"symbol": "E", "reason": "rounded_below_one_share"}],
            }
        ],
        "exclusions": [
            {"date": signal.isoformat(), "security_id": "Z", "reason": "liquidity_below_minimum"}
        ],
    }


def _canonical(sessions: tuple[date, ...]) -> SimpleNamespace:
    bars = []
    identities = ("SPY", "A", "B", "C", "D", "E")
    for offset, identity in enumerate(identities):
        for index, day in enumerate(sessions):
            price = 20 * math.exp(0.001 * index + 0.006 * math.sin(index * 0.31 + offset))
            median_dollars = 600_000_000 if identity in {"SPY", "A"} else 30_000_000
            volume = round(median_dollars / price)
            bars.append(
                CanonicalDailyBar(
                    identity,
                    identity,
                    day,
                    price,
                    price,
                    price,
                    price,
                    price,
                    volume,
                    price,
                    price,
                    price,
                    volume,
                )
            )
    memberships = tuple(
        SecurityMembershipInterval("fixture", identity, sessions[0], None)
        for identity in identities
        if identity != "SPY"
    )
    return SimpleNamespace(
        bars=tuple(bars),
        memberships=memberships,
        manifest_sha256="c" * 64,
    )


def _parent_report(ledger: dict[str, Any]) -> dict[str, Any]:
    pretty = json.dumps(ledger, sort_keys=True, indent=2, allow_nan=False) + "\n"
    compact = json.dumps(ledger, sort_keys=True, default=str, allow_nan=False)
    return {
        "run_id": "fixture-run",
        "scenarios": {
            "gbp3000/baseline": {
                "status": "executed",
                "ledger_sha256": hashlib.sha256(pretty.encode()).hexdigest(),
                "execution_audit": {
                    "passed": True,
                    "findings": [],
                    "ledger_sha256": hashlib.sha256(compact.encode()).hexdigest(),
                    "reconciled_sessions": len(ledger["points"]),
                    "trading_fills": len(ledger["fills"]),
                },
            }
        },
    }
def test_config_is_separate_strict_and_fail_closed(tmp_path: Path) -> None:
    checked_in = load_r3_feasibility_config(Path("config.r3-feasibility.yaml"))
    assert checked_in.annual_data_gbp == 0
    assert checked_in.whole_share_us_stocks_assumed_permitted
    assert not checked_in.account_tariff_verified
    assert checked_in.scope_decision == "proceed_with_open_evidence"
    with pytest.raises(ValueError, match="predeclared"):
        R3FeasibilityConfig(r3_liquidity_usd=19_000_000)
    with pytest.raises(ValueError, match="fractional"):
        R3FeasibilityConfig(fractional_shares=True)
    with pytest.raises(ValueError, match="documentary"):
        R3FeasibilityConfig(account_tariff_verified=True)
    with pytest.raises(ValueError, match="dated decision"):
        R3FeasibilityConfig(scope_decision="proceed_with_open_evidence")
    path = tmp_path / "r3.yaml"
    path.write_text("strategy_version: r3.1-feasibility-v1\nunknown: 1\n")
    with pytest.raises(ValueError, match="unknown"):
        load_r3_feasibility_config(path)


def test_report_reconciles_ledger_and_blocks_missing_contracts_without_mutation() -> None:
    sessions = _sessions()
    ledger = _ledger(sessions[252], sessions[253])
    original = deepcopy(ledger)
    report = build_r3_feasibility_report(
        ledger,
        R3FeasibilityConfig(),
        run_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
        ledger_sha256="a" * 64,
        config_file_sha256="b" * 64,
    )
    assert ledger == original
    attribution = report["legacy_ledger_attribution"]
    assert attribution["ledger_structure_validated"]
    assert not attribution["ledger_reconciled"]
    assert attribution["actual_fills"] == 1
    assert attribution["terminal_wealth_gbp"] == 2980
    assert attribution["recorded_cost_total_gbp"] == pytest.approx(4.01)
    assert attribution["daily_attribution"][0]["skips"] == {
        "rounded_below_one_share": 1
    }
    assert not report["research_acceptance_passed"]
    assert not report["next_stage_permitted"]
    assert not report["qualification_permitted"]
    assert "canonical_policy_recomputation_not_run" in report["blockers"]
    assert "content_bound_source_execution_audit_not_verified" in report["blockers"]
    assert report["starting_account_budget"]["additional_funding_assumed_gbp"] == 0
    assert not report["starting_account_budget"]["fractional_shares_assumed"]


def test_assumed_costs_and_permissions_never_become_verified_evidence() -> None:
    sessions = _sessions()
    config = R3FeasibilityConfig(
        annual_data_gbp=0,
        annual_hosting_gbp=0,
        annual_software_gbp=0,
        whole_share_us_stocks_assumed_permitted=True,
        account_tariff_evidence="assumption",
        account_permissions_evidence="assumption",
    )
    report = build_r3_feasibility_report(
        _ledger(sessions[252], sessions[253]),
        config,
        run_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
        ledger_sha256="a" * 64,
        config_file_sha256="b" * 64,
    )
    budget = report["starting_account_budget"]
    assert budget["recurring_operating_costs_gbp"] == {
        "data": 0,
        "hosting": 0,
        "software": 0,
    }
    assert not budget["all_in_cost_known"]
    assert "incremental_operating_cost_evidence" in budget["unresolved"]
    assert not report["research_acceptance_passed"]


def test_scope_decision_closes_phase_without_resolving_evidence_or_execution() -> None:
    sessions = _sessions()
    config = replace(
        R3FeasibilityConfig(),
        scope_decision="proceed_with_open_evidence",
        scope_decision_recorded_at="2026-09-27",
        scope_decision_note="User accepts carrying the open points into R3.2.",
    )
    report = build_r3_feasibility_report(
        _ledger(sessions[252], sessions[253]),
        config,
        run_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
        ledger_sha256="a" * 64,
        config_file_sha256="b" * 64,
    )
    assert not report["research_acceptance_passed"]
    assert report["phase_closed"]
    assert report["next_stage_permitted"]
    assert not report["next_stage_started"]
    assert not report["qualification_permitted"]
    assert not report["paper_execution_permitted"]
    assert report["blockers"]
    assert not report["scope_decision"]["resolves_evidence_blockers"]


def test_causal_policy_funnel_compares_fixed_policies_and_builds_whole_share_plans() -> None:
    sessions = _sessions()
    signal, execution = sessions[252], sessions[253]
    calendar = TradingCalendar("XNYS", "fixture", sessions, (), "d" * 64)
    config = R3FeasibilityConfig(
        annual_data_gbp=0,
        annual_hosting_gbp=0,
        annual_software_gbp=0,
        account_tariff_evidence="fixture tariff evidence",
        account_permissions_evidence="fixture whole-share permission evidence",
    )
    ledger = _ledger(signal, execution)
    report = build_r3_feasibility_report(
        ledger,
        config,
        run_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
        ledger_sha256="a" * 64,
        config_file_sha256="b" * 64,
        canonical=_canonical(sessions),  # type: ignore[arg-type]
        calendar=calendar,
        legacy_report=_parent_report(ledger),
        legacy_report_sha256="e" * 64,
    )
    policy = report["policy_comparison"]
    row = policy["dates"][0]
    assert row["pit_members"] == 5
    assert row["legacy_liquidity_500m"] == 1
    assert row["r3_liquidity_20m"] == 5
    assert row["r3_momentum_scores"] == 5
    assert row["volatility_selected"] == 4
    assert all(order["shares"] == int(order["shares"]) for order in row["orders"])
    assert all(order["notional_gbp"] <= order["capacity_gbp"] for order in row["orders"])
    assert policy["feasible_flat_account_plans"] == 1
    assert report["starting_account_budget"]["mandatory_liquidation_reserve_gbp"] > 0
    assert report["legacy_ledger_attribution"]["ledger_reconciled"]
    # The fixture ledger is explicitly marked invalid, so research still fails closed.
    assert "legacy_ledger_contains_known_data_limitations" in report["blockers"]


def test_noncausal_or_fractional_legacy_evidence_is_rejected() -> None:
    sessions = _sessions()
    ledger = _ledger(sessions[252], sessions[253])
    ledger["fills"][0]["date"] = sessions[252].isoformat()
    with pytest.raises(ValueError, match="non-causal"):
        build_r3_feasibility_report(
            ledger,
            R3FeasibilityConfig(),
            run_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
            ledger_sha256="a" * 64,
            config_file_sha256="b" * 64,
        )
    ledger = _ledger(sessions[252], sessions[253])
    ledger["fills"][0]["shares"] = 1.5
    with pytest.raises(ValueError, match="whole-share"):
        build_r3_feasibility_report(
            ledger,
            R3FeasibilityConfig(),
            run_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
            ledger_sha256="a" * 64,
            config_file_sha256="b" * 64,
        )
