"""Causal market-regime classification."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from src.features.core import FeatureRow


class Regime(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


@dataclass(frozen=True)
class RegimeParameters:
    risk_on_breadth: float = 0.60
    neutral_breadth: float = 0.45
    high_vol_percentile: float = 0.80
    min_vol_history: int = 20

    def __post_init__(self) -> None:
        numeric = (
            self.risk_on_breadth,
            self.neutral_breadth,
            self.high_vol_percentile,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("regime thresholds must be finite")
        if not 0.0 <= self.neutral_breadth <= self.risk_on_breadth <= 1.0:
            raise ValueError("breadth thresholds must satisfy 0 <= neutral <= risk-on <= 1")
        if not 0.0 <= self.high_vol_percentile <= 1.0:
            raise ValueError("high-volatility percentile must be in [0, 1]")
        if self.min_vol_history < 1:
            raise ValueError("minimum volatility history must be positive")


@dataclass(frozen=True)
class RegimeRow:
    date: date
    regime: Regime
    spy_above_sma200: bool | None
    breadth: float | None
    spy_vol20: float | None
    prior_vol_percentile: float | None


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def classify_regimes(
    rows: Iterable[FeatureRow],
    benchmark: str = "SPY",
    parameters: RegimeParameters | None = None,
) -> tuple[RegimeRow, ...]:
    """Classify each benchmark session using only earlier volatility history."""

    params = parameters or RegimeParameters()
    benchmark_rows = sorted(
        (row for row in rows if row.symbol == benchmark), key=lambda row: row.date
    )
    prior_volatility: list[float] = []
    output: list[RegimeRow] = []
    for row in benchmark_rows:
        trend_value = row.values.get("spy_trend_200d")
        breadth_value = row.values.get("breadth_above_sma200")
        volatility_value = row.values.get("spy_vol_20d")
        trend_number = None if trend_value is None else float(trend_value)
        breadth_number = None if breadth_value is None else float(breadth_value)
        volatility_number = None if volatility_value is None else float(volatility_value)
        trend = (
            None if trend_number is None or not math.isfinite(trend_number) else trend_number > 0.0
        )
        breadth = (
            None if breadth_number is None or not math.isfinite(breadth_number) else breadth_number
        )
        volatility = (
            None
            if volatility_number is None or not math.isfinite(volatility_number)
            else volatility_number
        )
        threshold = (
            _percentile(prior_volatility, params.high_vol_percentile)
            if len(prior_volatility) >= params.min_vol_history
            else None
        )

        regime = Regime.NEUTRAL
        complete = None not in (trend, breadth, volatility, threshold)
        if complete:
            assert trend is not None
            assert breadth is not None
            assert volatility is not None
            assert threshold is not None
            if (
                trend
                and breadth >= params.risk_on_breadth
                and volatility < threshold
                and not math.isclose(
                    volatility,
                    threshold,
                    rel_tol=1e-15,
                    abs_tol=1e-15,
                )
            ):
                regime = Regime.RISK_ON
            elif not trend and breadth < params.neutral_breadth:
                regime = Regime.RISK_OFF

        output.append(RegimeRow(row.date, regime, trend, breadth, volatility, threshold))
        if volatility is not None and math.isfinite(volatility):
            prior_volatility.append(volatility)
    return tuple(output)
