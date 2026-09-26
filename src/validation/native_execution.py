"""Attested native backtest runs bound to exact canonical inputs and targets."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from src.backtest.costs import CostModel
from src.backtest.engine import BacktestResult, run_backtest
from src.data.corporate_actions import DelistingEvent
from src.validation.native_inputs import NativeValidationInputs
from src.validation.native_strategy import NativeTargetSet


class NativeExecutionError(ValueError):
    """Raised when a native run cannot be tied to exact verified inputs."""


_NATIVE_RUN_ATTESTATION = object()
_NATIVE_MARKET_ATTESTATION = object()


@dataclass(frozen=True)
class _StableBar:
    date: date
    symbol: str
    open: float
    close: float
    adjusted_close: float
    adjusted_open: float


@dataclass(frozen=True)
class NativeBacktestRun:
    validation_run_id: str
    scenario: Literal["baseline", "stressed"]
    market_input_sha256: str
    target_sha256: str
    result: BacktestResult
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _NATIVE_RUN_ATTESTATION:
            raise NativeExecutionError("native runs must be issued by the native executor")


@dataclass(frozen=True)
class NativeMarketContext:
    validation_run_id: str
    bars: tuple[_StableBar, ...]
    bars_by_security: dict[str, tuple[_StableBar, ...]]
    delistings: tuple[DelistingEvent, ...]
    market_input_sha256: str
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _NATIVE_MARKET_ATTESTATION:
            raise NativeExecutionError("native market contexts must be issued by the executor")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_native_market_context(inputs: NativeValidationInputs) -> NativeMarketContext:
    """Materialize verified market rows once for repeated sensitivity executions."""
    context_start = inputs.certification_start or inputs.validation_start
    bars = tuple(
        _StableBar(
            row.date,
            row.security_id,
            row.open,
            row.close,
            row.adjusted_close,
            row.adjusted_open,
        )
        for row in inputs.canonical.bars
        if context_start is None or row.date >= context_start
    )
    delistings = tuple(
        DelistingEvent(row.action_date, row.security_id, row.value)
        for row in inputs.canonical.actions
        if row.action_type == "delisting"
        and (context_start is None or row.action_date >= context_start)
    )
    market_hash = _digest(
        {
            "canonical_manifest_sha256": inputs.canonical.manifest_sha256,
            "transformation_version": inputs.canonical.transformation_version,
        }
    )
    grouped: dict[str, list[_StableBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol, []).append(bar)
    return NativeMarketContext(
        inputs.identity.validation_run_id,
        bars,
        {security_id: tuple(rows) for security_id, rows in grouped.items()},
        delistings,
        market_hash,
        _NATIVE_MARKET_ATTESTATION,
    )


def run_native_backtest(
    inputs: NativeValidationInputs,
    *,
    scenario: Literal["baseline", "stressed"],
    targets: NativeTargetSet,
    initial_cash: float = 100_000.0,
    context: NativeMarketContext | None = None,
    window_start: date | None = None,
    window_end: date | None = None,
) -> NativeBacktestRun:
    """Execute targets only against rows retained by the verified canonical loader."""
    if targets.validation_run_id != inputs.identity.validation_run_id:
        raise NativeExecutionError("native target set belongs to a different validation run")
    market = context or build_native_market_context(inputs)
    if market._attestation is not _NATIVE_MARKET_ATTESTATION:
        raise NativeExecutionError("native market context is not attested")
    if market.validation_run_id != inputs.identity.validation_run_id:
        raise NativeExecutionError("native market context belongs to another validation run")
    if (window_start is None) != (window_end is None):
        raise NativeExecutionError("native execution window bounds must be supplied together")
    if window_start is not None and window_end is not None and window_end < window_start:
        raise NativeExecutionError("native execution window is reversed")
    stressed = CostModel(*inputs.config.stress_transaction_costs)
    if scenario == "baseline":
        commission, slippage, fx = inputs.config.transaction_costs
        costs = CostModel(
            commission * targets.parameters.commission_multiplier,
            targets.parameters.slippage_bps_each_side or slippage,
            fx,
        )
    else:
        costs = stressed
    portfolio = inputs.config.values["portfolio"]
    strategy = inputs.config.values["strategy"]
    risk = inputs.config.values["risk"]
    if not all(isinstance(value, dict) for value in (portfolio, strategy, risk)):
        raise NativeExecutionError("validated configuration sections are malformed")
    assert isinstance(portfolio, dict) and isinstance(strategy, dict) and isinstance(risk, dict)
    target_security_ids = {
        security_id
        for weights in targets.targets_by_signal_date.values()
        for security_id in weights
    } | {targets.benchmark_security_id}
    effective_start = window_start
    if window_start is not None:
        benchmark_dates = tuple(
            row.date
            for row in market.bars_by_security.get(targets.benchmark_security_id, ())
        )
        index = bisect_left(benchmark_dates, window_start)
        if index > 0:
            effective_start = benchmark_dates[index - 1]
    selected_bars = tuple(
        bar
        for security_id in sorted(target_security_ids)
        for bar in market.bars_by_security.get(security_id, ())
        if (effective_start is None or bar.date >= effective_start)
        and (window_end is None or bar.date <= window_end)
    )
    selected_delistings = tuple(
        row
        for row in market.delistings
        if row.symbol in target_security_ids
        and (effective_start is None or row.date >= effective_start)
        and (window_end is None or row.date <= window_end)
    )
    result = run_backtest(
        selected_bars,
        targets.targets_by_signal_date,
        initial_cash=initial_cash,
        costs=costs,
        delistings=selected_delistings,
        cash_buffer=float(portfolio["cash_buffer"]),
        max_position_weight=float(portfolio["max_position_weight"]),
        max_positions=int(strategy["max_positions"]),
        soft_drawdown_threshold=(
            1.0 - 1e-12
            if targets.parameters.disabled_component == "risk_controls"
            else float(risk["max_portfolio_drawdown_soft"])
        ),
        hard_drawdown_threshold=(
            1.0
            if targets.parameters.disabled_component == "risk_controls"
            else float(risk["max_portfolio_drawdown_hard"])
        ),
    )
    target_hash = _digest(
        [
            (day.isoformat(), sorted(weights.items()))
            for day, weights in sorted(targets.targets_by_signal_date.items())
        ]
    )
    if target_hash != targets.target_sha256:
        raise NativeExecutionError("native target set content does not match its attested hash")
    return NativeBacktestRun(
        inputs.identity.validation_run_id,
        scenario,
        (
            market.market_input_sha256
            if window_start is None
            else _digest(
                {
                    "market_input_sha256": market.market_input_sha256,
                    "window_start": window_start,
                    "window_end": window_end,
                }
            )
        ),
        target_hash,
        result,
        _NATIVE_RUN_ATTESTATION,
    )
