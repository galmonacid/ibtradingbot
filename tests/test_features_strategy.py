from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from src.features import (
    MARKET_FEATURE_NAMES,
    STOCK_FEATURE_NAMES,
    FeatureRow,
    Regime,
    RegimeParameters,
    build_features,
    classify_regimes,
)
from src.strategy import rank_features


@dataclass(frozen=True)
class Bar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


def _series(symbol: str, multiplier: float, count: int = 270) -> list[Bar]:
    start = date(2023, 1, 1)
    bars = []
    for index in range(count):
        adjusted = 100.0 * multiplier ** index
        bars.append(
            Bar(
                start + timedelta(days=index),
                symbol,
                adjusted * 0.995,
                adjusted * 1.01,
                adjusted * 0.99,
                adjusted,
                adjusted,
                1_000_000 + index,
            )
        )
    return bars


def _latest(rows: tuple[FeatureRow, ...], symbol: str) -> FeatureRow:
    return max((row for row in rows if row.symbol == symbol), key=lambda row: row.date)


def test_required_features_have_exact_trailing_values() -> None:
    bars = _series("AAA", 1.01) + _series("BBB", 1.0) + _series("SPY", 1.002)
    rows = build_features(reversed(bars))
    aaa = _latest(rows, "AAA")

    assert set(STOCK_FEATURE_NAMES) <= aaa.values.keys()
    assert set(MARKET_FEATURE_NAMES) <= aaa.values.keys()
    assert aaa.values["ret_21d"] == pytest.approx(1.01**21 - 1.0)
    assert aaa.values["ret_63_skip5"] == pytest.approx(1.01**63 - 1.0)
    assert aaa.values["ret_252_skip5"] == pytest.approx(1.01**252 - 1.0)
    assert aaa.values["relative_ret_63d"] == pytest.approx(
        (1.01**63 - 1.0) - (1.002**63 - 1.0)
    )
    assert aaa.values["trend_200d"] is not None
    assert aaa.values["median_dollar_volume_20d"] is not None
    assert aaa.values["breadth_above_sma200"] == pytest.approx(0.5)
    assert aaa.values["breadth_positive_126d"] == pytest.approx(0.5)
    prices = [100.0 * 1.01**index for index in range(270)]
    expected_sma20 = sum(prices[-20:]) / 20
    assert aaa.values["trend_20d"] == pytest.approx(prices[-1] / expected_sma20 - 1.0)
    assert aaa.values["vol_20d"] == pytest.approx(0.0, abs=1e-14)
    assert aaa.values["drawdown_63d"] == 0.0
    expected_dispersion = abs((1.01**21 - 1.0) - 0.0) / 2.0
    assert aaa.values["dispersion_21d"] == pytest.approx(expected_dispersion)


def test_gap_range_atr_and_liquidity_use_only_available_bar_data() -> None:
    start = date(2025, 1, 1)
    bars = [
        Bar(start + timedelta(days=index), "AAA", 12, 15, 10, 14, 14, 100 + index)
        for index in range(20)
    ]
    rows = build_features(bars)
    latest = rows[-1].values

    assert latest["overnight_gap"] == pytest.approx(12 / 14 - 1)
    assert latest["true_range"] == pytest.approx(5.0)
    assert latest["atr14_over_close"] == pytest.approx(5 / 14)
    assert latest["median_dollar_volume_20d"] == pytest.approx(14 * 109.5)
    assert latest["relative_volume_20d"] == pytest.approx(119 / 109.5)
    assert latest["turnover_proxy"] == pytest.approx(14 * 119)


def test_feature_history_is_prefix_invariant() -> None:
    prefix = _series("AAA", 1.003, 260) + _series("BBB", 0.999, 260) + _series("SPY", 1.001, 260)
    future = (
        _series("AAA", 1.2, 270)[260:]
        + _series("BBB", 0.8, 270)[260:]
        + _series("SPY", 1.3, 270)[260:]
    )

    before = build_features(prefix)
    after = tuple(row for row in build_features(prefix + future) if row.date <= before[-1].date)

    assert after == before


def test_breadth_uses_only_as_of_eligible_symbols_when_supplied() -> None:
    bars = _series("AAA", 1.01) + _series("BAD", 0.99) + _series("SPY", 1.002)
    last_date = max(bar.date for bar in bars)
    rows = build_features(
        bars,
        eligible_symbols_by_date={last_date: ("AAA",)},
    )
    latest_spy = _latest(rows, "SPY")

    assert latest_spy.values["breadth_above_sma200"] == 1.0
    assert latest_spy.values["breadth_positive_126d"] == 1.0


