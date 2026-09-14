"""Performance, trade, and benchmark-relative metrics without third-party dependencies."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from statistics import fmean, median, stdev
from typing import cast

TRADING_DAYS = 252.0


@dataclass(frozen=True)
class TradeOutcome:
    return_value: float
    holding_days: int
    profit_loss: float | None = None


@dataclass(frozen=True)
class PerformanceMetrics:
    cagr: float | None
    annualized_volatility: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    maximum_drawdown: float | None
    calmar_ratio: float | None
    win_rate: float | None
    profit_factor: float | None
    turnover: float | None
    average_holding_period: float | None
    exposure: float | None
    number_of_trades: int
    average_trade_return: float | None
    median_trade_return: float | None
    best_trade: float | None
    worst_trade: float | None
    best_month: float | None
    worst_month: float | None
    best_year: float | None
    worst_year: float | None


@dataclass(frozen=True)
class BenchmarkMetrics:
    excess_cagr: float | None
    tracking_error: float | None
    information_ratio: float | None
    up_market_capture: float | None
    down_market_capture: float | None


def _returns(values: Sequence[float]) -> list[float]:
    return [current / previous - 1.0 for previous, current in zip(values, values[1:], strict=False)]


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) <= 1e-15:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _cagr(dates: Sequence[date], values: Sequence[float]) -> float | None:
    days = (dates[-1] - dates[0]).days
    if days <= 0 or values[0] <= 0.0 or values[-1] < 0.0:
        return None
    result = (values[-1] / values[0]) ** (365.2425 / days) - 1.0
    return cast(float, result)


def _period_returns(dates: Sequence[date], returns: Sequence[float], annual: bool) -> list[float]:
    grouped: dict[tuple[int, int] | int, list[float]] = defaultdict(list)
    for item_date, value in zip(dates[1:], returns, strict=True):
        key: tuple[int, int] | int = item_date.year if annual else (item_date.year, item_date.month)
        grouped[key].append(value)
    return [math.prod(1.0 + item for item in group) - 1.0 for group in grouped.values()]


def performance_metrics(
    dates: Sequence[date],
    equity_values: Sequence[float],
    *,
    trade_outcomes: Sequence[TradeOutcome] = (),
    traded_notional: float | None = None,
    exposures: Sequence[float] = (),
) -> PerformanceMetrics:
    """Calculate the required baseline metrics, returning ``None`` when undefined."""
    if len(dates) != len(equity_values) or not dates:
        raise ValueError("dates and equity_values must be non-empty and have equal length")
    if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
        raise ValueError("dates must be strictly increasing")
    if any(not math.isfinite(value) or value <= 0.0 for value in equity_values):
        raise ValueError("equity values must be finite and positive")
    if traded_notional is not None and (
        not math.isfinite(traded_notional) or traded_notional < 0.0
    ):
        raise ValueError("traded_notional must be finite and non-negative")
    if exposures and len(exposures) != len(equity_values):
        raise ValueError("exposures must be empty or match equity_values")
    if any(not math.isfinite(value) or value < 0.0 for value in exposures):
        raise ValueError("exposures must be finite and non-negative")

    daily = _returns(equity_values)
    average = fmean(daily) if daily else None
    daily_std = stdev(daily) if len(daily) >= 2 else None
    volatility = daily_std * math.sqrt(TRADING_DAYS) if daily_std is not None else None
    annualized_average = average * math.sqrt(TRADING_DAYS) if average is not None else None
    sharpe = _safe_ratio(annualized_average, daily_std)
    downside = [min(value, 0.0) for value in daily]
    downside_deviation = (
        math.sqrt(fmean(value * value for value in downside))
        if any(value < 0.0 for value in downside)
        else None
    )
    sortino = _safe_ratio(annualized_average, downside_deviation)

    peak = equity_values[0]
    maximum_drawdown = 0.0
    for value in equity_values:
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, 1.0 - value / peak)
    cagr = _cagr(dates, equity_values)
    calmar = _safe_ratio(cagr, maximum_drawdown)

    returns = [outcome.return_value for outcome in trade_outcomes]
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("trade returns must be finite")
    profit_losses = [
        outcome.return_value if outcome.profit_loss is None else outcome.profit_loss
        for outcome in trade_outcomes
    ]
    if any(not math.isfinite(value) for value in profit_losses):
        raise ValueError("trade profit/loss values must be finite")
    gains = sum(value for value in profit_losses if value > 0.0)
    losses = -sum(value for value in profit_losses if value < 0.0)
    months = _period_returns(dates, daily, annual=False)
    years = _period_returns(dates, daily, annual=True)
    average_equity = fmean(equity_values)

    return PerformanceMetrics(
        cagr=cagr,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        maximum_drawdown=maximum_drawdown,
        calmar_ratio=calmar,
        win_rate=sum(value > 0.0 for value in returns) / len(returns) if returns else None,
        profit_factor=_safe_ratio(gains, losses),
        turnover=(
            traded_notional / average_equity
            if traded_notional is not None and average_equity > 0.0
            else None
        ),
        average_holding_period=fmean(outcome.holding_days for outcome in trade_outcomes)
        if trade_outcomes
        else None,
        exposure=fmean(exposures) if exposures else None,
        number_of_trades=len(trade_outcomes),
        average_trade_return=fmean(returns) if returns else None,
        median_trade_return=median(returns) if returns else None,
        best_trade=max(returns) if returns else None,
        worst_trade=min(returns) if returns else None,
        best_month=max(months) if months else None,
        worst_month=min(months) if months else None,
        best_year=max(years) if years else None,
        worst_year=min(years) if years else None,
    )


def benchmark_relative_metrics(
    dates: Sequence[date], strategy_values: Sequence[float], benchmark_values: Sequence[float]
) -> BenchmarkMetrics:
    """Calculate benchmark-relative metrics over aligned daily equity levels."""
    if len(dates) != len(strategy_values) or len(dates) != len(benchmark_values) or not dates:
        raise ValueError("dates, strategy_values, and benchmark_values must align and be non-empty")
    if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
        raise ValueError("dates must be strictly increasing")
    all_values = (*strategy_values, *benchmark_values)
    if any(value <= 0.0 or not math.isfinite(value) for value in all_values):
        raise ValueError("strategy and benchmark values must be finite and positive")
    strategy_returns = _returns(strategy_values)
    benchmark_returns = _returns(benchmark_values)
    pairs = list(zip(strategy_returns, benchmark_returns, strict=True))
    active = [strategy - benchmark for strategy, benchmark in pairs]
    active_std = stdev(active) if len(active) >= 2 else None
    tracking_error = active_std * math.sqrt(TRADING_DAYS) if active_std is not None else None
    information_ratio = _safe_ratio(
        fmean(active) * math.sqrt(TRADING_DAYS) if active else None,
        active_std,
    )
    up_pairs = [(strategy, benchmark) for strategy, benchmark in pairs if benchmark > 0.0]
    down_pairs = [(strategy, benchmark) for strategy, benchmark in pairs if benchmark < 0.0]
    up_capture = _safe_ratio(
        fmean(pair[0] for pair in up_pairs) if up_pairs else None,
        fmean(pair[1] for pair in up_pairs) if up_pairs else None,
    )
    down_capture = _safe_ratio(
        fmean(pair[0] for pair in down_pairs) if down_pairs else None,
        fmean(pair[1] for pair in down_pairs) if down_pairs else None,
    )
    strategy_cagr = _cagr(dates, strategy_values)
    benchmark_cagr = _cagr(dates, benchmark_values)
    excess_cagr = (
        strategy_cagr - benchmark_cagr
        if strategy_cagr is not None and benchmark_cagr is not None
        else None
    )
    return BenchmarkMetrics(
        excess_cagr,
        tracking_error,
        information_ratio,
        up_capture,
        down_capture,
    )
