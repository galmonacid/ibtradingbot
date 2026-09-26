"""Pure monthly V2 allocation and daily downward-only account risk controls.

Histories must be prefixes aligned to the same consecutive exchange sessions by
caller; these primitives cannot infer missing calendar dates from price arrays.
Orders, costs, rounding and actual fills belong to the research execution layer.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.portfolio.volatility import (
    PortfolioConstructionError,
    estimate_annualized_covariance,
    expected_annualized_volatility,
)

Covariance = Mapping[str, Mapping[str, float]]


def _weights(weights: Mapping[str, float]) -> dict[str, float]:
    if any(not s or s.strip() != s or isinstance(w, bool) or not math.isfinite(w) or w < 0
           for s, w in weights.items()):
        raise PortfolioConstructionError("weights must be finite nonnegative normalized identities")
    result = {s: w for s, w in weights.items() if w > 0}
    if len(result) > 5:
        raise PortfolioConstructionError("at most five positive holdings permitted")
    return result


def _validate_psd(symbols: Sequence[str], covariance: Covariance) -> None:
    """Check positive semidefiniteness, including singular but valid matrices."""
    expected_annualized_volatility(dict.fromkeys(symbols, 1.0), covariance)
    size = len(symbols)
    factor = [[0.0] * size for _ in symbols]
    tolerance = max((covariance[s][s] for s in symbols), default=1.0) * 1e-10
    for i, left in enumerate(symbols):
        for j in range(i + 1):
            residual = covariance[left][symbols[j]] - math.fsum(
                factor[i][k] * factor[j][k] for k in range(j)
            )
            if i == j:
                if residual < -tolerance:
                    raise PortfolioConstructionError("covariance must be positive semidefinite")
                factor[i][j] = math.sqrt(max(0.0, residual))
            elif factor[j][j] > math.sqrt(tolerance):
                factor[i][j] = residual / factor[j][j]
            elif abs(residual) > tolerance:
                raise PortfolioConstructionError("covariance must be positive semidefinite")


@dataclass(frozen=True)
class DualCovariance:
    """Annualized sample covariance estimates of short and longer windows."""

    short: Covariance
    long: Covariance

    def volatility(self, weights: Mapping[str, float]) -> float:
        positive = _weights(weights)
        if not positive:
            return 0.0
        values = []
        for matrix in (self.short, self.long):
            _validate_psd(tuple(positive), matrix)
            value = expected_annualized_volatility(positive, matrix)
            if not math.isfinite(value) or value <= 1e-15:
                raise PortfolioConstructionError("invalid or zero portfolio risk")
            values.append(value)
        return max(values)


def estimate_dual_covariance(
    adjusted_price_history: Mapping[str, Sequence[float]], *, longer_window: int = 63
) -> DualCovariance:
    """Use 252 times sample covariance of final 20 and longer aligned returns."""
    if isinstance(longer_window, bool) or not isinstance(longer_window, int) or longer_window < 20:
        raise PortfolioConstructionError("longer covariance window must be at least 20")
    return DualCovariance(
        estimate_annualized_covariance(adjusted_price_history, lookback=20),
        estimate_annualized_covariance(adjusted_price_history, lookback=longer_window),
    )


def _limits(regime_ceiling: float, cash_buffer: float, target: float, cap: float) -> float:
    if any(isinstance(v, bool) or not math.isfinite(v)
           for v in (regime_ceiling, cash_buffer, target, cap)):
        raise PortfolioConstructionError("risk limits must be finite numbers")
    if not 0 <= regime_ceiling <= 1 or not .02 <= cash_buffer < 1:
        raise PortfolioConstructionError("invalid regime ceiling or cash buffer")
    if not 0 < target or not 0 < cap <= .30:
        raise PortfolioConstructionError("invalid volatility target or name cap")
    return min(regime_ceiling, 1 - cash_buffer)


def reduce_v2_targets(
    actual_weights: Mapping[str, float], covariance: DualCovariance, *,
    regime_ceiling: float, cash_buffer: float = .02, target_annual_volatility: float = .12,
    max_position_weight: float = .30, mandatory_exits: Sequence[str] = (),
    previous_target_gross: float | None = None, hard_halted: bool = False,
) -> dict[str, float]:
    """Exit, clamp, gross-scale, then risk-scale without redistributing freed cash.

    During soft drawdown callers supply the 15% name cap and previous accepted
    target gross. Missing/invalid risk inputs raise, so callers must block new
    risk and report invalid evidence, never infer an executable liquidation price.
    """
    budget = _limits(regime_ceiling, cash_buffer, target_annual_volatility, max_position_weight)
    actual = _weights(actual_weights)
    if previous_target_gross is not None:
        if (isinstance(previous_target_gross, bool) or not math.isfinite(previous_target_gross)
                or not 0 <= previous_target_gross <= 1):
            raise PortfolioConstructionError("invalid previous target gross")
        budget = min(budget, previous_target_gross)
    if hard_halted or budget == 0:
        return {}
    exits = set(mandatory_exits)
    capped = {s: min(w, max_position_weight) for s, w in actual.items() if s not in exits}
    gross = math.fsum(capped.values())
    if gross == 0:
        return {}
    gross_scale = min(1.0, budget / gross)
    capped = {s: w * gross_scale for s, w in capped.items()}
    risk_scale = min(1.0, target_annual_volatility / covariance.volatility(capped))
    return {s: w * risk_scale for s, w in capped.items()}


def build_v2_targets(
    selected_ids: Sequence[str], covariance: DualCovariance, *, regime_ceiling: float,
    cash_buffer: float = .02, target_annual_volatility: float = .12,
    max_position_weight: float = .30, previous_target_gross: float | None = None,
    hard_halted: bool = False,
) -> dict[str, float]:
    """Equal weight before risk scaling; no allocation floor or leverage-up."""
    budget = _limits(regime_ceiling, cash_buffer, target_annual_volatility, max_position_weight)
    if len(set(selected_ids)) != len(selected_ids) or len(selected_ids) > 5:
        raise PortfolioConstructionError("selected identities must be unique and at most five")
    base = dict.fromkeys(selected_ids, min(max_position_weight, budget / len(selected_ids))) \
        if selected_ids else {}
    return reduce_v2_targets(
        base, covariance, regime_ceiling=regime_ceiling, cash_buffer=cash_buffer,
        target_annual_volatility=target_annual_volatility, max_position_weight=max_position_weight,
        previous_target_gross=previous_target_gross, hard_halted=hard_halted,
    )


def apply_discretionary_band(
    actual_weights: Mapping[str, float], target_weights: Mapping[str, float],
    covariance: DualCovariance, *, regime_ceiling: float, band: float = .03,
    cash_buffer: float = .02, target_annual_volatility: float = .12,
    max_position_weight: float = .30, previous_target_gross: float | None = None,
    mandatory_exits: Sequence[str] = (), hard_halted: bool = False,
) -> dict[str, float]:
    """Retain sub-band incumbents, then enforce all whole-portfolio constraints.

    Full exits and entries never receive the band. Exact-boundary changes trade;
    a tiny tolerance prevents float representation from suppressing that boundary.
    """
    actual = _weights(actual_weights)
    target = _weights(target_weights)
    if isinstance(band, bool) or not math.isfinite(band) or band < 0:
        raise PortfolioConstructionError("band must be finite and nonnegative")
    for symbol in target.keys() & actual.keys():
        delta = abs(target[symbol] - actual[symbol])
        if delta < band and not math.isclose(delta, band, rel_tol=0, abs_tol=1e-12):
            target[symbol] = actual[symbol]
    return reduce_v2_targets(
        target, covariance, regime_ceiling=regime_ceiling, cash_buffer=cash_buffer,
        target_annual_volatility=target_annual_volatility, max_position_weight=max_position_weight,
        previous_target_gross=previous_target_gross, mandatory_exits=mandatory_exits,
        hard_halted=hard_halted,
    )


@dataclass(frozen=True)
class V2DrawdownState:
    """Account-lifetime high water and immutable permanently latched hard halt."""

    high_water_mark: float
    soft_active: bool = False
    hard_halted: bool = False
    drawdown: float = 0.0

    def observe(self, equity: float) -> V2DrawdownState:
        if (not math.isfinite(self.high_water_mark) or self.high_water_mark <= 0
                or not math.isfinite(equity) or equity < 0):
            raise PortfolioConstructionError("equity/high water must be valid account values")
        high_water = max(self.high_water_mark, equity)
        drawdown = equity / high_water - 1
        return V2DrawdownState(
            high_water, drawdown <= -.10 + 1e-12,
            self.hard_halted or drawdown <= -.15 + 1e-12, drawdown,
        )
