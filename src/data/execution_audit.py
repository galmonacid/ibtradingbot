"""Exact-set execution certification for native baseline and stressed backtests."""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from datetime import date

from src.backtest.costs import CostModel
from src.backtest.engine import BacktestDecision, BacktestResult
from src.validation.native_execution import NativeBacktestRun
from src.validation.provenance import ValidationRunIdentity, cost_model_sha256, session_list_sha256


class ExecutionAuditError(ValueError):
    """Raised when execution evidence is malformed or not issued by the native auditor."""


_EXECUTION_AUDIT_ATTESTATION = object()


@dataclass(frozen=True, order=True)
class ExecutionAuditFinding:
    code: str
    scenario: str
    security_id: str
    decision_date: date | None
    detail: str


@dataclass(frozen=True, order=True)
class ExecutionPopulationCounts:
    scenario: str
    decisions: int
    orders: int
    fills: int
    missing_open_dispositions: int
    corporate_action_settlements: int


@dataclass(frozen=True)
class ExecutionAuditReport:
    validation_run_id: str
    canonical_manifest_sha256: str
    config_sha256: str
    strategy_version: str
    strategy_definition_sha256: str
    baseline_cost_sha256: str
    stressed_cost_sha256: str
    calendar_sessions_sha256: str
    validation_spec_sha256: str
    baseline_trace_sha256: str
    stressed_trace_sha256: str
    populations: tuple[ExecutionPopulationCounts, ExecutionPopulationCounts]
    findings: tuple[ExecutionAuditFinding, ...]
    passed: bool
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _EXECUTION_AUDIT_ATTESTATION:
            raise ExecutionAuditError("execution reports must be issued by the native auditor")
        if self.passed != (not self.findings):
            raise ExecutionAuditError("execution report decision must be derived from findings")

    def to_json(self) -> str:
        payload = {key: value for key, value in asdict(self).items() if key != "_attestation"}
        return json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))


def _finding(
    findings: list[ExecutionAuditFinding],
    code: str,
    scenario: str,
    detail: str,
    *,
    security_id: str = "",
    decision_date: date | None = None,
) -> None:
    findings.append(ExecutionAuditFinding(code, scenario, security_id, decision_date, detail))


def _expected_execution(sessions: tuple[date, ...], signal_date: date) -> date | None:
    index = bisect_right(sessions, signal_date)
    return sessions[index] if index < len(sessions) else None


def _audit_decision_timing(
    scenario: str,
    sessions: tuple[date, ...],
    decision: BacktestDecision,
    findings: list[ExecutionAuditFinding],
) -> None:
    expected = _expected_execution(sessions, decision.signal_date)
    valid = (
        expected is None and decision.execution_date is None
        if decision.status == "no_next_session"
        else expected is not None and decision.execution_date == expected
    )
    if not valid:
        _finding(
            findings,
            "NOT_NEXT_SESSION",
            scenario,
            f"expected {expected}; observed {decision.execution_date}",
            decision_date=decision.signal_date,
        )


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-10)


