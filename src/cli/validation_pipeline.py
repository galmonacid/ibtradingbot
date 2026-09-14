"""Artifact-driven Phase 3 validation CLI with deterministic JSON and Markdown output."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from src.backtest.metrics import (
    TradeOutcome,
    benchmark_relative_metrics,
    performance_metrics,
)
from src.validation.ablation import AblationContext, AblationEvaluation, AblationMetrics
from src.validation.engine import SegmentEvaluation, WalkForwardEvaluation
from src.validation.report import (
    AblationSummary,
    BootstrapSummary,
    DatasetSummary,
    FoldSummary,
    SensitivitySummary,
    ValidationReport,
    write_report_files,
)
from src.validation.sensitivity import ParameterSet, parameter_grid
from src.validation.workflow import (
    RealizedTradeEvidence,
    WorkflowEvidence,
    return_metrics,
    run_validation_workflow,
)


class ValidationArtifactError(ValueError):
    """Raised when a validation artifact is incomplete or inconsistent."""


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationArtifactError(f"{name} must be a mapping")
    return cast(dict[str, Any], value)


def _list(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationArtifactError(f"{name} must be a list")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationArtifactError(f"{name} must be a non-blank string")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationArtifactError(f"{name} must be a boolean")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationArtifactError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationArtifactError(f"{name} must be finite")
    return result


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationArtifactError(f"{name} must be an integer")
    return value


def _named_scalars(value: object, name: str) -> tuple[tuple[str, Any], ...]:
    values = _mapping(value, name)
    for key, item in values.items():
        if not key or item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValidationArtifactError(f"{name} must contain named scalar values")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValidationArtifactError(f"{name}.{key} must be finite")
    return tuple(sorted(values.items()))


def _benchmark_metrics(value: object) -> tuple[tuple[str, Any], ...]:
    metrics = _named_scalars(value, "benchmark_metrics")
    if {name for name, _value in metrics} != _REQUIRED_BENCHMARK_METRICS:
        raise ValidationArtifactError(
            "benchmark_metrics must contain every canonical comparison metric"
        )
    return metrics


def _derived_performance(
    dates: tuple[date, ...],
    returns: tuple[float, ...],
    trades: tuple[RealizedTradeEvidence, ...],
    all_sessions: tuple[date, ...],
    *,
    traded_notional: float | None = None,
    exposures: tuple[float, ...] = (),
) -> dict[str, int | float | None]:
    if len(dates) != len(returns) or not dates:
        raise ValidationArtifactError("performance dates and returns must align")
    first_index = all_sessions.index(dates[0])
    if first_index == 0:
        raise ValidationArtifactError("performance needs a preceding session for its first return")
    metric_dates = (all_sessions[first_index - 1], *dates)
    equity = [1.0]
    for value in returns:
        equity.append(equity[-1] * (1.0 + value))
    outcomes = tuple(
        TradeOutcome(
            trade.return_value,
            (trade.closed_date - trade.opened_date).days,
            trade.profit_loss,
        )
        for trade in trades
    )
    metric_exposures = (exposures[0], *exposures) if exposures else ()
    values = asdict(
        performance_metrics(
            metric_dates,
            equity,
            trade_outcomes=outcomes,
            traded_notional=traded_notional,
            exposures=metric_exposures,
        )
    )
    return cast(dict[str, int | float | None], values)


def _equity(returns: tuple[float, ...]) -> tuple[float, ...]:
    values = [1.0]
    for value in returns:
        values.append(values[-1] * (1.0 + value))
    return tuple(values)


def _dates(values: object, name: str) -> tuple[date, ...]:
    raw = _list(values, name)
    try:
        return tuple(date.fromisoformat(_string(value, name)) for value in raw)
    except ValueError as error:
        raise ValidationArtifactError(f"{name} contains an invalid date") from error


_HASH_FIELDS = (
    "config_sha256",
    "data_sha256",
    "universe_sha256",
    "calendar_sha256",
    "calendar_sessions_sha256",
    "corporate_actions_sha256",
)
_VERSION_FIELDS = (
    "data_version",
    "universe_version",
    "calendar_version",
    "corporate_actions_version",
    "strategy_version",
)
_REQUIRED_PERFORMANCE_METRICS = (
    "cagr",
    "annualized_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "maximum_drawdown",
    "calmar_ratio",
    "win_rate",
    "profit_factor",
    "turnover",
    "average_holding_period",
    "exposure",
    "number_of_trades",
    "average_trade_return",
    "median_trade_return",
    "best_trade",
    "worst_trade",
    "best_month",
    "worst_month",
    "best_year",
    "worst_year",
)
_REQUIRED_SENSITIVITY_AXES = {
    "target_positions",
    "skip_recent_days",
    "target_annual_volatility",
    "risk_on_breadth_threshold",
    "rebalance_frequency",
    "rebalance_day",
    "trend_window_scale",
    "momentum_63d_weight",
    "execution_delay_sessions",
    "commission_multiplier",
    "slippage_bps_each_side",
}
_CANONICAL_AXIS_VALUES: dict[str, set[int | float | str]] = {
    "target_positions": {3, 4, 5},
    "skip_recent_days": {0, 5, 10},
    "target_annual_volatility": {0.10, 0.12, 0.15},
    "risk_on_breadth_threshold": {0.55, 0.60, 0.65},
    "rebalance_frequency": {"weekly", "biweekly"},
    "rebalance_day": {"Thursday", "Friday"},
    "trend_window_scale": {0.80, 1.00, 1.20},
    "momentum_63d_weight": {0.30, 0.35, 0.40},
    "execution_delay_sessions": {1, 2},
    "commission_multiplier": {1.0, 2.0},
    "slippage_bps_each_side": {5.0, 10.0},
}
_REQUIRED_BENCHMARK_METRICS = {
    "spy_cagr",
    "cash_cagr",
    "excess_cagr",
    "tracking_error",
    "information_ratio",
    "up_market_capture",
    "down_market_capture",
}


def _validate_oat_design(
    axes: Mapping[str, tuple[Any, ...]], candidates: tuple[ParameterSet, ...]
) -> None:
    if set(axes) != _REQUIRED_SENSITIVITY_AXES:
        raise ValidationArtifactError(
            "admissible artifacts require every canonical sensitivity axis"
        )
    for name, required in _CANONICAL_AXIS_VALUES.items():
        if not required.issubset(set(axes[name])):
            raise ValidationArtifactError(f"grid_axes.{name} omits canonical sensitivity values")
    mappings = [candidate.as_dict() for candidate in candidates]
    keys = {_parameter_key(candidate) for candidate in candidates}
    for baseline in mappings:
        if all(
            _parameter_key(ParameterSet.from_mapping({**baseline, axis: choice})) in keys
            for axis, choices in axes.items()
            for choice in choices
        ):
            return
    raise ValidationArtifactError("admissible candidates must contain one complete OAT design")


def _provenance(payload: Mapping[str, Any], artifact_sha256: str) -> tuple[tuple[str, Any], ...]:
    raw = _mapping(payload.get("provenance"), "provenance")
    revision = _string(raw.get("git_revision"), "provenance.git_revision")
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise ValidationArtifactError("provenance.git_revision must be 40 lowercase hex characters")
    normalized: dict[str, Any] = {"git_revision": revision}
    normalized["git_dirty"] = _boolean(raw.get("git_dirty"), "provenance.git_dirty")
    for field in _HASH_FIELDS:
        value = _string(raw.get(field), f"provenance.{field}")
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValidationArtifactError(f"provenance.{field} must be 64 lowercase hex characters")
        normalized[field] = value
    for field in _VERSION_FIELDS:
        normalized[field] = _string(raw.get(field), f"provenance.{field}")
    timestamp = _string(raw.get("run_timestamp_utc"), "provenance.run_timestamp_utc")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValidationArtifactError("provenance.run_timestamp_utc must be ISO-8601") from error
    if parsed_timestamp.tzinfo is None:
        raise ValidationArtifactError("provenance.run_timestamp_utc must be timezone-aware")
    normalized["run_timestamp_utc"] = timestamp
    normalized["artifact_sha256"] = artifact_sha256
    return tuple(sorted(normalized.items()))


def _parameter_key(parameters: ParameterSet) -> str:
    return json.dumps(parameters.as_dict(), sort_keys=True, separators=(",", ":"))


def _performance_metrics(value: object, name: str) -> tuple[tuple[str, Any], ...]:
    metrics = _mapping(value, name)
    if set(metrics) != set(_REQUIRED_PERFORMANCE_METRICS):
        raise ValidationArtifactError(f"{name} must contain every required performance metric")
    normalized: list[tuple[str, Any]] = []
    for key in _REQUIRED_PERFORMANCE_METRICS:
        raw = metrics[key]
        normalized.append((key, None if raw is None else _number(raw, f"{name}.{key}")))
    return tuple(normalized)


def _validate_stress_scenario(value: object) -> None:
    scenario = _mapping(value, "stress_scenario")
    expected: dict[str, object] = {
        "commission_multiplier": 2.0,
        "slippage_bps_each_side": 10.0,
        "additional_execution_delay_sessions": 1,
        "fx_buffer_unchanged": True,
    }
    if set(scenario) != set(expected):
        raise ValidationArtifactError("stress_scenario must define the canonical cost stress")
    for name, expected_value in expected.items():
        if scenario[name] != expected_value:
            raise ValidationArtifactError(f"stress_scenario.{name} must equal {expected_value!r}")


def _verify_source_files(
    value: object, *, artifact_path: Path, provenance: Mapping[str, Any]
) -> None:
    sources = _mapping(value, "source_files")
    hash_fields = {
        "config": "config_sha256",
        "data": "data_sha256",
        "universe": "universe_sha256",
        "calendar": "calendar_sha256",
        "corporate_actions": "corporate_actions_sha256",
    }
    if set(sources) != set(hash_fields):
        raise ValidationArtifactError("source_files must identify every canonical evidence source")
    for name, hash_field in hash_fields.items():
        candidate = Path(_string(sources[name], f"source_files.{name}"))
        source = candidate if candidate.is_absolute() else artifact_path.parent / candidate
        if not source.is_file():
            raise ValidationArtifactError(f"source_files.{name} does not identify a readable file")
        if hashlib.sha256(source.read_bytes()).hexdigest() != provenance[hash_field]:
            raise ValidationArtifactError(f"source_files.{name} does not match provenance hash")


def _validate_execution_audit(value: object, sessions: tuple[date, ...]) -> None:
    rows = _list(value, "execution_audit")
    if not rows:
        raise ValidationArtifactError("admissible artifacts require execution timing evidence")
    next_session = {earlier: later for earlier, later in zip(sessions, sessions[1:], strict=False)}
    for raw in rows:
        row = _mapping(raw, "execution audit row")
        signal = date.fromisoformat(_string(row.get("signal_date"), "signal_date"))
        execution = date.fromisoformat(_string(row.get("execution_date"), "execution_date"))
        if next_session.get(signal) != execution:
            raise ValidationArtifactError("execution must occur on the next available session")


def run_artifact(path: Path, *, json_output: Path, markdown_output: Path) -> ValidationReport:
    """Validate one immutable backtest artifact and write both report forms."""
    payload = _mapping(json.loads(path.read_text(encoding="utf-8")), "artifact")
    _validate_stress_scenario(payload.get("stress_scenario"))
    sessions = _dates(payload.get("sessions"), "sessions")
    session_bytes = "".join(f"{session.isoformat()}\n" for session in sessions).encode()
    session_sha256 = hashlib.sha256(session_bytes).hexdigest()
    axes_raw = _mapping(payload.get("grid_axes"), "grid_axes")
    axes = {key: tuple(_list(value, f"grid_axes.{key}")) for key, value in axes_raw.items()}
    candidate_rows = payload.get("candidates")
    candidates = (
        tuple(
            ParameterSet.from_mapping(_mapping(row, "candidates item"))
            for row in _list(candidate_rows, "candidates")
        )
        if candidate_rows is not None
        else parameter_grid(axes)
    )
    fold_results = _mapping(payload.get("fold_results"), "fold_results")

    def segment_evaluator(
        context: Any, parameters: ParameterSet, segment: str
    ) -> SegmentEvaluation:
        fold = _mapping(fold_results.get(str(context.fold_index)), "fold result")
        if segment == "validation":
            scores = _mapping(fold.get("validation_scores"), "validation_scores")
            try:
                score = _number(scores[_parameter_key(parameters)], "validation score")
            except KeyError as error:
                raise ValidationArtifactError("missing validation score for a candidate") from error
            return SegmentEvaluation(score)
        returns_by_parameter = _mapping(fold.get("test_returns"), "test_returns")
        dated = _mapping(
            returns_by_parameter.get(_parameter_key(parameters)), "selected test returns"
        )
        observations = tuple(
            (day, _number(dated.get(day.isoformat()), "test return"))
            for day in context.evaluation_dates
        )
        return SegmentEvaluation(0.0, observations)

    evidence_values = _mapping(payload.get("evidence"), "evidence")
    regimes_by_date = _mapping(evidence_values.get("regimes_by_date"), "regimes_by_date")

    def evidence_evaluator(result: WalkForwardEvaluation) -> WorkflowEvidence:
        dates = tuple(day for day, _value in result.stitched_test_observations)
        stressed_by_date = _mapping(
            evidence_values.get("stressed_returns_by_date"), "stressed_returns_by_date"
        )
        trades: list[RealizedTradeEvidence] = []
        for raw_trade in _list(evidence_values.get("realized_trades"), "realized_trades"):
            trade = _mapping(raw_trade, "realized trade")
            trades.append(
                RealizedTradeEvidence(
                    _string(trade.get("lot_id"), "lot_id"),
                    date.fromisoformat(_string(trade.get("opened_date"), "opened_date")),
                    date.fromisoformat(_string(trade.get("closed_date"), "closed_date")),
                    _string(trade.get("symbol"), "symbol"),
                    _number(trade.get("basis"), "basis"),
                    _number(trade.get("proceeds"), "proceeds"),
                )
            )
        return WorkflowEvidence(
            tuple(_string(regimes_by_date.get(day.isoformat()), "regime") for day in dates),
            tuple(
                _number(stressed_by_date.get(day.isoformat()), "stressed return") for day in dates
            ),
            tuple(trades),
        )

    ablation_values = _mapping(payload.get("ablation_returns"), "ablation_returns")

    def ablation_evaluator(scenario: Any, context: AblationContext) -> AblationEvaluation:
        dated = _mapping(ablation_values.get(scenario.name), scenario.name)
        returns = tuple(
            _number(dated.get(day.isoformat()), f"{scenario.name} return")
            for day in context.oos_dates
        )
        cagr, sharpe, drawdown = return_metrics(returns)
        return AblationEvaluation(
            context,
            AblationMetrics.from_mapping(
                {
                    "cagr": cagr,
                    "sharpe_ratio": sharpe,
                    "maximum_drawdown": drawdown,
                }
            ),
        )

    settings = _mapping(payload.get("settings"), "settings")
    dataset = _mapping(payload.get("dataset"), "dataset")
    synthetic = _boolean(dataset.get("synthetic"), "dataset.synthetic")
    if not synthetic:
        _validate_oat_design(axes, candidates)
    point_in_time = _boolean(payload.get("point_in_time_universe"), "point_in_time_universe")
    complete_coverage = _boolean(payload.get("complete_data_coverage"), "complete_data_coverage")
    provenance_raw = _mapping(payload.get("provenance"), "provenance")
    if not synthetic:
        _verify_source_files(
            payload.get("source_files"), artifact_path=path, provenance=provenance_raw
        )
        _validate_execution_audit(payload.get("execution_audit"), sessions)
    if provenance_raw.get("calendar_sessions_sha256") != session_sha256:
        raise ValidationArtifactError("sessions do not match provenance calendar session hash")
    universe_source = _string(payload.get("universe_source"), "universe_source")
    verified_pit = point_in_time and universe_source == "point_in_time"
    result = run_validation_workflow(
        sessions,
        candidates,
        axes,
        segment_evaluator,
        evidence_evaluator,
        verified_complete_through=date.fromisoformat(
            _string(payload.get("verified_complete_through"), "verified_complete_through")
        ),
        # An artifact and its hashes can establish reproducibility, but cannot prove the
        # point-in-time semantics or cross-sectional completeness of caller-owned files.
        # Until a trusted producer validates those sources in process, artifact-only runs
        # are deliberately ineligible for deployment evidence.
        point_in_time_universe=False,
        complete_data_coverage=complete_coverage and not synthetic,
        ablation_evaluator=ablation_evaluator,
        ablation_data_id=_string(payload.get("data_id"), "data_id"),
        ablation_cost_id=_string(payload.get("cost_id"), "cost_id"),
        initial_train_years=_integer(settings.get("initial_train_years", 8), "initial_train_years"),
        validation_years=_integer(settings.get("validation_years", 2), "validation_years"),
        test_years=_integer(settings.get("test_years", 1), "test_years"),
        step_months=_integer(settings.get("step_months", 6), "step_months"),
        bootstrap_iterations=_integer(
            settings.get("bootstrap_iterations", 2000), "bootstrap_iterations"
        ),
        bootstrap_block_length=_integer(
            settings.get("bootstrap_block_length", 20), "bootstrap_block_length"
        ),
        bootstrap_seed=_integer(settings.get("bootstrap_seed", 0), "bootstrap_seed"),
        minimum_economic_validation_score=_number(
            settings.get("minimum_economic_validation_score", 0.60),
            "minimum_economic_validation_score",
        ),
        minimum_bootstrap_cagr_q05=_number(
            settings.get("minimum_bootstrap_cagr_q05", 0.0),
            "minimum_bootstrap_cagr_q05",
        ),
        minimum_bootstrap_sharpe_q05=_number(
            settings.get("minimum_bootstrap_sharpe_q05", 0.0),
            "minimum_bootstrap_sharpe_q05",
        ),
        maximum_bootstrap_drawdown_q95=_number(
            settings.get("maximum_bootstrap_drawdown_q95", 0.25),
            "maximum_bootstrap_drawdown_q95",
        ),
    )
    artifact_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = _provenance(payload, artifact_sha256)
    if _string(dataset.get("version"), "dataset.version") != provenance_raw["data_version"]:
        raise ValidationArtifactError("dataset.version must match provenance.data_version")
    if _string(payload.get("data_id"), "data_id") != provenance_raw["data_sha256"]:
        raise ValidationArtifactError("data_id must match provenance.data_sha256")
    folds = tuple(
        FoldSummary(
            fold.window.index,
            f"{fold.window.train[0]} to {fold.window.train[-1]}",
            f"{fold.window.validation[0]} to {fold.window.validation[-1]}",
            f"{fold.window.test[0]} to {fold.window.test[-1]}",
            fold.selection.selected.parameters.values,
            len(fold.test.observations),
        )
        for fold in result.walk_forward.folds
    )
    sensitivity = tuple(
        SensitivitySummary(
            fold.window.index,
            score.parameters.values,
            score.validation_score,
            score.parameters == fold.selection.selected.parameters,
            score in fold.selection.viable,
        )
        for fold in result.walk_forward.folds
        for score in fold.validation_scores
    )
    bootstrap_items: list[BootstrapSummary] = []
    bootstrap_sources = [
        ("daily", result.bootstrap.daily),
        ("regime_blocks", result.bootstrap.regime_blocks),
    ]
    for source, metrics in bootstrap_sources:
        for metric, distribution in (
            ("cagr", metrics.cagr),
            ("maximum_drawdown", metrics.maximum_drawdown),
            ("sharpe_ratio", metrics.sharpe_ratio),
            ("one_year_return", metrics.one_year_return),
            ("three_year_return", metrics.three_year_return),
        ):
            if distribution is not None:
                bootstrap_items.append(
                    BootstrapSummary(
                        source, metric, distribution.q05, distribution.q50, distribution.q95
                    )
                )
    if result.bootstrap.mean_trade_return is not None:
        item = result.bootstrap.mean_trade_return
        bootstrap_items.append(
            BootstrapSummary("trade_returns", "mean", item.q05, item.q50, item.q95)
        )
    bootstrap = tuple(bootstrap_items)
    ablations = (
        tuple(
            AblationSummary(item.scenario.name, item.metrics.values, item.deltas_vs_full.values)
            for item in result.ablations.results
        )
        if result.ablations is not None
        else ()
    )
    limitations_raw = _list(payload.get("limitations"), "limitations")
    limitations = tuple(_string(item, "limitations item") for item in limitations_raw)
    if synthetic and not limitations:
        raise ValidationArtifactError("synthetic artifacts must state a limitation")
    strategy_metrics = _performance_metrics(payload.get("strategy_metrics"), "strategy_metrics")
    stressed_metrics = _performance_metrics(payload.get("stressed_metrics"), "stressed_metrics")
    derived_strategy_names = {"cagr", "sharpe_ratio", "maximum_drawdown", "number_of_trades"}
    derived_stress_names = {"cagr", "sharpe_ratio"}
    if any(
        value is not None for name, value in strategy_metrics if name not in derived_strategy_names
    ):
        raise ValidationArtifactError("non-derived strategy metrics must be null")
    if any(
        value is not None for name, value in stressed_metrics if name not in derived_stress_names
    ):
        raise ValidationArtifactError("non-derived stressed metrics must be null")
    gate_by_name = result.gates.by_name()
    for metric_name, gate_name in (
        ("cagr", "out_of_sample_cagr"),
        ("sharpe_ratio", "out_of_sample_sharpe"),
        ("maximum_drawdown", "out_of_sample_maximum_drawdown"),
    ):
        reported = dict(strategy_metrics)[metric_name]
        derived = gate_by_name[gate_name].observed
        if reported is not None:
            if isinstance(derived, bool) or not isinstance(derived, (int, float)):
                raise ValidationArtifactError(f"derived {gate_name} is unavailable")
            if not math.isclose(float(reported), float(derived), abs_tol=1e-12):
                raise ValidationArtifactError(
                    f"strategy_metrics.{metric_name} contradicts OOS returns"
                )
    for metric_name, gate_name in (
        ("cagr", "stressed_cagr"),
        ("sharpe_ratio", "stressed_sharpe"),
    ):
        reported = dict(stressed_metrics)[metric_name]
        derived = gate_by_name[gate_name].observed
        if reported is not None:
            if isinstance(derived, bool) or not isinstance(derived, (int, float)):
                raise ValidationArtifactError(f"derived {gate_name} is unavailable")
            if not math.isclose(float(reported), float(derived), abs_tol=1e-12):
                raise ValidationArtifactError(f"stressed_metrics.{metric_name} contradicts returns")
    oos_observations = result.walk_forward.stitched_test_observations
    oos_dates = tuple(day for day, _value in oos_observations)
    oos_returns = tuple(value for _day, value in oos_observations)
    derived_evidence = evidence_evaluator(result.walk_forward)
    exposure_by_date = _mapping(
        evidence_values.get("exposure_by_date"), "evidence.exposure_by_date"
    )
    exposures = tuple(
        _number(exposure_by_date.get(day.isoformat()), "daily exposure") for day in oos_dates
    )
    traded_notional = _number(evidence_values.get("traded_notional"), "evidence.traded_notional")
    strategy_values = _derived_performance(
        oos_dates,
        oos_returns,
        derived_evidence.realized_trades,
        sessions,
        traded_notional=traded_notional,
        exposures=exposures,
    )
    strategy_values.update(
        {
            "cagr": gate_by_name["out_of_sample_cagr"].observed,
            "sharpe_ratio": gate_by_name["out_of_sample_sharpe"].observed,
            "maximum_drawdown": gate_by_name["out_of_sample_maximum_drawdown"].observed,
            "number_of_trades": gate_by_name["closed_trades"].observed,
        }
    )
    strategy_drawdown = strategy_values["maximum_drawdown"]
    strategy_cagr = strategy_values["cagr"]
    strategy_values["calmar_ratio"] = (
        float(strategy_cagr) / float(strategy_drawdown)
        if isinstance(strategy_cagr, (int, float))
        and isinstance(strategy_drawdown, (int, float))
        and strategy_drawdown > 1e-15
        else None
    )
    stressed_values = _derived_performance(
        oos_dates, derived_evidence.stressed_oos_returns, (), sessions
    )
    for name in (
        "number_of_trades",
        "win_rate",
        "profit_factor",
        "average_holding_period",
        "average_trade_return",
        "median_trade_return",
        "best_trade",
        "worst_trade",
        "turnover",
        "exposure",
    ):
        stressed_values[name] = None
    stressed_values.update(
        {
            "cagr": gate_by_name["stressed_cagr"].observed,
            "sharpe_ratio": gate_by_name["stressed_sharpe"].observed,
        }
    )
    strategy_metrics = tuple(
        (name, strategy_values[name]) for name in _REQUIRED_PERFORMANCE_METRICS
    )
    stressed_metrics = tuple(
        (name, stressed_values[name]) for name in _REQUIRED_PERFORMANCE_METRICS
    )
    benchmark_returns_raw = _mapping(
        evidence_values.get("benchmark_returns_by_date"),
        "evidence.benchmark_returns_by_date",
    )
    cash_returns_raw = _mapping(
        evidence_values.get("cash_returns_by_date"), "evidence.cash_returns_by_date"
    )
    benchmark_returns = tuple(
        _number(benchmark_returns_raw.get(day.isoformat()), "benchmark return") for day in oos_dates
    )
    cash_returns = tuple(
        _number(cash_returns_raw.get(day.isoformat()), "cash return") for day in oos_dates
    )
    metric_dates = (sessions[sessions.index(oos_dates[0]) - 1], *oos_dates)
    benchmark_absolute = performance_metrics(metric_dates, _equity(benchmark_returns))
    cash_absolute = performance_metrics(metric_dates, _equity(cash_returns))
    relative = benchmark_relative_metrics(
        metric_dates, _equity(oos_returns), _equity(benchmark_returns)
    )
    derived_benchmark: dict[str, float | None] = {
        "spy_cagr": benchmark_absolute.cagr,
        "cash_cagr": cash_absolute.cagr,
        "excess_cagr": relative.excess_cagr,
        "tracking_error": relative.tracking_error,
        "information_ratio": relative.information_ratio,
        "up_market_capture": relative.up_market_capture,
        "down_market_capture": relative.down_market_capture,
    }
    reported_benchmark = dict(_benchmark_metrics(payload.get("benchmark_metrics")))
    for name, reported in reported_benchmark.items():
        derived = derived_benchmark[name]
        if reported is not None and (
            derived is None or not math.isclose(float(reported), derived, abs_tol=1e-12)
        ):
            raise ValidationArtifactError(f"benchmark_metrics.{name} contradicts dated returns")
    report = ValidationReport(
        title="Phase 3 Research Report",
        provenance=provenance,
        dataset=DatasetSummary(
            _string(dataset.get("name"), "dataset.name"),
            _string(dataset.get("version"), "dataset.version"),
            verified_pit,
            synthetic,
            sessions[0].isoformat(),
            sessions[-1].isoformat(),
            len(sessions),
        ),
        admissible_evidence=result.admissible_evidence,
        folds=folds,
        sensitivity=sensitivity,
        bootstrap=bootstrap,
        ablations=ablations,
        strategy_metrics=strategy_metrics,
        stressed_metrics=stressed_metrics,
        benchmark_metrics=tuple(sorted(derived_benchmark.items())),
        gates=result.gates,
        limitations=limitations,
    )
    write_report_files(report, json_path=json_output, markdown_path=markdown_output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a fail-closed Phase 3 validation report."
    )
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_artifact(
            args.artifact,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
