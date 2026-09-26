"""Closed native canonical-to-walk-forward-report orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.data.execution_audit import ExecutionAuditReport
from src.validation.native_execution import NativeBacktestRun
from src.validation.native_inputs import NativeValidationInputs
from src.validation.native_strategy import NativeTargetSet
from src.validation.native_workflow import NativeValidationWorkflow, run_native_validation_workflow
from src.validation.report import (
    AblationSummary,
    BootstrapSummary,
    DatasetSummary,
    FoldSummary,
    NamedValues,
    SensitivitySummary,
    ValidationReport,
    report_as_dict,
    write_report_files,
)
from src.validation.workflow import return_metrics


class NativeReportError(ValueError):
    """Raised when a native report cannot be derived safely."""


_NATIVE_REPORT_ATTESTATION = object()


@dataclass(frozen=True)
class NativeValidationReport:
    """Attested native output retaining the complete chain of evidence."""

    inputs: NativeValidationInputs
    targets: NativeTargetSet
    baseline: NativeBacktestRun
    stressed: NativeBacktestRun
    execution_audit: ExecutionAuditReport
    report: ValidationReport
    report_sha256: str
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _NATIVE_REPORT_ATTESTATION:
            raise NativeReportError("native reports must be issued by the native report builder")


def _metrics(values: tuple[float, ...]) -> NamedValues:
    cagr, sharpe, drawdown = return_metrics(values)
    return (("cagr", cagr), ("maximum_drawdown", drawdown), ("sharpe_ratio", sharpe))


def _benchmark_metrics(inputs: NativeValidationInputs, dates: tuple[date, ...]) -> NamedValues:
    benchmark = inputs.config.benchmark
    by_date = {
        row.date: row.adjusted_close for row in inputs.canonical.bars if row.symbol == benchmark
    }
    if any(day not in by_date for day in dates):
        raise NativeReportError("benchmark is missing a native execution session")
    ordered = tuple(sorted(by_date))
    prior = tuple(day for day in ordered if day < dates[0])
    if not prior:
        raise NativeReportError("benchmark lacks the pre-OOS session needed for alignment")
    prices = tuple(by_date[day] for day in (prior[-1], *dates))
    returns = tuple(
        current / prior - 1.0 for prior, current in zip(prices, prices[1:], strict=False)
    )
    return tuple((f"benchmark_{name}", value) for name, value in _metrics(returns))


def _bootstrap_summaries(workflow: NativeValidationWorkflow) -> tuple[BootstrapSummary, ...]:
    analysis = workflow.bootstrap
    summaries: list[BootstrapSummary] = []
    for source, collection in (
        ("daily", analysis.daily),
        ("regime_blocks", analysis.regime_blocks),
    ):
        distributions = [
            ("cagr", collection.cagr),
            ("maximum_drawdown", collection.maximum_drawdown),
        ]
        if collection.sharpe_ratio is not None:
            distributions.append(("sharpe_ratio", collection.sharpe_ratio))
        if collection.one_year_return is not None:
            distributions.append(("one_year_return", collection.one_year_return))
        if collection.three_year_return is not None:
            distributions.append(("three_year_return", collection.three_year_return))
        summaries.extend(
            BootstrapSummary(source, metric, value.q05, value.q50, value.q95)
            for metric, value in distributions
        )
    if analysis.mean_trade_return is not None:
        value = analysis.mean_trade_return
        summaries.append(
            BootstrapSummary("closed_trades", "mean_trade_return", value.q05, value.q50, value.q95)
        )
    return tuple(summaries)


def _ablation_summaries(workflow: NativeValidationWorkflow) -> tuple[AblationSummary, ...]:
    full = next(item for item in workflow.ablations if item.name == "full_deterministic")
    result: list[AblationSummary] = []
    for item in workflow.ablations:
        metrics: NamedValues = (
            ("cagr", item.cagr),
            ("maximum_drawdown", item.maximum_drawdown),
            ("sharpe_ratio", item.sharpe_ratio),
            ("executable", item.executable),
        )
        deltas: NamedValues = (
            (
                "cagr",
                None
                if item.cagr is None or full.cagr is None
                else item.cagr - full.cagr,
            ),
            (
                "maximum_drawdown",
                None
                if item.maximum_drawdown is None or full.maximum_drawdown is None
                else item.maximum_drawdown - full.maximum_drawdown,
            ),
            (
                "sharpe_ratio",
                None
                if item.sharpe_ratio is None or full.sharpe_ratio is None
                else item.sharpe_ratio - full.sharpe_ratio,
            ),
            ("executable", None),
        )
        result.append(AblationSummary(item.name, metrics, deltas))
    return tuple(result)


def build_native_validation_report(
    inputs: NativeValidationInputs,
    *,
    workflow: NativeValidationWorkflow | None = None,
) -> NativeValidationReport:
    """Build the content-bound native walk-forward validation report."""
    workflow = workflow or run_native_validation_workflow(inputs)
    if workflow.validation_run_id != inputs.identity.validation_run_id:
        raise NativeReportError("native workflow belongs to a different validation run")
    targets = workflow.targets
    baseline = workflow.baseline_run
    stressed = workflow.stressed_run
    audit = workflow.execution_audits[0]
    oos = tuple(value for _day, value in workflow.walk_forward.stitched_test_observations)
    oos_dates = tuple(day for day, _value in workflow.walk_forward.stitched_test_observations)
    identity = inputs.identity
    provenance: NamedValues = tuple(
        sorted(
            (
                ("validation_run_id", identity.validation_run_id),
                ("canonical_manifest_sha256", identity.canonical_manifest_sha256),
                ("config_sha256", identity.config_sha256),
                ("strategy_version", identity.strategy_version),
                ("strategy_definition_sha256", identity.strategy_definition_sha256),
                ("validation_spec_sha256", identity.validation_spec_sha256),
                ("dataset_evidence_sha256", identity.dataset_evidence_sha256),
                ("universe_policy_sha256", identity.universe_policy_sha256),
                ("git_revision", identity.git_revision),
                ("git_dirty", identity.git_dirty),
                ("target_sha256", targets.target_sha256),
                ("market_input_sha256", baseline.market_input_sha256),
                ("baseline_trace_sha256", audit.baseline_trace_sha256),
                ("stressed_trace_sha256", audit.stressed_trace_sha256),
                ("bootstrap_iterations", workflow.bootstrap.iterations),
                ("bootstrap_block_length", workflow.bootstrap.block_length),
                ("bootstrap_seed", workflow.bootstrap.seed),
                ("bootstrap_daily_method", "circular_moving_block"),
                ("bootstrap_regime_method", "complete_regime_episode_block"),
                ("bootstrap_trade_method", "circular_moving_block_closed_trade_mean"),
                (
                    "execution_audit_sha256",
                    hashlib.sha256(audit.to_json().encode()).hexdigest(),
                ),
            )
        )
    )
    report = ValidationReport(
        title="Phase 3 Native Historical Validation",
        provenance=provenance,
        dataset=DatasetSummary(
            "trusted-canonical",
            inputs.canonical.transformation_version,
            True,
            False,
            oos_dates[0].isoformat(),
            oos_dates[-1].isoformat(),
            len(oos_dates),
        ),
        admissible_evidence=inputs.dataset_certified,
        folds=tuple(
            FoldSummary(
                fold.window.index,
                f"{fold.window.train[0]}..{fold.window.train[-1]}",
                f"{fold.window.validation[0]}..{fold.window.validation[-1]}",
                f"{fold.window.test[0]}..{fold.window.test[-1]}",
                fold.selection.selected.parameters.values,
                len(fold.test.observations),
            )
            for fold in workflow.walk_forward.folds
        ),
        sensitivity=tuple(
            SensitivitySummary(
                fold.window.index,
                score.parameters.values,
                score.validation_score,
                score == fold.selection.selected,
                score in fold.selection.viable,
            )
            for fold in workflow.walk_forward.folds
            for score in fold.validation_scores
        ),
        bootstrap=_bootstrap_summaries(workflow),
        ablations=_ablation_summaries(workflow),
        strategy_metrics=_metrics(oos),
        stressed_metrics=_metrics(workflow.stressed_oos_returns),
        benchmark_metrics=_benchmark_metrics(inputs, oos_dates),
        gates=workflow.gates,
        limitations=(
            "Open-source membership begins in 1996; the certified 400-name validation horizon "
            f"begins {inputs.validation_start} after Tiingo availability and quality exclusions.",
            "Wikipedia and IVV QA are separate evidence streams from one pinned riazarbi "
            "repository.",
            "Sensitivity score -1e9 denotes a candidate that could not execute without "
            "violating a hard portfolio constraint; it is retained as failed evidence.",
            "Sensitivity is a predeclared one-axis-at-a-time design around the production "
            "baseline across every configured axis; it is not a Cartesian interaction search.",
            "Ablations marked executable=no are not assigned fabricated performance metrics.",
            "A passing report permits Phase 4 paper evaluation only; it never authorizes "
            "live trading.",
        ),
    )
    report_sha256 = hashlib.sha256(
        json.dumps(report_as_dict(report), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return NativeValidationReport(
        inputs,
        targets,
        baseline,
        stressed,
        audit,
        report,
        report_sha256,
        _NATIVE_REPORT_ATTESTATION,
    )


def write_native_validation_report(
    result: NativeValidationReport, *, json_path: Path, markdown_path: Path
) -> None:
    """Write only a builder-issued native report."""
    write_report_files(result.report, json_path=json_path, markdown_path=markdown_path)