def _audit_trace_against_result(
    scenario: str,
    result: BacktestResult,
    costs: CostModel,
    sessions: tuple[date, ...],
    findings: list[ExecutionAuditFinding],
) -> None:
    trace = result.execution_trace
    decisions = {row.decision_id: row for row in trace.decisions}
    intents = {row.order_id: row for row in trace.order_intents}
    fills = {row.order_id: row for row in trace.fills}

    for decision in trace.decisions:
        _audit_decision_timing(scenario, sessions, decision, findings)

    applied = tuple(
        sorted(
            (row.date, row.signal_date, row.reason, tuple(sorted(row.weights.items())))
            for row in result.applied_targets
        )
    )
    traced_applied = tuple(
        sorted(
            (
                row.execution_date,
                row.signal_date,
                row.reason,
                tuple((weight.security_id, weight.weight) for weight in row.target_weights),
            )
            for row in trace.decisions
            if row.status in ("applied", "no_op")
        )
    )
    if applied != traced_applied:
        _finding(findings, "DECISION_POPULATION_MISMATCH", scenario, "applied targets differ")

    expected_issues = tuple(
        sorted(
            (row.date, row.signal_date, row.symbol, row.reason) for row in result.execution_issues
        )
    )
    traced_issues = tuple(
        sorted(
            (
                row.execution_date,
                decisions[row.decision_id].signal_date,
                row.security_id,
                row.reason,
            )
            for row in trace.missing_open_dispositions
        )
    )
    if expected_issues != traced_issues:
        _finding(findings, "DISPOSITION_POPULATION_MISMATCH", scenario, "execution issues differ")
    for disposition in trace.missing_open_dispositions:
        decision = decisions[disposition.decision_id]
        _finding(
            findings,
            "MISSING_OPEN_EXECUTION",
            scenario,
            "native execution could not obtain the required next-session open",
            security_id=disposition.security_id,
            decision_date=decision.signal_date,
        )

    ordinary_trades = tuple(row for row in result.trades if row.reason != "disappearance")
    if len(ordinary_trades) != len(trace.fills):
        _finding(findings, "FILL_POPULATION_MISMATCH", scenario, "trade and fill counts differ")
    unmatched_fills = set(fills)
    for trade in ordinary_trades:
        matches = [
            order_id
            for order_id in unmatched_fills
            if intents[order_id].security_id == trade.symbol
            and intents[order_id].side == trade.side
            and intents[order_id].execution_date == trade.date
            and decisions[intents[order_id].decision_id].signal_date == trade.signal_date
            and decisions[intents[order_id].decision_id].reason == trade.reason
            and _close(fills[order_id].shares, trade.shares)
            and _close(fills[order_id].execution_price, trade.execution_price)
            and _close(fills[order_id].gross_notional, trade.gross_notional)
            and _close(fills[order_id].commission, trade.commission)
            and _close(fills[order_id].slippage_cost, trade.slippage_cost)
            and _close(fills[order_id].fx_cost, trade.fx_cost)
        ]
        if len(matches) != 1:
            _finding(
                findings,
                "FILL_POPULATION_MISMATCH",
                scenario,
                "trade does not match exactly one native fill",
                security_id=trade.symbol,
                decision_date=trade.signal_date,
            )
        else:
            unmatched_fills.remove(matches[0])
    if unmatched_fills:
        _finding(findings, "FILL_POPULATION_MISMATCH", scenario, "orphan native fill exists")

    expected_settlements = tuple(
        sorted(
            (row.date, row.symbol, row.shares, row.reference_price, row.gross_notional)
            for row in result.trades
            if row.reason == "disappearance"
        )
    )
    traced_settlements = tuple(
        sorted(
            (row.session, row.security_id, row.shares, row.cash_per_share, row.proceeds)
            for row in trace.corporate_action_settlements
        )
    )
    if expected_settlements != traced_settlements:
        _finding(
            findings,
            "SETTLEMENT_POPULATION_MISMATCH",
            scenario,
            "disappearance trades differ from settlements",
        )

    for order_id, fill in fills.items():
        intent = intents[order_id]
        if intent.requested_shares is None or intent.reference_price is None:
            continue
        expected_price = costs.execution_price(intent.reference_price, intent.side)
        expected_notional = intent.requested_shares * expected_price
        expected_slippage = intent.requested_shares * abs(expected_price - intent.reference_price)
        expected_fx = costs.fx_cost(expected_notional)
        economics = (
            (fill.execution_price, expected_price),
            (fill.gross_notional, expected_notional),
            (fill.commission, costs.commission_per_order),
            (fill.slippage_cost, expected_slippage),
            (fill.fx_cost, expected_fx),
        )
        if any(not _close(observed, expected) for observed, expected in economics):
            decision = decisions[intent.decision_id]
            _finding(
                findings,
                "COST_ECONOMICS_MISMATCH",
                scenario,
                "fill economics do not match the bound cost model",
                security_id=intent.security_id,
                decision_date=decision.signal_date,
            )


def _logical_decisions(result: BacktestResult) -> tuple[object, ...]:
    return tuple(
        (
            row.decision_id,
            row.signal_date,
            row.execution_date,
            row.reason,
            row.status,
            row.target_weights,
        )
        for row in result.execution_trace.decisions
    )


def _logical_orders(result: BacktestResult) -> tuple[tuple[str, str, date, str, str], ...]:
    return tuple(
        (row.order_id, row.decision_id, row.execution_date, row.security_id, row.side)
        for row in result.execution_trace.order_intents
    )


def _logical_missing_opens(result: BacktestResult) -> tuple[tuple[str, str, date, str], ...]:
    return tuple(
        (row.order_id, row.decision_id, row.execution_date, row.security_id)
        for row in result.execution_trace.missing_open_dispositions
    )


def _logical_settlements(result: BacktestResult) -> tuple[tuple[date, str], ...]:
    return tuple(
        (row.session, row.security_id)
        for row in result.execution_trace.corporate_action_settlements
    )