def _ranking_row(symbol: str, value: float, *, close: float = 101.0) -> FeatureRow:
    values = {
        "ret_63_skip5": value,
        "ret_126_skip5": value,
        "ret_252_skip5": value,
        "trend_50d": value,
        "trend_100d": value,
        "trend_200d": value,
        "vol_20d": 0.2,
        "drawdown_63d": 0.0,
        "adjusted_close": close,
        "sma_200d": 100.0,
    }
    return FeatureRow(date(2025, 1, 3), symbol, values)


def test_ranking_is_deterministic_and_records_exclusions() -> None:
    missing = dict(_ranking_row("MISS", 0.0).values)
    missing["ret_252_skip5"] = None
    rows = [
        _ranking_row("BBB", 1.0),
        _ranking_row("AAA", 1.0),
        _ranking_row("CCC", -1.0),
        _ranking_row("TREND", 2.0, close=100.0),
        FeatureRow(date(2025, 1, 3), "MISS", missing),
    ]

    result = rank_features(rows)

    assert [item.symbol for item in result.ranked] == ["AAA", "BBB", "CCC"]
    assert result.ranked[0].score == pytest.approx(result.ranked[1].score)
    assert [(item.symbol, item.reason) for item in result.exclusions] == [
        ("MISS", "missing:ret_252_skip5"),
        ("TREND", "price_not_above_sma200"),
    ]
    assert all(math.isfinite(item.score) for item in result.ranked)


def test_ranking_exactly_applies_winsorized_weighted_formula() -> None:
    rows = [
        _ranking_row("AAA", 3.0),
        _ranking_row("BBB", 1.0),
        _ranking_row("CCC", -2.0),
    ]
    result = rank_features(rows)

    def percentile(values: list[float], quantile: float) -> float:
        ordered = sorted(values)
        position = (len(ordered) - 1) * quantile
        lower = math.floor(position)
        upper = math.ceil(position)
        fraction = position - lower
        return ordered[lower] * (1 - fraction) + ordered[upper] * fraction

    raw = {"AAA": 3.0, "BBB": 1.0, "CCC": -2.0}
    low, high = percentile(list(raw.values()), 0.01), percentile(list(raw.values()), 0.99)
    clipped = {symbol: min(max(value, low), high) for symbol, value in raw.items()}
    mean = sum(clipped.values()) / 3
    std = math.sqrt(sum((value - mean) ** 2 for value in clipped.values()) / 3)
    z = {symbol: (value - mean) / std for symbol, value in clipped.items()}
    # All momentum/trend inputs share z; vol and drawdown are constant and get z=0.
    expected = {symbol: (0.65 + 0.30) * value for symbol, value in z.items()}
    assert {item.symbol: item.score for item in result.ranked} == pytest.approx(expected)


def _regime_row(
    session: date, volatility: float, trend: float = 0.1, breadth: float = 0.6
) -> FeatureRow:
    return FeatureRow(
        session,
        "SPY",
        {
            "spy_vol_20d": volatility,
            "spy_trend_200d": trend,
            "breadth_above_sma200": breadth,
        },
    )


def test_regime_uses_prior_only_percentile_and_exact_boundaries() -> None:
    start = date(2025, 1, 1)
    history = [_regime_row(start, 0.1), _regime_row(start + timedelta(days=1), 0.1)]
    equal_threshold = _regime_row(start + timedelta(days=2), 0.1)
    risk_on = _regime_row(start + timedelta(days=3), 0.09)
    risk_off = _regime_row(start + timedelta(days=4), 0.3, trend=0.0, breadth=0.44)
    boundary_neutral = _regime_row(
        start + timedelta(days=5), 0.1, trend=0.0, breadth=0.45
    )
    parameters = RegimeParameters(min_vol_history=2)

    prefix = classify_regimes(history + [equal_threshold, risk_on], parameters=parameters)
    full = classify_regimes(
        history + [equal_threshold, risk_on, risk_off, boundary_neutral], parameters=parameters
    )

    assert [row.regime for row in prefix] == [
        Regime.NEUTRAL,
        Regime.NEUTRAL,
        Regime.NEUTRAL,
        Regime.RISK_ON,
    ]
    assert prefix[2].prior_vol_percentile == pytest.approx(0.1)
    assert full[:4] == prefix
    assert full[4].regime is Regime.RISK_OFF
    assert full[5].regime is Regime.NEUTRAL

    interpolated = classify_regimes(
        [
            _regime_row(start, 0.1),
            _regime_row(start + timedelta(days=1), 0.2),
            _regime_row(start + timedelta(days=2), 0.18),
            _regime_row(start + timedelta(days=3), 0.179999),
        ],
        parameters=parameters,
    )
    assert interpolated[2].regime is Regime.NEUTRAL
    assert interpolated[3].regime is Regime.RISK_ON
