"""Native chronological Phase 3 validation derived solely from canonical inputs."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from datetime import date
from statistics import fmean, stdev

from src.backtest.costs import CostModel
from src.backtest.engine import BacktestDataError
from src.data.execution_audit import (
    ExecutionAuditReport,
    audit_bound_native_backtest_executions,
)
from src.validation.ablation import DETERMINISTIC_COMPONENTS
from src.validation.bootstrap import BootstrapAnalysis, bootstrap_validation
from src.validation.engine import (
    EvaluationContext,
    FoldEvaluation,
    SegmentEvaluation,
    WalkForwardEvaluation,
    run_walk_forward_selection,
)
from src.validation.gates import (
    DeploymentGateAssessment,
    DeploymentGateInputs,
    assess_deployment_gates,
)
from src.validation.native_execution import (
    NativeBacktestRun,
    NativeMarketContext,
    build_native_market_context,
    run_native_backtest,
)
from src.validation.native_inputs import NativeValidationInputs
from src.validation.native_strategy import (
    NativeStrategyContext,
    NativeStrategyParameters,
    NativeTargetSet,
    build_native_regimes,
    build_native_strategy_context,
    build_native_targets,
    compose_native_targets,
)
from src.validation.sensitivity import ParameterSet
from src.validation.walk_forward import WalkForwardWindow, build_expanding_windows
from src.validation.workflow import RealizedTradeEvidence, return_metrics


class NativeWorkflowError(ValueError):
    """Raised when native chronological evidence cannot be completed."""


_ATTESTATION = object()


@dataclass(frozen=True)
class NativeAblationResult:
    name: str
    cagr: float | None
    sharpe_ratio: float | None
    maximum_drawdown: float | None
    executable: bool


@dataclass(frozen=True)
class NativeValidationWorkflow:
    validation_run_id: str
    windows: tuple[WalkForwardWindow, ...]
    walk_forward: WalkForwardEvaluation
    stressed_oos_returns: tuple[float, ...]
    bootstrap: BootstrapAnalysis
    ablations: tuple[NativeAblationResult, ...]
    execution_audits: tuple[ExecutionAuditReport, ...]
    baseline_run: NativeBacktestRun
    stressed_run: NativeBacktestRun
    realized_trades: tuple[RealizedTradeEvidence, ...]
    targets: NativeTargetSet
    gates: DeploymentGateAssessment
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _ATTESTATION:
            raise NativeWorkflowError(
                "native workflow results must be issued by the native builder"
            )


def _returns(run: NativeBacktestRun) -> dict[date, float]:
    points = run.result.equity_curve
    return {
        current.date: current.equity / previous.equity - 1.0
        for previous, current in zip(points, points[1:], strict=False)
    }


def _score(values: tuple[float, ...]) -> float:
    if not values:
        raise NativeWorkflowError("validation segment contains no native returns")
    if len(values) > 1:
        deviation = stdev(values)
        if deviation > 1e-15:
            return fmean(values) / deviation * math.sqrt(252.0)
    return math.prod(1.0 + value for value in values) - 1.0


def _candidate_grid(
    inputs: NativeValidationInputs,
) -> tuple[
    tuple[ParameterSet, ...], dict[str, tuple[int | float | str, ...]]
]:
    strategy = inputs.config.values["strategy"]
    if not isinstance(strategy, dict):
        raise NativeWorkflowError("validated strategy configuration is malformed")
    axes = inputs.config.sensitivity_grid
    validation = inputs.config.values["validation"]
    regime = inputs.config.values["regime"]
    portfolio = inputs.config.values["portfolio"]
    costs = inputs.config.values["costs"]
    if not all(isinstance(item, dict) for item in (validation, regime, portfolio, costs)):
        raise NativeWorkflowError("validated sensitivity configuration is malformed")
    momentum = inputs.config.momentum_weights
    baseline: dict[str, int | float | str] = {
        "target_positions": int(strategy["target_positions"]),
        "skip_recent_days": int(strategy["momentum"]["skip_recent_days"]),
        "target_annual_volatility": float(portfolio["target_annual_volatility"]),
        "risk_on_breadth_threshold": float(regime["risk_on_breadth_threshold"]),
        "rebalance_frequency": str(strategy["rebalance_frequency"]),
        "rebalance_day": str(strategy["rebalance_day"]),
        "trend_window_scale": 1.0,
        "momentum_63d_weight": momentum[0],
        "execution_delay_sessions": 1,
        "commission_multiplier": 1.0,
        "slippage_bps_each_side": float(costs["slippage_bps_each_side"]),
    }
    if any(baseline[key] not in choices for key, choices in axes.items()):
        raise NativeWorkflowError(
            "configured sensitivity axes must contain the production baseline"
        )
    candidates = [ParameterSet.from_mapping(baseline)]
    for key in sorted(axes):
        for value in axes[key]:
            if value != baseline[key]:
                candidates.append(ParameterSet.from_mapping({**baseline, key: value}))
    return tuple(candidates), axes


def _native_parameters(parameters: ParameterSet) -> NativeStrategyParameters:
    values = parameters.as_dict()
    return NativeStrategyParameters(
        target_positions=int(values["target_positions"]),
        skip_recent_days=int(values["skip_recent_days"]),
        target_annual_volatility=float(values["target_annual_volatility"]),
        risk_on_breadth_threshold=float(values["risk_on_breadth_threshold"]),
        rebalance_frequency=str(values["rebalance_frequency"]),
        rebalance_day=str(values["rebalance_day"]),
        trend_window_scale=float(values["trend_window_scale"]),
        momentum_63d_weight=float(values["momentum_63d_weight"]),
        execution_delay_sessions=int(values["execution_delay_sessions"]),
        commission_multiplier=float(values["commission_multiplier"]),
        slippage_bps_each_side=float(values["slippage_bps_each_side"]),
    )


def _realized_trades(run: NativeBacktestRun) -> tuple[RealizedTradeEvidence, ...]:
    """Attribute exact execution costs to FIFO lots in the issued OOS run."""
    lots: dict[str, deque[tuple[str, date, float, float]]] = defaultdict(deque)
    realized: list[RealizedTradeEvidence] = []
    lot_number = 0
    close_number = 0
    for trade in run.result.trades:
        unit_cost = trade.total_cost / trade.shares
        if trade.side == "buy":
            lot_number += 1
            lots[trade.symbol].append(
                (
                    f"{trade.symbol}-{lot_number}",
                    trade.date,
                    trade.shares,
                    trade.execution_price + unit_cost,
                )
            )
            continue
        remaining = trade.shares
        while remaining > 1e-10:
            if not lots[trade.symbol]:
                raise NativeWorkflowError("native sell execution exceeds FIFO holdings")
            lot_id, opened, shares, basis_per_share = lots[trade.symbol].popleft()
            closed = min(shares, remaining)
            close_number += 1
            realized.append(
                RealizedTradeEvidence(
                    f"{lot_id}-close-{close_number}",
                    opened,
                    trade.date,
                    trade.symbol,
                    closed * basis_per_share,
                    closed * (trade.execution_price - unit_cost),
                )
            )
            remaining -= closed
            if shares - closed > 1e-10:
                lots[trade.symbol].appendleft(
                    (lot_id, opened, shares - closed, basis_per_share)
                )
    return tuple(realized)


def _apply_trading_session_embargo(
    windows: tuple[WalkForwardWindow, ...], sessions: int
) -> tuple[WalkForwardWindow, ...]:
    """Remove exactly ``sessions`` observations from each validation tail."""
    if sessions < 0:
        raise NativeWorkflowError("embargo sessions must be non-negative")
    if not sessions:
        return windows
    if any(len(window.validation) <= sessions for window in windows):
        raise NativeWorkflowError("trading-session embargo consumes a validation segment")
    result = tuple(
        WalkForwardWindow(window.index, window.train, window.validation[:-sessions], window.test)
        for window in windows
    )
    return result


def _validate_selected_execution_costs(
    selected: dict[int, NativeStrategyParameters], inputs: NativeValidationInputs
) -> None:
    """Fail closed because a continuous engine cannot change costs between folds."""
    configured_slippage = inputs.config.transaction_costs[1]
    if any(
        item.commission_multiplier != 1.0
        or item.slippage_bps_each_side != configured_slippage
        for item in selected.values()
    ):
        raise NativeWorkflowError(
            "a selected fold changes execution costs; fold-varying costs cannot be "
            "silently discarded by the continuous OOS run"
        )


def _sequential_targets(
    inputs: NativeValidationInputs,
    context: NativeStrategyContext,
    owner_by_date: dict[date, int],
    selected_by_fold: dict[int, NativeStrategyParameters],
    *,
    disabled_component: str | None = None,
) -> NativeTargetSet:
    """Build fold-owned targets while carrying only actual prior OOS incumbents."""
    selections: list[tuple[NativeTargetSet, tuple[date, ...]]] = []
    incumbents: tuple[str, ...] = ()
    for fold_index in dict.fromkeys(owner_by_date.values()):
        execution_dates = {
            day for day, owner in owner_by_date.items() if owner == fold_index
        }
        parameters = replace(
            selected_by_fold[fold_index], disabled_component=disabled_component
        )
        target_set = build_native_targets(
            inputs,
            parameters,
            context=context,
            allowed_execution_dates=execution_dates,
            initial_incumbents=incumbents,
        )
        selections.append((target_set, target_set.signal_dates))
        if target_set.signal_dates:
            incumbents = tuple(
                target_set.targets_by_signal_date[target_set.signal_dates[-1]]
            )
    return compose_native_targets(
        inputs,
        selections,
        parameters=NativeStrategyParameters(disabled_component=disabled_component),
    )


def run_native_validation_workflow(
    inputs: NativeValidationInputs,
    *,
    initial_train_years: int | None = None,
    validation_years: int | None = None,
    test_years: int | None = None,
    step_months: int | None = None,
    bootstrap_iterations: int | None = None,
    bootstrap_block_length: int | None = None,
    bootstrap_seed: int | None = None,
    strategy_context: NativeStrategyContext | None = None,
    market_context: NativeMarketContext | None = None,
) -> NativeValidationWorkflow:
    """Select on validation dates and issue untouched, audited native OOS evidence."""
    all_sessions = tuple(
        sorted({row.date for row in inputs.canonical.bars if row.symbol == inputs.config.benchmark})
    )
    sessions = all_sessions
    if inputs.validation_start is not None:
        sessions = tuple(day for day in sessions if day >= inputs.validation_start)
    configured_windows = inputs.config.validation_windows
    window_values = (
        initial_train_years or configured_windows[0],
        validation_years or configured_windows[1],
        test_years or configured_windows[2],
        step_months or configured_windows[3],
    )
    windows = build_expanding_windows(
        sessions,
        verified_complete_through=sessions[-1],
        initial_train_years=window_values[0],
        validation_years=window_values[1],
        test_years=window_values[2],
        step_months=window_values[3],
    )
    validation_section = inputs.config.values["validation"]
    if not isinstance(validation_section, dict):
        raise NativeWorkflowError("validated validation configuration is malformed")
    embargo_days = int(validation_section["embargo_days"])
    windows = _apply_trading_session_embargo(windows, embargo_days)
    if not windows:
        raise NativeWorkflowError("native validation requires at least one complete fold")
    candidates, axes = _candidate_grid(inputs)
    context = strategy_context or build_native_strategy_context(inputs)
    execution_context = market_context or build_native_market_context(inputs)
    cache: dict[tuple[NativeStrategyParameters, str, date, date], NativeBacktestRun] = {}
    failed_candidates: set[tuple[NativeStrategyParameters, str, date, date]] = set()

    def get_run(
        parameters: NativeStrategyParameters,
        scenario: str,
        evaluation_dates: tuple[date, ...],
    ) -> NativeBacktestRun:
        key = (parameters, scenario, evaluation_dates[0], evaluation_dates[-1])
        if key in failed_candidates:
            raise BacktestDataError("native sensitivity candidate is not executable")
        if key not in cache:
            evaluation_set = set(evaluation_dates)
            targets = build_native_targets(
                inputs,
                parameters,
                context=context,
                allowed_execution_dates=evaluation_set,
                initial_incumbents=(),
            )
            try:
                cache[key] = run_native_backtest(
                    inputs,
                    scenario="baseline" if scenario == "baseline" else "stressed",
                    targets=targets,
                    context=execution_context,
                    window_start=evaluation_dates[0],
                    window_end=evaluation_dates[-1],
                )
            except BacktestDataError:
                failed_candidates.add(key)
                raise
        return cache[key]

    def evaluator(
        context: EvaluationContext, parameters: ParameterSet, purpose: str
    ) -> SegmentEvaluation:
        native_parameters = _native_parameters(parameters)
        try:
            values = _returns(
                get_run(native_parameters, "baseline", context.evaluation_dates)
            )
        except BacktestDataError:
            return SegmentEvaluation(
                -1_000_000_000.0,
                (
                    tuple((day, 0.0) for day in context.evaluation_dates)
                    if purpose == "test"
                    else ()
                ),
            )
        observations = tuple((day, values[day]) for day in context.evaluation_dates)
        return SegmentEvaluation(
            _score(tuple(value for _day, value in observations)),
            observations if purpose == "test" else (),
        )

    walk_forward = run_walk_forward_selection(
        windows,
        candidates,
        axes,
        evaluator,
        relative_tolerance=float(inputs.config.values["validation"]["plateau_relative_tolerance"]),
        minimum_viable_neighbours=1,
        allow_unsupported_fallback=True,
    )
    owner_by_date: dict[date, int] = {}
    selected_by_fold = {
        fold.window.index: _native_parameters(fold.selection.selected.parameters)
        for fold in walk_forward.folds
    }
    _validate_selected_execution_costs(selected_by_fold, inputs)
    for fold in walk_forward.folds:
        for day in fold.window.test:
            owner_by_date.setdefault(day, fold.window.index)
    final_targets = _sequential_targets(inputs, context, owner_by_date, selected_by_fold)
    oos_dates = tuple(sorted(owner_by_date))
    baseline_run = run_native_backtest(
        inputs, scenario="baseline", targets=final_targets, context=execution_context,
        window_start=oos_dates[0], window_end=oos_dates[-1],
    )
    stressed_run = run_native_backtest(
        inputs, scenario="stressed", targets=final_targets, context=execution_context,
        window_start=oos_dates[0], window_end=oos_dates[-1],
    )
    baseline_by_date = _returns(baseline_run)
    stressed_by_date = _returns(stressed_run)
    if any(day not in baseline_by_date or day not in stressed_by_date for day in oos_dates):
        raise NativeWorkflowError("continuous native run is missing an OOS session")
    oos = tuple(baseline_by_date[day] for day in oos_dates)
    stressed = tuple(stressed_by_date[day] for day in oos_dates)
    rebuilt_folds: list[FoldEvaluation] = []
    for fold in walk_forward.folds:
        owned = tuple(day for day in fold.window.test if owner_by_date[day] == fold.window.index)
        rebuilt_folds.append(
            replace(
                fold,
                test=SegmentEvaluation(
                    _score(tuple(baseline_by_date[day] for day in owned)),
                    tuple((day, baseline_by_date[day]) for day in owned),
                ),
            )
        )
    walk_forward = WalkForwardEvaluation(
        tuple(rebuilt_folds), tuple(zip(oos_dates, oos, strict=True))
    )
    baseline_costs = CostModel(*inputs.config.transaction_costs)
    stressed_costs = CostModel(*inputs.config.stress_transaction_costs)
    audit = audit_bound_native_backtest_executions(
        inputs.identity,
        sessions=all_sessions,
        baseline_run=baseline_run,
        stressed_run=stressed_run,
        baseline_costs=baseline_costs,
        stressed_costs=stressed_costs,
    )
    if not audit.passed:
        finding_codes = ", ".join(sorted({row.code for row in audit.findings}))
        raise NativeWorkflowError(
            f"continuous native execution failed exact-set audit: {finding_codes}"
        )
    regimes = build_native_regimes(inputs, context=context)
    labels = tuple(str(regimes[day]) for day in oos_dates)
    trades = _realized_trades(baseline_run)
    configured_bootstrap = inputs.config.bootstrap_settings
    bootstrap = bootstrap_validation(
        oos,
        tuple(trade.return_value for trade in trades),
        labels,
        iterations=bootstrap_iterations or configured_bootstrap[0],
        block_length=min(bootstrap_block_length or configured_bootstrap[1], len(oos)),
        seed=bootstrap_seed if bootstrap_seed is not None else configured_bootstrap[2],
    )
    ablations: list[NativeAblationResult] = []
    for component in (*DETERMINISTIC_COMPONENTS, "full_deterministic"):
        try:
            run = run_native_backtest(
                inputs,
                scenario="baseline",
                targets=_sequential_targets(
                    inputs, context, owner_by_date, selected_by_fold,
                    disabled_component=(None if component == "full_deterministic" else component),
                ),
                context=execution_context,
                window_start=oos_dates[0],
                window_end=oos_dates[-1],
            )
        except BacktestDataError:
            if component == "full_deterministic":
                raise NativeWorkflowError(
                    "full deterministic OOS schedule is not executable"
                ) from None
            ablations.append(NativeAblationResult(component, None, None, None, False))
            continue
        values = _returns(run)
        series = tuple(values[day] for day in oos_dates)
        cagr, sharpe, drawdown = return_metrics(series)
        ablations.append(NativeAblationResult(component, cagr, sharpe, drawdown, True))

    cagr, sharpe, drawdown = return_metrics(oos)
    stressed_cagr, stressed_sharpe, _ = return_metrics(stressed)
    minimum_score = float(validation_section["minimum_economic_validation_score"])
    robustness = all(
        fold.selection.neighbouring_viable >= 1
        and fold.selection.selected.validation_score >= minimum_score
        and all(score >= minimum_score for score in fold.selection.neighbouring_viable_scores)
        for fold in walk_forward.folds
    )
    by_year: dict[int, float] = defaultdict(float)
    by_stock: dict[str, float] = defaultdict(float)
    for trade in trades:
        by_year[trade.closed_date.year] += trade.profit_loss
        by_stock[trade.symbol] += trade.profit_loss
    bootstrap_thresholds = inputs.config.bootstrap_gate_thresholds
    gates = assess_deployment_gates(
        DeploymentGateInputs(
            admissible_point_in_time_evidence=inputs.dataset_certified,
            out_of_sample_cagr=cagr,
            out_of_sample_sharpe=sharpe,
            out_of_sample_maximum_drawdown=drawdown,
            stressed_cagr=stressed_cagr,
            stressed_sharpe=stressed_sharpe,
            closed_trades=len(trades),
            realized_profit_loss_by_year=by_year,
            realized_profit_loss_by_stock=by_stock,
            nearby_parameters_economically_viable=robustness,
            bootstrap_cagr_q05=min(bootstrap.daily.cagr.q05, bootstrap.regime_blocks.cagr.q05),
            bootstrap_sharpe_q05=(
                min(bootstrap.daily.sharpe_ratio.q05, bootstrap.regime_blocks.sharpe_ratio.q05)
                if bootstrap.daily.sharpe_ratio and bootstrap.regime_blocks.sharpe_ratio
                else None
            ),
            bootstrap_maximum_drawdown_q95=max(
                bootstrap.daily.maximum_drawdown.q95,
                bootstrap.regime_blocks.maximum_drawdown.q95,
            ),
        ),
        minimum_bootstrap_cagr_q05=bootstrap_thresholds[0],
        minimum_bootstrap_sharpe_q05=bootstrap_thresholds[1],
        maximum_bootstrap_drawdown_q95=bootstrap_thresholds[2],
    )
    return NativeValidationWorkflow(
        inputs.identity.validation_run_id,
        windows,
        walk_forward,
        stressed,
        bootstrap,
        tuple(ablations),
        (audit,),
        baseline_run,
        stressed_run,
        trades,
        final_targets,
        gates,
        _ATTESTATION,
    )