def audit_native_backtest_executions(
    identity: ValidationRunIdentity,
    *,
    sessions: tuple[date, ...],
    baseline_result: BacktestResult,
    stressed_result: BacktestResult,
    baseline_costs: CostModel,
    stressed_costs: CostModel,
    compare_logical_populations: bool = True,
) -> ExecutionAuditReport:
    """Certify complete native traces and their dataset/strategy/cost/run identity."""
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ExecutionAuditError("execution audit sessions must be non-empty, sorted, and unique")
    findings: list[ExecutionAuditFinding] = []
    if session_list_sha256(sessions) != identity.calendar_sessions_sha256:
        _finding(findings, "SESSION_IDENTITY_MISMATCH", "run", "sessions do not match run identity")
    if cost_model_sha256(baseline_costs) != identity.baseline_cost_sha256:
        _finding(
            findings, "BASELINE_COST_IDENTITY_MISMATCH", "baseline", "cost hash does not match"
        )
    if cost_model_sha256(stressed_costs) != identity.stressed_cost_sha256:
        _finding(
            findings, "STRESSED_COST_IDENTITY_MISMATCH", "stressed", "cost hash does not match"
        )
    if stressed_costs.commission_per_order + 1e-12 < 2 * baseline_costs.commission_per_order:
        _finding(
            findings,
            "COMMISSION_STRESS_TOO_LOW",
            "stressed",
            "stressed commission must be at least 2x baseline",
        )
    minimum_slippage = max(10.0, 2 * baseline_costs.slippage_bps_each_side)
    if stressed_costs.slippage_bps_each_side + 1e-12 < minimum_slippage:
        _finding(
            findings,
            "SLIPPAGE_STRESS_TOO_LOW",
            "stressed",
            "stressed slippage must be at least 10 bps and 2x baseline",
        )
    if stressed_costs.fx_buffer_bps != baseline_costs.fx_buffer_bps:
        _finding(findings, "FX_STRESS_CHANGED", "stressed", "FX friction must remain unchanged")

    _audit_trace_against_result("baseline", baseline_result, baseline_costs, sessions, findings)
    _audit_trace_against_result("stressed", stressed_result, stressed_costs, sessions, findings)
    comparisons = (
        (
            "DECISION_SET_MISMATCH",
            _logical_decisions(baseline_result),
            _logical_decisions(stressed_result),
        ),
        ("ORDER_SET_MISMATCH", _logical_orders(baseline_result), _logical_orders(stressed_result)),
        (
            "DISPOSITION_SET_MISMATCH",
            _logical_missing_opens(baseline_result),
            _logical_missing_opens(stressed_result),
        ),
        (
            "SETTLEMENT_SET_MISMATCH",
            _logical_settlements(baseline_result),
            _logical_settlements(stressed_result),
        ),
    )
    if compare_logical_populations:
        for code, baseline_population, stressed_population in comparisons:
            if baseline_population != stressed_population:
                _finding(
                    findings,
                    code,
                    "cross_scenario",
                    "baseline and stressed logical populations differ",
                )

    baseline_counts = ExecutionPopulationCounts(
        "baseline",
        len(baseline_result.execution_trace.decisions),
        len(baseline_result.execution_trace.order_intents),
        len(baseline_result.execution_trace.fills),
        len(baseline_result.execution_trace.missing_open_dispositions),
        len(baseline_result.execution_trace.corporate_action_settlements),
    )
    stressed_counts = ExecutionPopulationCounts(
        "stressed",
        len(stressed_result.execution_trace.decisions),
        len(stressed_result.execution_trace.order_intents),
        len(stressed_result.execution_trace.fills),
        len(stressed_result.execution_trace.missing_open_dispositions),
        len(stressed_result.execution_trace.corporate_action_settlements),
    )
    ordered_findings = tuple(sorted(findings))
    return ExecutionAuditReport(
        identity.validation_run_id,
        identity.canonical_manifest_sha256,
        identity.config_sha256,
        identity.strategy_version,
        identity.strategy_definition_sha256,
        identity.baseline_cost_sha256,
        identity.stressed_cost_sha256,
        identity.calendar_sessions_sha256,
        identity.validation_spec_sha256,
        baseline_result.execution_trace.sha256,
        stressed_result.execution_trace.sha256,
        (baseline_counts, stressed_counts),
        ordered_findings,
        not ordered_findings,
        _EXECUTION_AUDIT_ATTESTATION,
    )


def audit_bound_native_backtest_executions(
    identity: ValidationRunIdentity,
    *,
    sessions: tuple[date, ...],
    baseline_run: NativeBacktestRun,
    stressed_run: NativeBacktestRun,
    baseline_costs: CostModel,
    stressed_costs: CostModel,
) -> ExecutionAuditReport:
    """Audit only executor-attested runs bound to one input and target population."""
    if baseline_run.scenario != "baseline" or stressed_run.scenario != "stressed":
        raise ExecutionAuditError("bound runs must have baseline and stressed scenarios")
    if baseline_run.validation_run_id != identity.validation_run_id:
        raise ExecutionAuditError("baseline run identity does not match validation identity")
    if stressed_run.validation_run_id != identity.validation_run_id:
        raise ExecutionAuditError("stressed run identity does not match validation identity")
    if baseline_run.market_input_sha256 != stressed_run.market_input_sha256:
        raise ExecutionAuditError("bound runs do not share the same canonical market inputs")
    if baseline_run.target_sha256 != stressed_run.target_sha256:
        raise ExecutionAuditError("bound runs do not share the same target population")
    return audit_native_backtest_executions(
        identity,
        sessions=sessions,
        baseline_result=baseline_run.result,
        stressed_result=stressed_run.result,
        baseline_costs=baseline_costs,
        stressed_costs=stressed_costs,
        # The exact target population is already content-bound above. Costs may
        # legitimately change drawdown-triggered decisions and subsequent orders;
        # each scenario's full population is audited independently.
        compare_logical_populations=False,
    )
