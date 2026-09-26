from dataclasses import replace
from datetime import date

import pytest

from src.backtest.costs import CostModel
from src.backtest.engine import PriceBar, run_backtest
from src.data.execution_audit import (
    ExecutionAuditError,
    ExecutionAuditReport,
    audit_native_backtest_executions,
)
from src.validation.provenance import create_validation_run_identity, session_list_sha256

SESSIONS = (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6))
BASELINE = CostModel(0.35, 5.0, 5.0)
STRESSED = CostModel(0.70, 10.0, 5.0)


def _identity(
    *,
    sessions: tuple[date, ...] = SESSIONS,
    baseline: CostModel = BASELINE,
    stressed: CostModel = STRESSED,
):
    return create_validation_run_identity(
        canonical_manifest_sha256="a" * 64,
        config_sha256="b" * 64,
        strategy_version="phase3-v1",
        strategy_definition_sha256="e" * 64,
        baseline_costs=baseline,
        stressed_costs=stressed,
        calendar_sessions_sha256=session_list_sha256(sessions),
        validation_spec_sha256="c" * 64,
        git_revision="d" * 40,
        git_dirty=False,
    )


def _result(costs: CostModel, targets: dict[str, float] | None = None):
    bars = [
        PriceBar(session, symbol, 100.0, 100.0, 100.0)
        for session in SESSIONS
        for symbol in ("SEC-A", "SEC-B")
    ]
    return run_backtest(
        bars,
        {SESSIONS[0]: targets or {"SEC-A": 0.3, "SEC-B": 0.2}},
        initial_cash=10_000,
        costs=costs,
    )


def _audit(baseline=None, stressed=None, *, identity=None, sessions=SESSIONS):
    return audit_native_backtest_executions(
        identity or _identity(sessions=sessions),
        sessions=sessions,
        baseline_result=baseline or _result(BASELINE),
        stressed_result=stressed or _result(STRESSED),
        baseline_costs=BASELINE,
        stressed_costs=STRESSED,
    )


def test_native_exact_set_audit_binds_run_and_recomputes_costs() -> None:
    baseline = _result(BASELINE)
    stressed = _result(STRESSED)
    report = _audit(baseline, stressed)

    assert report.passed
    assert report.findings == ()
    assert report.validation_run_id == _identity().validation_run_id
    assert report.baseline_trace_sha256 == baseline.execution_trace.sha256
    assert report.stressed_trace_sha256 == stressed.execution_trace.sha256
    assert report.populations[0].decisions == report.populations[1].decisions == 1
    assert report.populations[0].orders == report.populations[0].fills == 2
    assert len(report.to_json()) > 100


def test_audit_rejects_identity_and_actual_cost_mismatches() -> None:
    wrong_costs = CostModel(0.5, 6.0, 5.0)
    identity_report = _audit(identity=_identity(baseline=wrong_costs))
    economics_report = audit_native_backtest_executions(
        _identity(baseline=wrong_costs),
        sessions=SESSIONS,
        baseline_result=_result(BASELINE),
        stressed_result=_result(STRESSED),
        baseline_costs=wrong_costs,
        stressed_costs=STRESSED,
    )

    assert {row.code for row in identity_report.findings} == {"BASELINE_COST_IDENTITY_MISMATCH"}
    assert "COST_ECONOMICS_MISMATCH" in {row.code for row in economics_report.findings}


def test_audit_detects_deleted_trade_despite_intact_native_trace() -> None:
    baseline = _result(BASELINE)
    report = _audit(replace(baseline, trades=baseline.trades[:-1]))

    assert not report.passed
    assert {row.code for row in report.findings} == {"FILL_POPULATION_MISMATCH"}


def test_audit_detects_cross_scenario_decision_and_order_substitution() -> None:
    stressed = _result(STRESSED, {"SEC-A": 0.25})
    report = _audit(stressed=stressed)

    assert not report.passed
    assert {row.code for row in report.findings} >= {
        "DECISION_SET_MISMATCH",
        "ORDER_SET_MISMATCH",
    }


def test_audit_detects_session_identity_and_timing_substitution() -> None:
    substituted_sessions = (SESSIONS[0], SESSIONS[2])
    report = _audit(
        identity=_identity(sessions=substituted_sessions), sessions=substituted_sessions
    )

    assert not report.passed
    assert "NOT_NEXT_SESSION" in {row.code for row in report.findings}


def test_documented_stress_levels_and_unchanged_fx_are_required() -> None:
    weak = CostModel(0.69, 9.9, 6.0)
    report = audit_native_backtest_executions(
        _identity(stressed=weak),
        sessions=SESSIONS,
        baseline_result=_result(BASELINE),
        stressed_result=_result(weak),
        baseline_costs=BASELINE,
        stressed_costs=weak,
    )

    assert {row.code for row in report.findings} >= {
        "COMMISSION_STRESS_TOO_LOW",
        "SLIPPAGE_STRESS_TOO_LOW",
        "FX_STRESS_CHANGED",
    }


def test_report_cannot_be_constructed_or_decision_overridden() -> None:
    with pytest.raises(ExecutionAuditError, match="native auditor"):
        ExecutionAuditReport(
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "strategy",
            "3" * 64,
            "d" * 64,
            "e" * 64,
            "f" * 64,
            "0" * 64,
            "1" * 64,
            "2" * 64,
            (),  # type: ignore[arg-type]
            (),
            True,
        )
