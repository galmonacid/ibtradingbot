"""Mandatory deterministic deployment-gate assessment.

The evaluator is deliberately independent of report generation and backtest
orchestration.  Callers must first establish that their inputs are admissible
point-in-time, out-of-sample evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class GateStatus(StrEnum):
    """Outcome of one mandatory deployment gate."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


@dataclass(frozen=True)
class GateResult:
    """Auditable result for one deployment gate."""

    name: str
    status: GateStatus
    observed: float | int | bool | None
    threshold: float | int | bool
    detail: str


@dataclass(frozen=True)
class DeploymentGateInputs:
    """Evidence required by the deterministic Phase 3 deployment gates."""

    admissible_point_in_time_evidence: bool
    out_of_sample_cagr: float | None = None
    out_of_sample_sharpe: float | None = None
    out_of_sample_maximum_drawdown: float | None = None
    stressed_cagr: float | None = None
    stressed_sharpe: float | None = None
    closed_trades: int | None = None
    realized_profit_loss_by_year: Mapping[int, float] | None = None
    realized_profit_loss_by_stock: Mapping[str, float] | None = None
    nearby_parameters_economically_viable: bool | None = None
    bootstrap_cagr_q05: float | None = None
    bootstrap_sharpe_q05: float | None = None
    bootstrap_maximum_drawdown_q95: float | None = None


@dataclass(frozen=True)
class DeploymentGateAssessment:
    """Complete gate assessment; readiness requires every gate to pass."""

    gates: tuple[GateResult, ...]
    ready_for_paper_trading: bool

    def by_name(self) -> dict[str, GateResult]:
        """Return gate results keyed by their stable names."""

        return {gate.name: gate for gate in self.gates}


def _minimum_gate(name: str, value: float | int | None, threshold: float | int) -> GateResult:
    if value is None or isinstance(value, float) and not math.isfinite(value):
        return GateResult(name, GateStatus.NOT_ASSESSABLE, value, threshold, "metric unavailable")
    status = GateStatus.PASS if value >= threshold else GateStatus.FAIL
    return GateResult(name, status, value, threshold, f"requires {name} >= {threshold}")


def _maximum_gate(name: str, value: float | None, threshold: float) -> GateResult:
    if value is None or not math.isfinite(value) or value < 0.0:
        return GateResult(name, GateStatus.NOT_ASSESSABLE, value, threshold, "metric unavailable")
    status = GateStatus.PASS if value <= threshold else GateStatus.FAIL
    return GateResult(name, status, value, threshold, f"requires {name} <= {threshold}")


def _concentration_gate(
    name: str,
    profit_losses: Mapping[int, float] | Mapping[str, float] | None,
    threshold: float,
) -> GateResult:
    if profit_losses is None or not profit_losses:
        return GateResult(
            name,
            GateStatus.NOT_ASSESSABLE,
            None,
            threshold,
            "profit data unavailable",
        )
    values = tuple(profit_losses.values())
    if any(not math.isfinite(value) for value in values):
        return GateResult(
            name,
            GateStatus.NOT_ASSESSABLE,
            None,
            threshold,
            "realized profit/loss contributions must be finite",
        )
    net_total_profit = sum(values)
    if net_total_profit <= 0.0:
        return GateResult(
            name,
            GateStatus.NOT_ASSESSABLE,
            None,
            threshold,
            "net total cumulative profit must be greater than zero",
        )
    largest_positive_contributor = max((value for value in values if value > 0.0), default=0.0)
    concentration = largest_positive_contributor / net_total_profit
    status = GateStatus.PASS if concentration <= threshold else GateStatus.FAIL
    return GateResult(
        name,
        status,
        concentration,
        threshold,
        f"largest positive contributor / net cumulative profit must be <= {threshold}",
    )


def assess_deployment_gates(
    inputs: DeploymentGateInputs,
    *,
    minimum_bootstrap_cagr_q05: float = 0.0,
    minimum_bootstrap_sharpe_q05: float = 0.0,
    maximum_bootstrap_drawdown_q95: float = 0.25,
) -> DeploymentGateAssessment:
    """Assess every mandatory deterministic deployment gate."""

    evidence_status = (
        GateStatus.PASS if inputs.admissible_point_in_time_evidence else GateStatus.FAIL
    )
    evidence = GateResult(
        "admissible_point_in_time_evidence",
        evidence_status,
        inputs.admissible_point_in_time_evidence,
        True,
        "requires out-of-sample results from admissible point-in-time data",
    )
    robustness = GateResult(
        "parameter_robustness",
        GateStatus.NOT_ASSESSABLE
        if inputs.nearby_parameters_economically_viable is None
        else (GateStatus.PASS if inputs.nearby_parameters_economically_viable else GateStatus.FAIL),
        inputs.nearby_parameters_economically_viable,
        True,
        "nearby parameter values must remain economically viable",
    )
    gates = (
        evidence,
        _minimum_gate("out_of_sample_cagr", inputs.out_of_sample_cagr, 0.08),
        _minimum_gate("out_of_sample_sharpe", inputs.out_of_sample_sharpe, 0.8),
        _maximum_gate(
            "out_of_sample_maximum_drawdown",
            inputs.out_of_sample_maximum_drawdown,
            0.15,
        ),
        _minimum_gate("stressed_cagr", inputs.stressed_cagr, 0.06),
        _minimum_gate("stressed_sharpe", inputs.stressed_sharpe, 0.6),
        _minimum_gate("closed_trades", inputs.closed_trades, 150),
        _concentration_gate("year_profit_concentration", inputs.realized_profit_loss_by_year, 0.35),
        _concentration_gate(
            "stock_profit_concentration", inputs.realized_profit_loss_by_stock, 0.20
        ),
        robustness,
        _minimum_gate(
            "bootstrap_cagr_q05", inputs.bootstrap_cagr_q05, minimum_bootstrap_cagr_q05
        ),
        _minimum_gate(
            "bootstrap_sharpe_q05",
            inputs.bootstrap_sharpe_q05,
            minimum_bootstrap_sharpe_q05,
        ),
        _maximum_gate(
            "bootstrap_maximum_drawdown_q95",
            inputs.bootstrap_maximum_drawdown_q95,
            maximum_bootstrap_drawdown_q95,
        ),
    )
    return DeploymentGateAssessment(
        gates=gates,
        ready_for_paper_trading=all(gate.status is GateStatus.PASS for gate in gates),
    )
