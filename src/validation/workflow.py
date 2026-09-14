"""Generic, injected Phase 3 validation workflow without market-data assumptions."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from statistics import fmean, stdev
from typing import cast

from src.data.execution_audit import ExecutionAuditReport
from src.data.membership_audit import MembershipAuditReport
from src.data.semantic_certification import SemanticCertificationReport
from src.validation.ablation import (
    AblationAnalysis,
    AblationEvaluator,
    run_ablation_analysis,
)
from src.validation.bootstrap import BootstrapAnalysis, bootstrap_validation
from src.validation.engine import (
    Evaluator,
    WalkForwardEvaluation,
    run_walk_forward_selection,
)
from src.validation.gates import (
    DeploymentGateAssessment,
    DeploymentGateInputs,
    assess_deployment_gates,
)
from src.validation.sensitivity import ParameterSet, ParameterValue
from src.validation.walk_forward import WalkForwardWindow, build_expanding_windows


@dataclass(frozen=True)
class WorkflowEvidence:
    """Evidence derived by a caller from the untouched stitched OOS results."""

    regimes: tuple[str, ...]
    stressed_oos_returns: tuple[float, ...]
    realized_trades: tuple[RealizedTradeEvidence, ...]


@dataclass(frozen=True)
class RealizedTradeEvidence:
    """One closed OOS trade with signed realized profit/loss attribution."""

    lot_id: str
    opened_date: date
    closed_date: date
    symbol: str
    basis: float
    proceeds: float

    def __post_init__(self) -> None:
        if not self.lot_id or not self.symbol:
            raise ValueError("realized trade lot ID and symbol must not be blank")
        if self.closed_date <= self.opened_date:
            raise ValueError("realized trade must close after it opens")
        if not math.isfinite(self.basis) or self.basis <= 0.0:
            raise ValueError("realized trade basis must be finite and positive")
        if not math.isfinite(self.proceeds) or self.proceeds < 0.0:
            raise ValueError("realized trade proceeds must be finite and non-negative")

    @property
    def return_value(self) -> float:
        return self.proceeds / self.basis - 1.0

    @property
    def profit_loss(self) -> float:
        return self.proceeds - self.basis


@dataclass(frozen=True)
class TrustedProducerEvidence:
    """Typed result of the trusted producer's source-level semantic checks."""

    producer_id: str
    producer_version: str
    source_manifest_validated: bool
    membership_identity_validated: bool
    corporate_actions_validated: bool
    independent_membership_audit_validated: bool
    execution_audit_validated: bool
    dataset_manifest_sha256: str
    membership_audit_sha256: str
    semantic_report_sha256: str
    execution_audit_sha256: str
    _attestation: object = field(repr=False)

    def __post_init__(self) -> None:
        if not self.producer_id.strip() or not self.producer_version.strip():
            raise ValueError("trusted producer identity and version must not be blank")
        checks = (
            self.source_manifest_validated,
            self.membership_identity_validated,
            self.corporate_actions_validated,
            self.independent_membership_audit_validated,
            self.execution_audit_validated,
        )
        if any(not isinstance(check, bool) for check in checks):
            raise TypeError("trusted producer validation checks must be booleans")
        if self._attestation is not _PRODUCER_ATTESTATION:
            raise ValueError("trusted producer evidence must be issued from concrete reports")
        for value in (
            self.dataset_manifest_sha256,
            self.membership_audit_sha256,
            self.semantic_report_sha256,
            self.execution_audit_sha256,
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("trusted producer evidence hashes must be canonical SHA-256")

    @property
    def semantically_validated(self) -> bool:
        return all(
            (
                self.source_manifest_validated,
                self.membership_identity_validated,
                self.corporate_actions_validated,
                self.independent_membership_audit_validated,
                self.execution_audit_validated,
            )
        )


_PRODUCER_ATTESTATION = object()


def issue_trusted_producer_evidence(
    *,
    producer_id: str,
    producer_version: str,
    dataset_manifest_sha256: str,
    membership_audit: MembershipAuditReport,
    semantic_report: SemanticCertificationReport,
    execution_audit: ExecutionAuditReport,
) -> TrustedProducerEvidence:
    """Issue evidence only from concrete, content-bound producer reports."""
    import hashlib

    if (
        not membership_audit.passed
        or not 50 <= membership_audit.requested_sample_size <= 100
        or len(membership_audit.audited_events) != membership_audit.requested_sample_size
        or len(membership_audit.independent_sources) < 2
    ):
        raise ValueError("trusted producer requires a complete passing membership audit")
    if not semantic_report.passed or semantic_report.findings:
        raise ValueError("trusted producer requires a complete passing semantic report")
    if not execution_audit.passed or execution_audit.findings or execution_audit.record_count <= 0:
        raise ValueError("trusted producer requires a passing execution audit")
    audit_bytes = membership_audit.to_json().encode()
    semantic_bytes = semantic_report.to_json().encode()
    execution_bytes = execution_audit.to_json().encode()
    return TrustedProducerEvidence(
        producer_id,
        producer_version,
        source_manifest_validated=True,
        membership_identity_validated=semantic_report.passed,
        corporate_actions_validated=semantic_report.passed,
        independent_membership_audit_validated=membership_audit.passed,
        execution_audit_validated=execution_audit.passed,
        dataset_manifest_sha256=dataset_manifest_sha256,
        membership_audit_sha256=hashlib.sha256(audit_bytes).hexdigest(),
        semantic_report_sha256=hashlib.sha256(semantic_bytes).hexdigest(),
        execution_audit_sha256=hashlib.sha256(execution_bytes).hexdigest(),
        _attestation=_PRODUCER_ATTESTATION,
    )


@dataclass(frozen=True)
class ValidationWorkflowResult:
    """Typed Phase 3 evidence with a JSON-compatible conversion."""

    admissible_evidence: bool
    windows: tuple[WalkForwardWindow, ...]
    walk_forward: WalkForwardEvaluation
    bootstrap: BootstrapAnalysis
    ablations: AblationAnalysis | None
    gates: DeploymentGateAssessment

    def as_dict(self) -> dict[str, object]:
        """Return a recursively JSON-compatible machine representation."""
        return cast(dict[str, object], _json_value(asdict(self)))


def _json_value(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


EvidenceEvaluator = Callable[[WalkForwardEvaluation], WorkflowEvidence]


def return_metrics(returns: Sequence[float]) -> tuple[float, float | None, float]:
    if not returns or any(not math.isfinite(value) or value <= -1.0 for value in returns):
        raise ValueError("OOS returns must be finite simple returns greater than -1")
    wealth = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in returns:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        maximum_drawdown = max(maximum_drawdown, 1.0 - wealth / peak)
    cagr = wealth ** (252.0 / len(returns)) - 1.0
    deviation = stdev(returns) if len(returns) >= 2 else None
    sharpe = (
        fmean(returns) / deviation * math.sqrt(252.0)
        if deviation is not None and deviation > 1e-15
        else None
    )
    return cagr, sharpe, maximum_drawdown


def _terminal_wealth(returns: Sequence[float]) -> float:
    return math.prod(1.0 + value for value in returns)


def _derived_gate_inputs(
    *,
    admissible: bool,
    daily_returns: tuple[float, ...],
    stressed_returns: tuple[float, ...],
    trades: tuple[RealizedTradeEvidence, ...],
    walk_forward: WalkForwardEvaluation,
    minimum_validation_score: float,
    bootstrap: BootstrapAnalysis,
) -> DeploymentGateInputs:
    cagr, sharpe, maximum_drawdown = return_metrics(daily_returns)
    stressed_cagr, stressed_sharpe, _stressed_drawdown = return_metrics(stressed_returns)
    by_year: defaultdict[int, float] = defaultdict(float)
    by_stock: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        by_year[trade.closed_date.year] += trade.profit_loss
        by_stock[trade.symbol] += trade.profit_loss
    robustness = all(
        fold.selection.neighbouring_viable >= 1
        and fold.selection.selected.validation_score >= minimum_validation_score
        and all(
            score >= minimum_validation_score for score in fold.selection.neighbouring_viable_scores
        )
        for fold in walk_forward.folds
    )
    return DeploymentGateInputs(
        admissible_point_in_time_evidence=admissible,
        out_of_sample_cagr=cagr,
        out_of_sample_sharpe=sharpe,
        out_of_sample_maximum_drawdown=maximum_drawdown,
        stressed_cagr=stressed_cagr,
        stressed_sharpe=stressed_sharpe,
        closed_trades=len(trades),
        realized_profit_loss_by_year=dict(by_year),
        realized_profit_loss_by_stock=dict(by_stock),
        nearby_parameters_economically_viable=robustness,
        bootstrap_cagr_q05=min(bootstrap.daily.cagr.q05, bootstrap.regime_blocks.cagr.q05),
        bootstrap_sharpe_q05=(
            min(bootstrap.daily.sharpe_ratio.q05, bootstrap.regime_blocks.sharpe_ratio.q05)
            if bootstrap.daily.sharpe_ratio is not None
            and bootstrap.regime_blocks.sharpe_ratio is not None
            else None
        ),
        bootstrap_maximum_drawdown_q95=max(
            bootstrap.daily.maximum_drawdown.q95,
            bootstrap.regime_blocks.maximum_drawdown.q95,
        ),
    )


def _run_ablations(
    walk_forward: WalkForwardEvaluation,
    evaluator: AblationEvaluator | None,
    data_id: str | None,
    cost_id: str | None,
) -> AblationAnalysis | None:
    if evaluator is None:
        if data_id is not None or cost_id is not None:
            raise ValueError("ablation identifiers require an ablation evaluator")
        return None
    if not data_id or not cost_id:
        raise ValueError("ablation evaluator requires data_id and cost_id")
    return run_ablation_analysis(
        oos_dates=tuple(day for day, _value in walk_forward.stitched_test_observations),
        data_id=data_id,
        cost_id=cost_id,
        evaluator=evaluator,
    )


def run_validation_workflow(
    sessions: Sequence[date],
    candidates: Sequence[ParameterSet],
    grid_axes: Mapping[str, Sequence[ParameterValue]],
    segment_evaluator: Evaluator,
    evidence_evaluator: EvidenceEvaluator,
    *,
    verified_complete_through: date,
    point_in_time_universe: bool,
    complete_data_coverage: bool,
    ablation_evaluator: AblationEvaluator | None = None,
    ablation_data_id: str | None = None,
    ablation_cost_id: str | None = None,
    initial_train_years: int = 8,
    validation_years: int = 2,
    test_years: int = 1,
    step_months: int = 6,
    relative_tolerance: float = 0.20,
    minimum_viable_neighbours: int = 1,
    bootstrap_iterations: int = 2_000,
    bootstrap_block_length: int = 20,
    bootstrap_seed: int = 0,
    minimum_economic_validation_score: float = 0.60,
    trusted_producer_evidence: TrustedProducerEvidence | None = None,
    minimum_bootstrap_cagr_q05: float = 0.0,
    minimum_bootstrap_sharpe_q05: float = 0.0,
    maximum_bootstrap_drawdown_q95: float = 0.25,
) -> ValidationWorkflowResult:
    """Run chronological selection, OOS resampling, ablations, and mandatory gates.

    Market-data evaluation remains injected.  The workflow owns sequencing and
    prevents a caller from marking evidence admissible unless both historical
    universe membership and data coverage have been explicitly established.
    """
    if not isinstance(point_in_time_universe, bool) or not isinstance(complete_data_coverage, bool):
        raise TypeError("admissibility flags must be booleans")
    if not math.isfinite(minimum_economic_validation_score):
        raise ValueError("minimum economic validation score must be finite")
    bootstrap_thresholds = (
        minimum_bootstrap_cagr_q05,
        minimum_bootstrap_sharpe_q05,
        maximum_bootstrap_drawdown_q95,
    )
    if any(not math.isfinite(value) for value in bootstrap_thresholds):
        raise ValueError("bootstrap gate thresholds must be finite")
    if minimum_bootstrap_cagr_q05 < -1.0 or minimum_bootstrap_sharpe_q05 < 0.0:
        raise ValueError("bootstrap lower-confidence thresholds are outside their safe ranges")
    if not 0.0 <= maximum_bootstrap_drawdown_q95 <= 1.0:
        raise ValueError("bootstrap drawdown threshold must be in [0, 1]")
    windows = build_expanding_windows(
        sessions,
        verified_complete_through=verified_complete_through,
        initial_train_years=initial_train_years,
        validation_years=validation_years,
        test_years=test_years,
        step_months=step_months,
    )
    if not windows:
        raise ValueError("validation workflow requires at least one complete fold")
    walk_forward = run_walk_forward_selection(
        windows,
        candidates,
        grid_axes,
        segment_evaluator,
        relative_tolerance=relative_tolerance,
        minimum_viable_neighbours=minimum_viable_neighbours,
    )
    evidence = evidence_evaluator(walk_forward)
    daily_returns = tuple(value for _day, value in walk_forward.stitched_test_observations)
    if len(evidence.regimes) != len(daily_returns):
        raise ValueError("evidence regimes must align with stitched OOS daily returns")
    if len(evidence.stressed_oos_returns) != len(daily_returns):
        raise ValueError("stressed returns must align with stitched OOS daily returns")
    if _terminal_wealth(evidence.stressed_oos_returns) > _terminal_wealth(daily_returns) + 1e-12:
        raise ValueError("stressed costs may not improve terminal OOS wealth")
    oos_dates = {day for day, _value in walk_forward.stitched_test_observations}
    lot_ids = [trade.lot_id for trade in evidence.realized_trades]
    if len(lot_ids) != len(set(lot_ids)):
        raise ValueError("realized trade lot IDs must be unique")
    if any(
        trade.opened_date not in oos_dates or trade.closed_date not in oos_dates
        for trade in evidence.realized_trades
    ):
        raise ValueError("realized trades must open and close on stitched OOS dates")
    trades = tuple(
        sorted(
            evidence.realized_trades,
            key=lambda trade: (trade.closed_date, trade.opened_date, trade.symbol, trade.lot_id),
        )
    )
    bootstrap = bootstrap_validation(
        daily_returns,
        tuple(trade.return_value for trade in trades),
        evidence.regimes,
        iterations=bootstrap_iterations,
        block_length=bootstrap_block_length,
        seed=bootstrap_seed,
    )
    admissible = (
        point_in_time_universe
        and complete_data_coverage
        and trusted_producer_evidence is not None
        and trusted_producer_evidence.semantically_validated
    )
    gates = assess_deployment_gates(
        _derived_gate_inputs(
            admissible=admissible,
            daily_returns=daily_returns,
            stressed_returns=evidence.stressed_oos_returns,
            trades=trades,
            walk_forward=walk_forward,
            minimum_validation_score=minimum_economic_validation_score,
            bootstrap=bootstrap,
        ),
        minimum_bootstrap_cagr_q05=minimum_bootstrap_cagr_q05,
        minimum_bootstrap_sharpe_q05=minimum_bootstrap_sharpe_q05,
        maximum_bootstrap_drawdown_q95=maximum_bootstrap_drawdown_q95,
    )
    return ValidationWorkflowResult(
        admissible_evidence=admissible,
        windows=windows,
        walk_forward=walk_forward,
        bootstrap=bootstrap,
        ablations=_run_ablations(
            walk_forward,
            ablation_evaluator,
            ablation_data_id,
            ablation_cost_id,
        ),
        gates=gates,
    )
