import math

import pytest

from src.portfolio import (
    PortfolioConstructionError,
    build_inverse_volatility_targets,
    estimate_annualized_covariance,
    expected_annualized_volatility,
)


def test_covariance_uses_only_trailing_as_of_prices_and_is_annualized() -> None:
    histories = {
        "AAA": [100.0, 101.0, 99.0, 102.0, 104.0],
        "BBB": [50.0, 49.0, 51.0, 50.0, 52.0],
    }
    covariance = estimate_annualized_covariance(histories, lookback=3)
    changed_discarded_prefix = estimate_annualized_covariance(
        {symbol: [prices[0] * 10.0, *prices[1:]] for symbol, prices in histories.items()},
        lookback=3,
    )
    assert covariance["AAA"]["BBB"] == pytest.approx(covariance["BBB"]["AAA"])
    assert covariance["AAA"]["AAA"] > 0.0
    assert changed_discarded_prefix == covariance


@pytest.mark.parametrize(
    "histories,message",
    [
        ({"AAA": [1.0, 1.1, 1.2], "BBB": [1.0, 1.1]}, "aligned"),
        ({"AAA": [1.0, 1.0, 1.0]}, "zero realized"),
        ({"AAA": [1.0, math.nan, 1.1]}, "invalid adjusted"),
    ],
)
def test_covariance_fails_closed_on_invalid_inputs(
    histories: dict[str, list[float]], message: str
) -> None:
    with pytest.raises(PortfolioConstructionError, match=message):
        estimate_annualized_covariance(histories, lookback=2)


def test_inverse_volatility_active_set_applies_bounds_and_deterministic_order() -> None:
    covariance = {
        "LOW": {"LOW": 0.01, "MID": 0.0, "HIGH": 0.0},
        "MID": {"LOW": 0.0, "MID": 0.04, "HIGH": 0.0},
        "HIGH": {"LOW": 0.0, "MID": 0.0, "HIGH": 0.16},
    }
    result = build_inverse_volatility_targets(
        ["LOW", "MID", "HIGH"],
        {"LOW": 0.10, "MID": 0.20, "HIGH": 0.40},
        covariance,
        target_positions=3,
        regime_ceiling=0.70,
        target_annual_volatility=1.0,
    )
    assert list(result.weights) == ["LOW", "MID", "HIGH"]
    assert result.weights == pytest.approx({"LOW": 0.30, "MID": 0.2666666667, "HIGH": 0.1333333333})
    assert sum(result.weights.values()) == pytest.approx(0.70)
    assert result.volatility_scale == 1.0


def test_volatility_target_scales_only_down_and_preserves_hard_caps() -> None:
    covariance = {
        "AAA": {"AAA": 0.16, "BBB": 0.0},
        "BBB": {"AAA": 0.0, "BBB": 0.16},
    }
    result = build_inverse_volatility_targets(
        ["AAA", "BBB"],
        {"AAA": 0.40, "BBB": 0.40},
        covariance,
        target_positions=2,
        regime_ceiling=1.0,
        target_annual_volatility=0.10,
    )
    assert result.unscaled_weights == {"AAA": 0.30, "BBB": 0.30}
    assert result.expected_volatility == pytest.approx(0.10)
    assert 0.0 < result.volatility_scale < 1.0
    assert sum(result.weights.values()) <= 0.98
    assert max(result.weights.values()) <= 0.30


def test_invalid_vols_are_excluded_and_covariance_gaps_fail_closed() -> None:
    covariance = {"AAA": {"AAA": 0.04}}
    result = build_inverse_volatility_targets(
        ["MISSING", "ZERO", "AAA"],
        {"ZERO": 0.0, "AAA": 0.20},
        covariance,
        target_positions=1,
        regime_ceiling=0.50,
        target_annual_volatility=1.0,
    )
    assert result.weights == {"AAA": 0.30}
    assert result.excluded == {
        "MISSING": "missing_volatility",
        "ZERO": "invalid_volatility",
    }
    with pytest.raises(PortfolioConstructionError, match="missing covariance"):
        expected_annualized_volatility({"AAA": 0.2, "BBB": 0.2}, covariance)
    with pytest.raises(PortfolioConstructionError, match="non-positive covariance"):
        expected_annualized_volatility({"AAA": 0.2}, {"AAA": {"AAA": 0.0}})


def test_risk_off_and_too_small_budget_hold_cash() -> None:
    covariance = {"AAA": {"AAA": 0.04}}
    for ceiling in (0.0, 0.05):
        result = build_inverse_volatility_targets(
            ["AAA"],
            {"AAA": 0.20},
            covariance,
            target_positions=1,
            regime_ceiling=ceiling,
            target_annual_volatility=0.12,
        )
        assert result.weights == {}

    no_positions = build_inverse_volatility_targets(
        ["AAA"],
        {"AAA": 0.20},
        covariance,
        target_positions=0,
        regime_ceiling=1.0,
        target_annual_volatility=0.12,
    )
    assert no_positions.weights == {}
