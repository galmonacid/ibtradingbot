"""Native, attested strategy targets derived only from verified canonical rows."""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from src.features import (
    FeatureRow,
    Regime,
    RegimeParameters,
    build_features,
    classify_regimes,
)
from src.portfolio import (
    PortfolioConstructionError,
    build_inverse_volatility_targets,
    estimate_annualized_covariance,
)
from src.strategy import (
    RankedStock,
    RankingParameters,
    rank_features,
    select_with_rank_hysteresis,
)
from src.validation.native_inputs import NativeValidationInputs


class NativeStrategyError(ValueError):
    """Raised when canonical inputs cannot produce safe native strategy targets."""


_TARGET_ATTESTATION = object()
_CONTEXT_ATTESTATION = object()


@dataclass(frozen=True)
class NativeStrategyParameters:
    """Small deterministic sensitivity/ablation surface owned by native validation."""

    target_positions: int | None = None
    skip_recent_days: int | None = None
    target_annual_volatility: float | None = None
    risk_on_breadth_threshold: float | None = None
    rebalance_frequency: str | None = None
    rebalance_day: str | None = None
    trend_window_scale: float | None = None
    momentum_63d_weight: float | None = None
    execution_delay_sessions: int = 1
    commission_multiplier: float = 1.0
    slippage_bps_each_side: float | None = None
    disabled_component: str | None = None
    diagnostic_change: str | None = None

    def __post_init__(self) -> None:
        if self.diagnostic_change not in {
            None,
            "monthly",
            "score",
            "equal_weight",
            "simple_regime",
            "dual_covariance",
        }:
            raise NativeStrategyError("unsupported V2 single-change diagnostic")
        if self.diagnostic_change is not None and self.disabled_component is not None:
            raise NativeStrategyError("single-change diagnostics cannot combine ablations")
        if self.target_positions is not None and self.target_positions < 1:
            raise NativeStrategyError("target_positions must be positive")
        if self.skip_recent_days is not None and self.skip_recent_days < 0:
            raise NativeStrategyError("skip_recent_days must be non-negative")
        if self.target_annual_volatility is not None and self.target_annual_volatility <= 0:
            raise NativeStrategyError("target volatility must be positive")
        if self.trend_window_scale is not None and self.trend_window_scale <= 0:
            raise NativeStrategyError("trend window scale must be positive")
        if self.momentum_63d_weight is not None and not 0 < self.momentum_63d_weight < 1:
            raise NativeStrategyError("63-day momentum weight must be in (0, 1)")
        if self.execution_delay_sessions not in {1, 2}:
            raise NativeStrategyError("execution delay must be one or two sessions")
        if self.commission_multiplier <= 0:
            raise NativeStrategyError("commission multiplier must be positive")
        if self.disabled_component not in {
            None,
            "momentum",
            "trend",
            "regime",
            "inverse_volatility",
            "risk_controls",
        }:
            raise NativeStrategyError("unsupported native ablation component")


@dataclass(frozen=True)
class NativeTargetSet:
    validation_run_id: str
    targets_by_signal_date: dict[date, dict[str, float]]
    target_sha256: str
    signal_dates: tuple[date, ...]
    benchmark_security_id: str
    parameters: NativeStrategyParameters
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _TARGET_ATTESTATION:
            raise NativeStrategyError("native target sets must be issued by the native strategy")


@dataclass(frozen=True)
class _StableFeatureBar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


@dataclass(frozen=True)
class NativeStrategyContext:
    """Run-bound canonical strategy state that is expensive to derive repeatedly."""

    validation_run_id: str
    benchmark_security_id: str
    bars: tuple[_StableFeatureBar, ...]
    sessions: tuple[date, ...]
    members_by_date: dict[date, set[str]]
    features: tuple[FeatureRow, ...]
    features_by_key: dict[tuple[date, str], FeatureRow]
    features_by_date: dict[date, tuple[FeatureRow, ...]]
    regimes: dict[date, Regime]
    prices: dict[tuple[date, str], float]
    raw_closes: dict[tuple[date, str], float]
    history_dates_by_security: dict[str, tuple[date, ...]]
    price_series_by_security: dict[str, tuple[float, ...]]
    session_indexes: dict[date, int]
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _CONTEXT_ATTESTATION:
            raise NativeStrategyError(
                "native strategy contexts must be issued by the native strategy"
            )


