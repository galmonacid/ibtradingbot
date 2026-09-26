"""Risk precedence and covariance checks for the monthly V2 candidate."""
import math
import statistics

import pytest

from src.portfolio.v2 import (
    DualCovariance,
    V2DrawdownState,
    apply_discretionary_band,
    build_v2_targets,
    estimate_dual_covariance,
    reduce_v2_targets,
)
from src.portfolio.volatility import PortfolioConstructionError


def covariance(symbols: str = 'ABCD', variance: float = .01) -> DualCovariance:
    matrix = {a: {b: variance if a == b else 0.0 for b in symbols} for a in symbols}
    return DualCovariance(matrix, matrix)


def test_equal_weights_cap_without_redistribution_or_floor() -> None:
    assert build_v2_targets(['A'], covariance(), regime_ceiling=.98) == {'A': .3}
    assert build_v2_targets(['A', 'B'], covariance(), regime_ceiling=.98) == {'A': .3, 'B': .3}
    assert build_v2_targets(['A', 'B'], covariance(), regime_ceiling=.01) == {'A': .005, 'B': .005}
    assert build_v2_targets([], DualCovariance({}, {}), regime_ceiling=0) == {}


def test_longer_risk_estimate_controls_uniform_scale() -> None:
    risk = DualCovariance(covariance().short, covariance(variance=1).long)
    weights = build_v2_targets(list('ABCD'), risk, regime_ceiling=.98)
    assert weights == pytest.approx(dict.fromkeys('ABCD', .06))
    assert risk.volatility(weights) == pytest.approx(.12)


def test_daily_reduction_order_and_no_unrelated_buys() -> None:
    risk = covariance(variance=1)
    result = reduce_v2_targets({'A': .4, 'B': .2, 'C': .1}, risk,
                               mandatory_exits=['A'], regime_ceiling=.2,
                               max_position_weight=.15)
    # After removal/capping .15/.10, gross scaling .12/.08, then risk scaling.
    scale = .12 / math.hypot(.12, .08)
    assert result == pytest.approx({'B': .12 * scale, 'C': .08 * scale})
    assert all(result[s] <= w for s, w in {'B': .2, 'C': .1}.items())
    assert reduce_v2_targets({'A': .2}, DualCovariance({}, {}), regime_ceiling=0) == {}


def test_soft_drawdown_cap_and_previous_target_gross() -> None:
    result = build_v2_targets(list('ABCD'), covariance(), regime_ceiling=.98,
                              max_position_weight=.15, previous_target_gross=.4)
    assert result == pytest.approx(dict.fromkeys('ABCD', .1))


def test_band_boundary_full_exit_and_risk_precedence() -> None:
    risk = covariance()
    assert apply_discretionary_band({'A': .2}, {'A': .22}, risk,
                                     regime_ceiling=.98) == {'A': .2}
    assert apply_discretionary_band({'A': .2}, {'A': .23}, risk,
                                     regime_ceiling=.98) == {'A': .23}
    assert apply_discretionary_band({'A': .02}, {}, risk, regime_ceiling=.98) == {}
    assert apply_discretionary_band({'A': .31}, {'A': .3}, risk,
                                     regime_ceiling=.98) == {'A': .3}
    assert apply_discretionary_band({'A': .16}, {'A': .15}, risk,
                                     regime_ceiling=.98, max_position_weight=.15) == {'A': .15}
    high_risk = covariance(variance=1)
    target = apply_discretionary_band({'A': .14}, {'A': .12}, high_risk, regime_ceiling=.98)
    assert target == pytest.approx({'A': .12})


def test_band_cannot_break_aggregate_cash_limit() -> None:
    result = apply_discretionary_band(dict.fromkeys('ABCD', .25), dict.fromkeys('ABCD', .245),
                                      covariance(), regime_ceiling=.98)
    assert math.fsum(result.values()) == pytest.approx(.98)


def test_drawdown_thresholds_and_permanent_halt() -> None:
    state = V2DrawdownState(100)
    assert not state.observe(90.01).soft_active
    state = state.observe(90)
    assert state.soft_active and not state.hard_halted
    state = state.observe(85)
    assert state.hard_halted
    recovered = state.observe(110)
    assert recovered.high_water_mark == 110
    assert recovered.hard_halted and not recovered.soft_active
    assert build_v2_targets(['A'], covariance(), regime_ceiling=.98,
                              hard_halted=recovered.hard_halted) == {}


def test_aligned_sample_covariance_matches_manual_variance() -> None:
    returns = [(.01 if n % 3 else -.02) for n in range(63)]
    prices = [100.0]
    for value in returns:
        prices.append(prices[-1] * (1 + value))
    risk = estimate_dual_covariance({'A': prices})
    assert risk.short['A']['A'] == pytest.approx(252 * statistics.variance(returns[-20:]))
    assert risk.long['A']['A'] == pytest.approx(252 * statistics.variance(returns))
    with pytest.raises(PortfolioConstructionError, match='aligned'):
        estimate_dual_covariance({'A': prices, 'B': prices[:-1]})
    with pytest.raises(PortfolioConstructionError, match='64'):
        estimate_dual_covariance({'A': prices[:-1]})
    with pytest.raises(PortfolioConstructionError, match='zero'):
        estimate_dual_covariance({'A': [100.] * 64})


@pytest.mark.parametrize('matrix', [
    {'A': {'A': float('nan')}}, {'A': {'A': -1}}, {},
    {'A': {'A': 1., 'B': 2.}, 'B': {'A': 2., 'B': 1.}},
    {'A': {'A': 1., 'B': .1}, 'B': {'A': .2, 'B': 1.}},
    {'A': {'A': 1., 'B': -1.}, 'B': {'A': -1., 'B': 1.}},
])
def test_invalid_or_zero_risk_fails_closed(matrix: dict[str, dict[str, float]]) -> None:
    with pytest.raises(PortfolioConstructionError):
        DualCovariance(matrix, matrix).volatility({'A': .2, 'B': .2})


def test_singular_positive_risk_is_valid() -> None:
    matrix = {'A': {'A': 1., 'B': 1.}, 'B': {'A': 1., 'B': 1.}}
    assert DualCovariance(matrix, matrix).volatility({'A': .2, 'B': .2}) == pytest.approx(.4)


@pytest.mark.parametrize('kwargs', [
    {'cash_buffer': .01}, {'regime_ceiling': 1.1}, {'max_position_weight': .31},
    {'target_annual_volatility': 0.}, {'previous_target_gross': float('nan')},
])
def test_invalid_risk_limits(kwargs: dict[str, float]) -> None:
    parameters = {'regime_ceiling': .98, **kwargs}
    with pytest.raises(PortfolioConstructionError):
        build_v2_targets(['A'], covariance(), **parameters)
