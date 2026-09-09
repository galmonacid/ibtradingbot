"""Deterministic cross-sectional momentum ranking."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from src.features.core import FeatureRow

MANDATORY_SCORE_FEATURES = (
    "ret_63_skip5",
    "ret_126_skip5",
    "ret_252_skip5",
    "trend_50d",
    "trend_100d",
    "trend_200d",
    "vol_20d",
    "drawdown_63d",
    "adjusted_close",
    "sma_200d",
)


@dataclass(frozen=True)
class RankingParameters:
    momentum_63_weight: float = 0.35
    momentum_126_weight: float = 0.35
    momentum_252_weight: float = 0.30
    momentum_total_weight: float = 0.65
    trend_weight: float = 0.30
    volatility_penalty: float = 0.20
    drawdown_penalty: float = 0.15
    winsor_lower: float = 0.01
    winsor_upper: float = 0.99

    def __post_init__(self) -> None:
        numeric = (
            self.momentum_63_weight,
            self.momentum_126_weight,
            self.momentum_252_weight,
            self.momentum_total_weight,
            self.trend_weight,
            self.volatility_penalty,
            self.drawdown_penalty,
            self.winsor_lower,
            self.winsor_upper,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("ranking parameters must be finite")
        if not math.isclose(
            self.momentum_63_weight
            + self.momentum_126_weight
            + self.momentum_252_weight,
            1.0,
        ):
            raise ValueError("momentum horizon weights must sum to one")
        if not 0.50 <= self.momentum_total_weight <= 0.80:
            raise ValueError("total momentum weight must be in [0.50, 0.80]")
        if not 0.15 <= self.trend_weight <= 0.40:
            raise ValueError("trend weight must be in [0.15, 0.40]")
        if not 0.10 <= self.volatility_penalty <= 0.30:
            raise ValueError("volatility penalty must be in [0.10, 0.30]")
        if not 0.05 <= self.drawdown_penalty <= 0.25:
            raise ValueError("drawdown penalty must be in [0.05, 0.25]")
        if not 0.0 <= self.winsor_lower <= self.winsor_upper <= 1.0:
            raise ValueError("winsor limits must satisfy 0 <= lower <= upper <= 1")


@dataclass(frozen=True)
class RankedStock:
    symbol: str
    rank: int
    score: float


@dataclass(frozen=True)
class RankingExclusion:
    symbol: str
    reason: str


@dataclass(frozen=True)
class RankingResult:
    date: date
    ranked: tuple[RankedStock, ...]
    exclusions: tuple[RankingExclusion, ...]


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _zscores(
    values: Mapping[str, float], lower_quantile: float, upper_quantile: float
) -> dict[str, float]:
    concrete = list(values.values())
    lower = _percentile(concrete, lower_quantile)
    upper = _percentile(concrete, upper_quantile)
    winsorized = {
        symbol: min(max(value, lower), upper) for symbol, value in values.items()
    }
    mean = math.fsum(winsorized.values()) / len(winsorized)
    variance = math.fsum((value - mean) ** 2 for value in winsorized.values()) / len(
        winsorized
    )
    standard_deviation = math.sqrt(variance)
    scale = max(1.0, *(abs(value) for value in winsorized.values()))
    if standard_deviation <= 1e-15 * scale:
        return dict.fromkeys(winsorized, 0.0)
    return {
        symbol: (value - mean) / standard_deviation
        for symbol, value in winsorized.items()
    }


def _required_value(row: FeatureRow, feature: str) -> float:
    value = row.values.get(feature)
    if value is None:  # Protected by the eligibility pass; keeps the invariant local.
        raise ValueError(f"missing required feature {feature} for {row.symbol}")
    return float(value)


def rank_features(
    rows: Iterable[FeatureRow],
    as_of_date: date | None = None,
    benchmark: str = "SPY",
    parameters: RankingParameters | None = None,
) -> RankingResult:
    """Rank the eligible cross-section on one close, breaking ties by symbol."""

    params = parameters or RankingParameters()
    supplied = tuple(rows)
    available_dates = [row.date for row in supplied if row.symbol != benchmark]
    if not available_dates:
        raise ValueError("no non-benchmark feature rows supplied")
    session = as_of_date or max(available_dates)
    session_rows = sorted(
        (row for row in supplied if row.date == session and row.symbol != benchmark),
        key=lambda row: row.symbol,
    )
    if not session_rows:
        raise ValueError(f"no non-benchmark feature rows for {session.isoformat()}")

    eligible: dict[str, FeatureRow] = {}
    exclusions: list[RankingExclusion] = []
    for row in session_rows:
        missing = [name for name in MANDATORY_SCORE_FEATURES if row.values.get(name) is None]
        if missing:
            exclusions.append(
                RankingExclusion(row.symbol, "missing:" + ",".join(missing))
            )
            continue
        non_finite = [
            name
            for name in MANDATORY_SCORE_FEATURES
            if not math.isfinite(_required_value(row, name))
        ]
        if non_finite:
            exclusions.append(
                RankingExclusion(row.symbol, "non_finite:" + ",".join(non_finite))
            )
            continue
        close = _required_value(row, "adjusted_close")
        sma200 = _required_value(row, "sma_200d")
        if close <= sma200:
            exclusions.append(RankingExclusion(row.symbol, "price_not_above_sma200"))
            continue
        eligible[row.symbol] = row

    if not eligible:
        return RankingResult(session, (), tuple(exclusions))

    transformed: dict[str, dict[str, float]] = {}
    for feature in MANDATORY_SCORE_FEATURES[:8]:
        raw: dict[str, float] = {}
        for symbol, row in eligible.items():
            value = _required_value(row, feature)
            if feature == "drawdown_63d":
                value = abs(min(value, 0.0))
            raw[symbol] = value
        transformed[feature] = _zscores(raw, params.winsor_lower, params.winsor_upper)

    scores: dict[str, float] = {}
    for symbol in eligible:
        momentum = (
            params.momentum_63_weight * transformed["ret_63_skip5"][symbol]
            + params.momentum_126_weight * transformed["ret_126_skip5"][symbol]
            + params.momentum_252_weight * transformed["ret_252_skip5"][symbol]
        )
        trend = math.fsum(
            transformed[feature][symbol]
            for feature in ("trend_50d", "trend_100d", "trend_200d")
        ) / 3.0
        scores[symbol] = (
            params.momentum_total_weight * momentum
            + params.trend_weight * trend
            - params.volatility_penalty * transformed["vol_20d"][symbol]
            - params.drawdown_penalty * transformed["drawdown_63d"][symbol]
        )

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ranked = tuple(
        RankedStock(symbol, rank, score)
        for rank, (symbol, score) in enumerate(ordered, start=1)
    )
    return RankingResult(session, ranked, tuple(exclusions))
