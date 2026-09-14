"""Deterministic block-bootstrap validation without third-party dependencies."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean, stdev

TRADING_DAYS = 252
MIN_ADMISSIBLE_ITERATIONS = 2_000


@dataclass(frozen=True)
class MetricDistribution:
    """Bootstrap observations and deterministic 5/50/95 percent quantiles."""

    samples: tuple[float, ...]
    q05: float
    q50: float
    q95: float


@dataclass(frozen=True)
class ReturnMetricDistributions:
    """Distributions calculated from resampled daily returns."""

    cagr: MetricDistribution
    maximum_drawdown: MetricDistribution
    sharpe_ratio: MetricDistribution | None
    one_year_return: MetricDistribution | None
    three_year_return: MetricDistribution | None


@dataclass(frozen=True)
class BootstrapAnalysis:
    """Daily, trade-level, and regime-block bootstrap evidence."""

    iterations: int
    seed: int
    block_length: int
    daily: ReturnMetricDistributions
    mean_trade_return: MetricDistribution | None
    regime_blocks: ReturnMetricDistributions


def _validate_iterations(iterations: int) -> None:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < MIN_ADMISSIBLE_ITERATIONS:
        raise ValueError(
            f"iterations must be at least {MIN_ADMISSIBLE_ITERATIONS} for admissible analysis"
        )


def _validate_returns(values: Sequence[float], name: str) -> tuple[float, ...]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    normalized = tuple(float(value) for value in values)
    if any(not math.isfinite(value) or value <= -1.0 for value in normalized):
        raise ValueError(f"{name} must contain finite simple returns greater than -1")
    return normalized


def _validate_block_length(block_length: int, sample_size: int) -> None:
    if isinstance(block_length, bool) or not isinstance(block_length, int):
        raise TypeError("block_length must be an integer")
    if not 1 <= block_length <= sample_size:
        raise ValueError("block_length must be between 1 and the sample size")


def circular_block_samples(
    values: Sequence[float],
    *,
    block_length: int,
    iterations: int = MIN_ADMISSIBLE_ITERATIONS,
    seed: int = 0,
) -> tuple[tuple[float, ...], ...]:
    """Resample fixed-length circular moving blocks to the original sample size."""
    source = _validate_returns(values, "values")
    _validate_block_length(block_length, len(source))
    _validate_iterations(iterations)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    generator = random.Random(seed)
    samples: list[tuple[float, ...]] = []
    for _ in range(iterations):
        result: list[float] = []
        while len(result) < len(source):
            start = generator.randrange(len(source))
            result.extend(source[(start + offset) % len(source)] for offset in range(block_length))
        samples.append(tuple(result[: len(source)]))
    return tuple(samples)


def _regime_runs[Label: str](
    returns: tuple[float, ...], regimes: Sequence[Label]
) -> tuple[tuple[tuple[float, Label], ...], ...]:
    if len(regimes) != len(returns):
        raise ValueError("regimes must align one-to-one with daily returns")
    if any(not isinstance(label, str) or not label for label in regimes):
        raise ValueError("regime labels must be non-empty strings")
    runs: list[list[tuple[float, Label]]] = []
    for value, label in zip(returns, regimes, strict=True):
        if not runs or runs[-1][-1][1] != label:
            runs.append([])
        runs[-1].append((value, label))
    if len(set(regimes)) < 2 or len(runs) < 2:
        raise ValueError("regime bootstrap requires at least two distinct regimes and episodes")
    return tuple(tuple(run) for run in runs)


def regime_block_samples[Label: str](
    daily_returns: Sequence[float],
    regimes: Sequence[Label],
    *,
    iterations: int = MIN_ADMISSIBLE_ITERATIONS,
    seed: int = 0,
) -> tuple[tuple[tuple[float, Label], ...], ...]:
    """Resample complete contiguous regime runs into variable-length paths.

    Each path reaches at least the observed length.  Keeping the final episode whole
    avoids manufacturing an unobserved partial regime; downstream annualization uses
    the actual resampled path length.
    """
    returns = _validate_returns(daily_returns, "daily_returns")
    runs = _regime_runs(returns, regimes)
    _validate_iterations(iterations)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    generator = random.Random(seed)
    samples: list[tuple[tuple[float, Label], ...]] = []
    for _ in range(iterations):
        result: list[tuple[float, Label]] = []
        while len(result) < len(returns):
            result.extend(runs[generator.randrange(len(runs))])
        samples.append(tuple(result))
    return tuple(samples)


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _distribution(values: Sequence[float]) -> MetricDistribution:
    if not values:
        raise ValueError("a metric distribution cannot be empty")
    samples = tuple(values)
    ordered = sorted(samples)
    return MetricDistribution(
        samples=samples,
        q05=_quantile(ordered, 0.05),
        q50=_quantile(ordered, 0.50),
        q95=_quantile(ordered, 0.95),
    )


def _compound(returns: Sequence[float]) -> float:
    return math.prod(1.0 + value for value in returns) - 1.0


def _maximum_drawdown(returns: Sequence[float]) -> float:
    wealth = 1.0
    peak = 1.0
    maximum = 0.0
    for value in returns:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        maximum = max(maximum, 1.0 - wealth / peak)
    return maximum


def _sharpe(returns: Sequence[float], periods_per_year: float) -> float | None:
    if len(returns) < 2:
        return None
    deviation = stdev(returns)
    if deviation <= 1e-15:
        return None
    return fmean(returns) / deviation * math.sqrt(periods_per_year)


def _metric_distributions(
    samples: Sequence[Sequence[float]], observed_sample_size: int, periods_per_year: float
) -> ReturnMetricDistributions:
    if not math.isfinite(periods_per_year) or periods_per_year <= 0.0:
        raise ValueError("periods_per_year must be finite and positive")
    cagrs = [
        (1.0 + _compound(sample)) ** (periods_per_year / len(sample)) - 1.0
        for sample in samples
    ]
    drawdowns = [_maximum_drawdown(sample) for sample in samples]
    sharpes = [_sharpe(sample, periods_per_year) for sample in samples]
    defined_sharpes = [value for value in sharpes if value is not None]
    one_year_periods = max(1, round(periods_per_year))
    three_year_periods = 3 * one_year_periods
    one_year = (
        _distribution([_compound(sample[:one_year_periods]) for sample in samples])
        if observed_sample_size >= one_year_periods
        else None
    )
    three_year = (
        _distribution([_compound(sample[:three_year_periods]) for sample in samples])
        if observed_sample_size >= three_year_periods
        else None
    )
    return ReturnMetricDistributions(
        cagr=_distribution(cagrs),
        maximum_drawdown=_distribution(drawdowns),
        sharpe_ratio=_distribution(defined_sharpes) if defined_sharpes else None,
        one_year_return=one_year,
        three_year_return=three_year,
    )


def bootstrap_validation(
    daily_returns: Sequence[float],
    trade_returns: Sequence[float],
    regimes: Sequence[str],
    *,
    iterations: int = MIN_ADMISSIBLE_ITERATIONS,
    block_length: int = 20,
    seed: int = 0,
) -> BootstrapAnalysis:
    """Build deterministic daily, trade, and regime-aware bootstrap evidence."""
    daily = _validate_returns(daily_returns, "daily_returns")
    _validate_iterations(iterations)
    _validate_block_length(block_length, len(daily))
    trades = tuple(trade_returns)
    if trades:
        validated_trades = _validate_returns(trades, "trade_returns")
    else:
        validated_trades = ()

    daily_samples = circular_block_samples(
        daily, block_length=block_length, iterations=iterations, seed=seed
    )
    labelled_samples = regime_block_samples(daily, regimes, iterations=iterations, seed=seed + 1)
    regime_returns = tuple(tuple(value for value, _label in sample) for sample in labelled_samples)
    mean_trade_return: MetricDistribution | None = None
    if validated_trades:
        trade_samples = circular_block_samples(
            validated_trades,
            block_length=min(block_length, len(validated_trades)),
            iterations=iterations,
            seed=seed + 2,
        )
        trade_means = [fmean(sample) for sample in trade_samples]
        mean_trade_return = _distribution(trade_means)
    return BootstrapAnalysis(
        iterations=iterations,
        seed=seed,
        block_length=block_length,
        daily=_metric_distributions(daily_samples, len(daily), TRADING_DAYS),
        mean_trade_return=mean_trade_return,
        regime_blocks=_metric_distributions(regime_returns, len(daily), TRADING_DAYS),
    )
