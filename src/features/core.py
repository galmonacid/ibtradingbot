"""Causal, deterministic price-derived research features."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class BarLike(Protocol):
    """Structural interface accepted from the data-ingestion layer."""

    @property
    def date(self) -> date: ...

    @property
    def symbol(self) -> str: ...

    @property
    def open(self) -> float: ...

    @property
    def high(self) -> float: ...

    @property
    def low(self) -> float: ...

    @property
    def close(self) -> float: ...

    @property
    def adjusted_close(self) -> float: ...

    @property
    def volume(self) -> int: ...


FeatureValue = float | None


@dataclass(frozen=True)
class FeatureRow:
    """All information available for one symbol after the stated session close."""

    date: date
    symbol: str
    values: Mapping[str, FeatureValue]


STOCK_FEATURE_NAMES = (
    "ret_1d",
    "ret_5d",
    "ret_21d",
    "ret_63d",
    "ret_126d",
    "ret_252d",
    "ret_63_skip5",
    "ret_126_skip5",
    "ret_252_skip5",
    "relative_ret_63d",
    "relative_ret_126d",
    "relative_ret_252d",
    "trend_20d",
    "trend_50d",
    "trend_100d",
    "trend_200d",
    "sma50_over_sma200_minus_1",
    "vol_10d",
    "vol_20d",
    "vol_63d",
    "drawdown_21d",
    "drawdown_63d",
    "drawdown_252d",
    "median_dollar_volume_20d",
    "relative_volume_20d",
    "turnover_proxy",
    "overnight_gap",
    "true_range",
    "atr14_over_close",
)

MARKET_FEATURE_NAMES = (
    "spy_ret_5d",
    "spy_ret_21d",
    "spy_ret_63d",
    "spy_trend_50d",
    "spy_trend_200d",
    "spy_vol_20d",
    "spy_drawdown_63d",
    "spy_drawdown_252d",
    "breadth_above_sma50",
    "breadth_above_sma200",
    "breadth_positive_63d",
    "breadth_positive_126d",
    "dispersion_21d",
    "dispersion_63d",
)


@dataclass(frozen=True)
class _Bar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"bar date must be a date or ISO date string, got {type(value).__name__}")


def _normalize(bar: BarLike) -> _Bar:
    return _Bar(
        date=_as_date(bar.date),
        symbol=str(bar.symbol).strip(),
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        adjusted_close=float(bar.adjusted_close),
        volume=int(bar.volume),
    )


def _return(prices: list[float], index: int, periods: int) -> FeatureValue:
    if index < periods:
        return None
    return prices[index] / prices[index - periods] - 1.0


def _skip_return(prices: list[float], index: int, lookback: int, skip: int = 5) -> FeatureValue:
    if index < lookback + skip:
        return None
    return prices[index - skip] / prices[index - skip - lookback] - 1.0


def _mean(values: list[float], index: int, window: int) -> FeatureValue:
    if index + 1 < window:
        return None
    return math.fsum(values[index - window + 1 : index + 1]) / window


def _volatility(returns: list[FeatureValue], index: int, window: int) -> FeatureValue:
    if index < window:
        return None
    sample = returns[index - window + 1 : index + 1]
    if any(value is None for value in sample):
        return None
    concrete = [float(value) for value in sample if value is not None]
    return statistics.stdev(concrete) * math.sqrt(252.0)


def _drawdown(prices: list[float], index: int, window: int) -> FeatureValue:
    if index + 1 < window:
        return None
    peak = max(prices[index - window + 1 : index + 1])
    return prices[index] / peak - 1.0


def _population_std(values: list[float]) -> FeatureValue:
    if not values:
        return None
    return statistics.pstdev(values)


def _individual_features(series: list[_Bar]) -> list[dict[str, FeatureValue]]:
    adjusted = [bar.adjusted_close for bar in series]
    raw_dollar_volume = [bar.close * bar.volume for bar in series]
    volumes = [float(bar.volume) for bar in series]
    daily_returns = [_return(adjusted, index, 1) for index in range(len(series))]
    true_ranges: list[float] = []
    output: list[dict[str, FeatureValue]] = []

    for index, bar in enumerate(series):
        # Apply the close adjustment factor to the whole OHLC bar. This keeps
        # price-derived research features continuous through ordinary splits.
        factor = bar.adjusted_close / bar.close
        adjusted_open = bar.open * factor
        adjusted_high = bar.high * factor
        adjusted_low = bar.low * factor
        previous_close = adjusted[index - 1] if index else None
        true_range = adjusted_high - adjusted_low
        if previous_close is not None:
            true_range = max(
                true_range,
                abs(adjusted_high - previous_close),
                abs(adjusted_low - previous_close),
            )
        true_ranges.append(true_range)

        values: dict[str, FeatureValue] = {}
        for periods in (1, 5, 21, 63, 126, 252):
            values[f"ret_{periods}d"] = _return(adjusted, index, periods)
        for periods in (63, 126, 252):
            values[f"ret_{periods}_skip5"] = _skip_return(adjusted, index, periods)

        moving_averages = {window: _mean(adjusted, index, window) for window in (20, 50, 100, 200)}
        for window, average in moving_averages.items():
            values[f"trend_{window}d"] = (
                None if average is None else bar.adjusted_close / average - 1.0
            )
        sma50, sma200 = moving_averages[50], moving_averages[200]
        values["sma50_over_sma200_minus_1"] = (
            None if sma50 is None or sma200 is None else sma50 / sma200 - 1.0
        )
        for window in (10, 20, 63):
            values[f"vol_{window}d"] = _volatility(daily_returns, index, window)
        for window in (21, 63, 252):
            values[f"drawdown_{window}d"] = _drawdown(adjusted, index, window)

        median_dollar_volume = (
            None if index + 1 < 20 else statistics.median(raw_dollar_volume[index - 19 : index + 1])
        )
        median_volume = (
            None if index + 1 < 20 else statistics.median(volumes[index - 19 : index + 1])
        )
        values["median_dollar_volume_20d"] = median_dollar_volume
        values["relative_volume_20d"] = (
            None if median_volume in (None, 0.0) else bar.volume / median_volume
        )
        # Shares outstanding are not present in OHLCV data, so raw dollar
        # volume is the reproducible turnover proxy available at this layer.
        values["turnover_proxy"] = raw_dollar_volume[index]
        values["overnight_gap"] = (
            None if previous_close is None else adjusted_open / previous_close - 1.0
        )
        values["true_range"] = true_range
        atr14 = _mean(true_ranges, index, 14)
        values["atr14_over_close"] = None if atr14 is None else atr14 / bar.adjusted_close
        # Internal values make the exact trend eligibility rule inspectable.
        values["adjusted_close"] = bar.adjusted_close
        values["sma_200d"] = moving_averages[200]
        output.append(values)
    return output


def build_features(
    bars: Iterable[BarLike],
    benchmark: str = "SPY",
    eligible_symbols_by_date: Mapping[date, Collection[str]] | None = None,
) -> tuple[FeatureRow, ...]:
    """Build causal features, sorted by date and symbol.

    Every calculation is trailing or contemporaneous. Adding later bars cannot
    change an already-produced row.
    """

    grouped: dict[str, list[_Bar]] = defaultdict(list)
    seen: set[tuple[date, str]] = set()
    for supplied in bars:
        bar = _normalize(supplied)
        key = (bar.date, bar.symbol)
        if key in seen:
            raise ValueError(f"duplicate bar for {bar.symbol} on {bar.date.isoformat()}")
        seen.add(key)
        grouped[bar.symbol].append(bar)
    for series in grouped.values():
        series.sort(key=lambda item: item.date)

    by_key: dict[tuple[date, str], dict[str, FeatureValue]] = {}
    by_date: dict[date, list[tuple[str, dict[str, FeatureValue]]]] = defaultdict(list)
    for symbol, series in grouped.items():
        for bar, values in zip(series, _individual_features(series), strict=True):
            by_key[(bar.date, symbol)] = values
            by_date[bar.date].append((symbol, values))

    benchmark_values = {key[0]: values for key, values in by_key.items() if key[1] == benchmark}
    for session in sorted(by_date):
        eligible_symbols = (
            None
            if eligible_symbols_by_date is None
            else set(eligible_symbols_by_date.get(session, ()))
        )
        stock_values = [
            values
            for symbol, values in by_date[session]
            if symbol != benchmark and (eligible_symbols is None or symbol in eligible_symbols)
        ]
        market: dict[str, FeatureValue] = {}
        spy = benchmark_values.get(session)
        for periods in (5, 21, 63):
            market[f"spy_ret_{periods}d"] = None if spy is None else spy[f"ret_{periods}d"]
        for window in (50, 200):
            market[f"spy_trend_{window}d"] = None if spy is None else spy[f"trend_{window}d"]
        market["spy_vol_20d"] = None if spy is None else spy["vol_20d"]
        for window in (63, 252):
            market[f"spy_drawdown_{window}d"] = None if spy is None else spy[f"drawdown_{window}d"]

        for window in (50, 200):
            trends = [values[f"trend_{window}d"] for values in stock_values]
            known = [float(value) for value in trends if value is not None]
            market[f"breadth_above_sma{window}"] = (
                None if not known else sum(value > 0.0 for value in known) / len(known)
            )
        for periods in (63, 126):
            returns = [values[f"ret_{periods}d"] for values in stock_values]
            known = [float(value) for value in returns if value is not None]
            market[f"breadth_positive_{periods}d"] = (
                None if not known else sum(value > 0.0 for value in known) / len(known)
            )
        for periods in (21, 63):
            returns = [values[f"ret_{periods}d"] for values in stock_values]
            known = [float(value) for value in returns if value is not None]
            market[f"dispersion_{periods}d"] = _population_std(known)

        for _symbol, values in by_date[session]:
            for periods in (63, 126, 252):
                stock_return = values[f"ret_{periods}d"]
                spy_return = None if spy is None else spy[f"ret_{periods}d"]
                values[f"relative_ret_{periods}d"] = (
                    None
                    if stock_return is None or spy_return is None
                    else float(stock_return) - float(spy_return)
                )
            values.update(market)

    return tuple(
        FeatureRow(session, symbol, by_key[(session, symbol)]) for session, symbol in sorted(by_key)
    )