def _digest(targets: dict[date, dict[str, float]]) -> str:
    payload = [
        (day.isoformat(), sorted(weights.items())) for day, weights in sorted(targets.items())
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _validate_target_set(inputs: NativeValidationInputs, targets: NativeTargetSet) -> None:
    if targets._attestation is not _TARGET_ATTESTATION:
        raise NativeStrategyError("native target set is not attested")
    if targets.validation_run_id != inputs.identity.validation_run_id:
        raise NativeStrategyError("native target set belongs to a different validation run")
    if targets.signal_dates != tuple(targets.targets_by_signal_date):
        raise NativeStrategyError("native target signal-date index has been modified")
    if targets.target_sha256 != _digest(targets.targets_by_signal_date):
        raise NativeStrategyError("native target content does not match its attested hash")


def select_native_targets(
    inputs: NativeValidationInputs,
    targets: NativeTargetSet,
    signal_dates: Iterable[date],
) -> NativeTargetSet:
    """Issue an attested date subset of an existing, intact native target set."""
    _validate_target_set(inputs, targets)
    requested = set(signal_dates)
    unknown = requested.difference(targets.targets_by_signal_date)
    if unknown:
        raise NativeStrategyError("requested signal date is absent from native target set")
    selected = {
        day: dict(weights)
        for day, weights in targets.targets_by_signal_date.items()
        if day in requested
    }
    return NativeTargetSet(
        targets.validation_run_id,
        selected,
        _digest(selected),
        tuple(selected),
        targets.benchmark_security_id,
        targets.parameters,
        _TARGET_ATTESTATION,
    )


def compose_native_targets(
    inputs: NativeValidationInputs,
    selections: Sequence[tuple[NativeTargetSet, Iterable[date]]],
    *,
    parameters: NativeStrategyParameters | None = None,
) -> NativeTargetSet:
    """Compose non-overlapping date slices from intact, run-bound target sets."""
    composed: dict[date, dict[str, float]] = {}
    benchmark_id: str | None = None
    for targets, dates in selections:
        selected = select_native_targets(inputs, targets, dates)
        if benchmark_id is None:
            benchmark_id = selected.benchmark_security_id
        elif benchmark_id != selected.benchmark_security_id:
            raise NativeStrategyError("native target selections use different benchmarks")
        duplicate = set(composed).intersection(selected.targets_by_signal_date)
        if duplicate:
            raise NativeStrategyError("native target selections contain duplicate signal dates")
        composed.update(selected.targets_by_signal_date)
    if benchmark_id is None:
        context = build_native_strategy_context(inputs)
        benchmark_id = context.benchmark_security_id
    ordered = {day: composed[day] for day in sorted(composed)}
    return NativeTargetSet(
        inputs.identity.validation_run_id,
        ordered,
        _digest(ordered),
        tuple(ordered),
        benchmark_id,
        parameters or NativeStrategyParameters(),
        _TARGET_ATTESTATION,
    )


def _active_members(inputs: NativeValidationInputs, day: date) -> set[str]:
    return {
        row.security_id
        for row in inputs.canonical.memberships
        if row.effective_from <= day and (row.effective_to is None or day < row.effective_to)
    }


def _ranking_parameters(
    inputs: NativeValidationInputs, parameters: NativeStrategyParameters
) -> RankingParameters:
    momentum = inputs.config.momentum_weights
    if parameters.momentum_63d_weight is not None:
        remaining = 1.0 - parameters.momentum_63d_weight
        tail_total = momentum[1] + momentum[2]
        momentum = (
            parameters.momentum_63d_weight,
            remaining * momentum[1] / tail_total,
            remaining * momentum[2] / tail_total,
        )
    total, trend = inputs.config.ranking_weights
    volatility, drawdown = inputs.config.ranking_penalties
    return RankingParameters(
        momentum_63_weight=momentum[0],
        momentum_126_weight=momentum[1],
        momentum_252_weight=momentum[2],
        momentum_total_weight=total,
        trend_weight=trend,
        volatility_penalty=volatility,
        drawdown_penalty=drawdown,
        include_momentum=parameters.disabled_component != "momentum",
        include_trend=parameters.disabled_component != "trend",
    )


def _regime_parameters(
    inputs: NativeValidationInputs, parameters: NativeStrategyParameters | None = None
) -> RegimeParameters:
    risk_on, neutral, high_vol = inputs.config.regime_thresholds
    section = inputs.config.values["regime"]
    if not isinstance(section, dict):
        raise NativeStrategyError("validated regime configuration is malformed")
    if parameters is not None and parameters.risk_on_breadth_threshold is not None:
        risk_on = parameters.risk_on_breadth_threshold
    return RegimeParameters(risk_on, neutral, high_vol, int(section["volatility_lookback"]))


def _signal_dates(
    sessions: tuple[date, ...], *, rebalance_day: str, frequency: str
) -> tuple[date, ...]:
    weekday = {"Thursday": 3, "Friday": 4}.get(rebalance_day)
    if weekday is None or frequency not in {"weekly", "biweekly"}:
        raise NativeStrategyError("unsupported native rebalance schedule")
    by_week: dict[tuple[int, int], list[date]] = {}
    for session in sessions:
        iso = session.isocalendar()
        by_week.setdefault((iso.year, iso.week), []).append(session)
    selected = tuple(
        max((day for day in by_week[key] if day.weekday() <= weekday), default=max(by_week[key]))
        for key in sorted(by_week)
    )
    return selected if frequency == "weekly" else selected[::2]


def build_native_strategy_context(inputs: NativeValidationInputs) -> NativeStrategyContext:
    """Precompute canonical strategy state and bind it to the validation run."""
    benchmark_ids = {
        row.security_id for row in inputs.canonical.bars if row.symbol == inputs.config.benchmark
    }
    if len(benchmark_ids) != 1:
        raise NativeStrategyError("benchmark ticker must resolve to exactly one security ID")
    benchmark_id = benchmark_ids.pop()
    context_start = inputs.certification_start
    bars = tuple(
        _StableFeatureBar(
            row.date,
            row.security_id,
            row.open,
            row.high,
            row.low,
            row.close,
            row.adjusted_close,
            row.volume,
        )
        for row in inputs.canonical.bars
        if context_start is None or row.date >= context_start
    )
    sessions = tuple(sorted({row.date for row in bars if row.symbol == benchmark_id}))
    if not sessions:
        raise NativeStrategyError("benchmark has no canonical sessions")
    members_by_date = {day: _active_members(inputs, day) for day in sessions}
    features = build_features(
        bars,
        benchmark=benchmark_id,
        eligible_symbols_by_date=members_by_date,
    )
    regimes = {
        row.date: row.regime
        for row in classify_regimes(
            features, benchmark=benchmark_id, parameters=_regime_parameters(inputs)
        )
    }
    prices = {(row.date, row.security_id): row.adjusted_close for row in inputs.canonical.bars}
    benchmark_sessions = set(sessions)
    history_rows: dict[str, list[tuple[date, float]]] = {}
    for row in inputs.canonical.bars:
        if context_start is not None and row.date < context_start:
            continue
        if row.date in benchmark_sessions:
            history_rows.setdefault(row.security_id, []).append((row.date, row.adjusted_close))
    features_by_date: dict[date, list[FeatureRow]] = {}
    for feature_row in features:
        features_by_date.setdefault(feature_row.date, []).append(feature_row)
    return NativeStrategyContext(
        inputs.identity.validation_run_id,
        benchmark_id,
        bars,
        sessions,
        members_by_date,
        features,
        {(row.date, row.symbol): row for row in features},
        {day: tuple(rows) for day, rows in features_by_date.items()},
        regimes,
        prices,
        {
            (row.date, row.security_id): row.close
            for row in inputs.canonical.bars
            if context_start is None or row.date >= context_start
        },
        {
            security_id: tuple(day for day, _price in sorted(rows))
            for security_id, rows in history_rows.items()
        },
        {
            security_id: tuple(price for _day, price in sorted(rows))
            for security_id, rows in history_rows.items()
        },
        {day: index for index, day in enumerate(sessions)},
        _CONTEXT_ATTESTATION,
    )


def _validated_context(
    inputs: NativeValidationInputs, context: NativeStrategyContext | None
) -> NativeStrategyContext:
    if context is None:
        return build_native_strategy_context(inputs)
    if context._attestation is not _CONTEXT_ATTESTATION:
        raise NativeStrategyError("native strategy context is not attested")
    if context.validation_run_id != inputs.identity.validation_run_id:
        raise NativeStrategyError("native strategy context belongs to a different validation run")
    return context


def build_native_regimes(
    inputs: NativeValidationInputs,
    *,
    context: NativeStrategyContext | None = None,
) -> dict[date, Regime]:
    """Classify benchmark regimes causally from verified canonical rows."""
    return dict(_validated_context(inputs, context).regimes)


def _parameterized_feature_row(
    row: FeatureRow,
    context: NativeStrategyContext,
    parameters: NativeStrategyParameters,
) -> FeatureRow:
    if parameters.skip_recent_days is None and parameters.trend_window_scale is None:
        return row
    dates = context.history_dates_by_security.get(row.symbol, ())
    prices = context.price_series_by_security.get(row.symbol, ())
    index = bisect_right(dates, row.date) - 1
    values = dict(row.values)
    if parameters.skip_recent_days is not None:
        skip = parameters.skip_recent_days
        for lookback in (63, 126, 252):
            values[f"ret_{lookback}_skip5"] = (
                prices[index - skip] / prices[index - skip - lookback] - 1.0
                if index >= skip + lookback
                else None
            )
    if parameters.trend_window_scale is not None:
        for base_window in (50, 100, 200):
            window = max(2, round(base_window * parameters.trend_window_scale))
            average = (
                math.fsum(prices[index - window + 1 : index + 1]) / window
                if index + 1 >= window
                else None
            )
            values[f"trend_{base_window}d"] = (
                None if average is None else prices[index] / average - 1.0
            )
            if base_window == 200:
                values["sma_200d"] = average
    return FeatureRow(row.date, row.symbol, values)


def build_native_targets(
    inputs: NativeValidationInputs,
    parameters: NativeStrategyParameters | None = None,
    *,
    context: NativeStrategyContext | None = None,
    allowed_execution_dates: set[date] | None = None,
    initial_incumbents: tuple[str, ...] = (),
) -> NativeTargetSet:
    """Build causal targets using stable IDs and close-known point-in-time membership."""
    parameters = parameters or NativeStrategyParameters()
    strategy_context = _validated_context(inputs, context)
    benchmark_id = strategy_context.benchmark_security_id
    sessions = strategy_context.sessions
    member_by_date = strategy_context.members_by_date
    features = strategy_context.features
    feature_by_key = strategy_context.features_by_key
    regimes = (
        strategy_context.regimes
        if parameters.risk_on_breadth_threshold is None
        else {
            row.date: row.regime
            for row in classify_regimes(
                features,
                benchmark=benchmark_id,
                parameters=_regime_parameters(inputs, parameters),
            )
        }
    )
    prices = strategy_context.prices
    raw_closes = strategy_context.raw_closes
    config = inputs.config
    _stress_commission, stress_slippage_bps, stress_fx_bps = config.stress_transaction_costs
    execution_reserve = (stress_slippage_bps + stress_fx_bps) / 10_000.0
    research_cash_buffer = config.cash_buffer + execution_reserve
    if research_cash_buffer >= 1.0:
        raise NativeStrategyError("configured cash and execution reserves consume all capital")
    strategy = config.values["strategy"]
    if not isinstance(strategy, dict):
        raise NativeStrategyError("validated strategy configuration is malformed")
    configured_positions = int(strategy["target_positions"])
    target_positions = parameters.target_positions or configured_positions
    if target_positions > int(strategy["max_positions"]):
        raise NativeStrategyError("target_positions exceeds configured maximum")
    targets: dict[date, dict[str, float]] = {}
    incumbents = initial_incumbents
    session_index = strategy_context.session_indexes
    signal_dates = _signal_dates(
        sessions,
        rebalance_day=parameters.rebalance_day or str(strategy["rebalance_day"]),
        frequency=parameters.rebalance_frequency or str(strategy["rebalance_frequency"]),
    )
    if parameters.diagnostic_change == "monthly":
        signal_dates = tuple(
            left
            for left, right in zip(sessions, sessions[1:], strict=False)
            if (left.year, left.month) != (right.year, right.month)
        )
    for signal_date in signal_dates:
        target_date = signal_date
        if parameters.execution_delay_sessions > 1:
            delayed_index = session_index[signal_date] + parameters.execution_delay_sessions - 1
            if delayed_index >= len(sessions):
                continue
            target_date = sessions[delayed_index]
        execution_index = session_index[target_date] + 1
        if execution_index >= len(sessions):
            continue
        if (
            allowed_execution_dates is not None
            and sessions[execution_index] not in allowed_execution_dates
        ):
            continue
        active = member_by_date[signal_date]
        candidates: list[tuple[str, float]] = []
        for security_id in active:
            if security_id == benchmark_id:
                continue
            row = feature_by_key.get((signal_date, security_id))
            if row is None:
                continue
            close = raw_closes.get((signal_date, security_id))
            liquidity = row.values.get("median_dollar_volume_20d")
            history = bisect_right(
                strategy_context.history_dates_by_security.get(security_id, ()), signal_date
            )
            if (
                close is not None
                and liquidity is not None
                and float(close) >= config.minimum_price_usd
                and float(liquidity) >= config.minimum_median_dollar_volume_20d
                and history >= config.minimum_history_sessions
            ):
                candidates.append((security_id, float(liquidity)))
        allowed = {
            security_id
            for security_id, _liquidity in sorted(candidates, key=lambda item: (-item[1], item[0]))[
                : config.universe_max_symbols
            ]
        }
        rows = tuple(
            _parameterized_feature_row(row, strategy_context, parameters)
            for row in strategy_context.features_by_date.get(signal_date, ())
            if row.symbol in allowed or row.symbol == benchmark_id
        )
        ranked: tuple[RankedStock, ...] = ()
        exclusions: dict[str, str] = {}
        if allowed:
            ranking = rank_features(
                rows,
                as_of_date=signal_date,
                benchmark=benchmark_id,
                parameters=_ranking_parameters(inputs, parameters),
            )
            ranked = ranking.ranked
            exclusions = {item.symbol: item.reason for item in ranking.exclusions}
        if parameters.diagnostic_change == "score":
            from src.validation.v2_diagnostics import diagnostic_momentum_rank

            ranked, exclusions = diagnostic_momentum_rank(strategy_context, signal_date, allowed)
        selection = select_with_rank_hysteresis(
            ranked,
            incumbents,
            target_positions,
            mandatory_exclusions=exclusions,
        )
        selected = [item.symbol for item in selection.selected]
        regime = regimes.get(signal_date, Regime.NEUTRAL)
        ceiling = config.regime_exposure_limits[str(regime)]
        if parameters.diagnostic_change == "simple_regime":
            from src.validation.v2_diagnostics import diagnostic_spy_ceiling

            ceiling = diagnostic_spy_ceiling(strategy_context, signal_date, research_cash_buffer)
        if parameters.disabled_component == "regime":
            ceiling = 1.0 - research_cash_buffer
        target: dict[str, float] = {}
        if selected and ceiling > 0.0:
            start = session_index[signal_date] - 20
            if start >= 0:
                window = sessions[start : session_index[signal_date] + 1]
                histories = {
                    symbol: [prices.get((day, symbol)) for day in window] for symbol in selected
                }
                usable = {
                    symbol: [float(value) for value in values if value is not None]
                    for symbol, values in histories.items()
                    if all(value is not None for value in values)
                }
                volatilities: dict[str, float] = {}
                for symbol in usable:
                    volatility = feature_by_key[(signal_date, symbol)].values["vol_20d"]
                    if volatility is not None:
                        volatilities[symbol] = float(volatility)
                if usable:
                    try:
                        covariance = estimate_annualized_covariance(usable)
                        target = build_inverse_volatility_targets(
                            selected,
                            (
                                {symbol: 1.0 for symbol in volatilities}
                                if parameters.disabled_component == "inverse_volatility"
                                or parameters.diagnostic_change == "equal_weight"
                                else volatilities
                            ),
                            covariance,
                            target_positions=target_positions,
                            regime_ceiling=ceiling,
                            target_annual_volatility=(
                                parameters.target_annual_volatility
                                or config.target_annual_volatility
                            ),
                            cash_buffer=research_cash_buffer,
                            min_position_weight=config.min_position_weight,
                            max_position_weight=config.max_position_weight,
                            max_positions=int(strategy["max_positions"]),
                        ).weights
                        if parameters.diagnostic_change == "dual_covariance":
                            from src.validation.v2_diagnostics import diagnostic_dual_scale

                            target = diagnostic_dual_scale(
                                strategy_context,
                                signal_date,
                                target,
                                parameters.target_annual_volatility
                                or config.target_annual_volatility,
                            )
                    except PortfolioConstructionError:
                        target = {}
        incumbents = tuple(target)
        if any(symbol not in active for symbol in target):
            raise NativeStrategyError("target contains a security outside point-in-time membership")
        if not math.isclose(sum(target.values()), min(sum(target.values()), 1.0), abs_tol=1e-12):
            raise NativeStrategyError("target gross exposure exceeds 100%")
        targets[target_date] = target
    return NativeTargetSet(
        inputs.identity.validation_run_id,
        targets,
        _digest(targets),
        tuple(targets),
        benchmark_id,
        parameters,
        _TARGET_ATTESTATION,
    )
