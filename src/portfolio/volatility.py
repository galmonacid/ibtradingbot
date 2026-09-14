"""Causal volatility estimates and constrained inverse-volatility sizing."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class PortfolioConstructionError(ValueError):
    """Raised when risk inputs cannot support safe portfolio construction."""


@dataclass(frozen=True)
class VolatilityTargets:
    """Auditable result of inverse-volatility construction and risk scaling."""

    weights: dict[str, float]
    unscaled_weights: dict[str, float]
    excluded: dict[str, str]
    expected_volatility_before_scaling: float
    expected_volatility: float
    volatility_scale: float


def estimate_annualized_covariance(
    adjusted_price_history: Mapping[str, Sequence[float]],
    *,
    lookback: int = 20,
    annualization_sessions: int = 252,
) -> dict[str, dict[str, float]]:
    """Estimate sample covariance from the final ``lookback`` observed returns.

    The caller supplies an as-of price prefix; this function never requests or
    infers later observations. All series must cover the same observation count
    so covariance rows cannot be silently misaligned.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 2:
        raise PortfolioConstructionError("lookback must be an integer of at least 2")
    if (
        isinstance(annualization_sessions, bool)
        or not isinstance(annualization_sessions, int)
        or annualization_sessions <= 0
    ):
        raise PortfolioConstructionError("annualization_sessions must be positive")
    if not adjusted_price_history:
        raise PortfolioConstructionError("at least one price history is required")

    lengths = {len(prices) for prices in adjusted_price_history.values()}
    if len(lengths) != 1:
        raise PortfolioConstructionError("price histories must be explicitly aligned")
    required = lookback + 1
    if next(iter(lengths)) < required:
        raise PortfolioConstructionError(f"price histories require at least {required} values")

    returns: dict[str, list[float]] = {}
    for raw_symbol, history in sorted(adjusted_price_history.items()):
        symbol = raw_symbol.strip()
        if not symbol or symbol != raw_symbol:
            raise PortfolioConstructionError("symbols must be non-blank and normalized")
        prices = [float(value) for value in history[-required:]]
        if any(not math.isfinite(value) or value <= 0.0 for value in prices):
            raise PortfolioConstructionError(f"invalid adjusted price history for {symbol}")
        sample = [prices[index] / prices[index - 1] - 1.0 for index in range(1, required)]
        if math.isclose(statistics.stdev(sample), 0.0, abs_tol=1e-15):
            raise PortfolioConstructionError(f"zero realized volatility for {symbol}")
        returns[symbol] = sample

    covariance: dict[str, dict[str, float]] = {}
    for left, left_returns in returns.items():
        covariance[left] = {}
        left_mean = statistics.fmean(left_returns)
        for right, right_returns in returns.items():
            right_mean = statistics.fmean(right_returns)
            value = math.fsum(
                (left_value - left_mean) * (right_value - right_mean)
                for left_value, right_value in zip(left_returns, right_returns, strict=True)
            ) / (lookback - 1)
            covariance[left][right] = value * annualization_sessions
    return covariance


def expected_annualized_volatility(
    weights: Mapping[str, float], covariance: Mapping[str, Mapping[str, float]]
) -> float:
    """Return ``sqrt(w'Cov w)`` after strict matrix/input validation."""
    if not weights:
        return 0.0
    symbols = tuple(weights)
    for symbol, weight in weights.items():
        if not symbol.strip() or not math.isfinite(weight) or weight < 0.0:
            raise PortfolioConstructionError("weights must be finite, non-negative, and named")
    variance = 0.0
    for left in symbols:
        if left not in covariance:
            raise PortfolioConstructionError(f"missing covariance row for {left}")
        for right in symbols:
            value = covariance[left].get(right)
            mirror = covariance.get(right, {}).get(left)
            if value is None or mirror is None:
                raise PortfolioConstructionError(f"missing covariance for {left}/{right}")
            if not math.isfinite(value) or not math.isfinite(mirror):
                raise PortfolioConstructionError(f"non-finite covariance for {left}/{right}")
            if not math.isclose(value, mirror, rel_tol=1e-10, abs_tol=1e-12):
                raise PortfolioConstructionError("covariance matrix must be symmetric")
            if left == right and value <= 0.0:
                raise PortfolioConstructionError(f"non-positive covariance diagonal for {left}")
            variance += weights[left] * weights[right] * value
    if variance < -1e-12:
        raise PortfolioConstructionError("covariance implies negative portfolio variance")
    return math.sqrt(max(0.0, variance))


def _bounded_inverse_vol_weights(
    symbols: Sequence[str],
    volatilities: Mapping[str, float],
    total: float,
    minimum: float,
    maximum: float,
) -> dict[str, float]:
    inverse = {symbol: 1.0 / volatilities[symbol] for symbol in symbols}

    def allocated(multiplier: float) -> float:
        return math.fsum(
            min(maximum, max(minimum, multiplier * inverse[symbol])) for symbol in symbols
        )

    lower = 0.0
    upper = total / min(inverse.values())
    for _iteration in range(100):
        midpoint = (lower + upper) / 2.0
        if allocated(midpoint) < total:
            lower = midpoint
        else:
            upper = midpoint
    multiplier = (lower + upper) / 2.0
    weights = {
        symbol: min(maximum, max(minimum, multiplier * inverse[symbol])) for symbol in symbols
    }
    # Remove the tiny bisection residual without changing deterministic order.
    residual = total - math.fsum(weights.values())
    for symbol in symbols:
        room = maximum - weights[symbol] if residual > 0.0 else weights[symbol] - minimum
        adjustment = math.copysign(min(abs(residual), room), residual)
        weights[symbol] += adjustment
        residual -= adjustment
        if abs(residual) <= 1e-14:
            break
    return weights


def build_inverse_volatility_targets(
    ordered_symbols: Sequence[str],
    annualized_volatilities: Mapping[str, float],
    covariance: Mapping[str, Mapping[str, float]],
    *,
    target_positions: int,
    regime_ceiling: float,
    target_annual_volatility: float,
    cash_buffer: float = 0.02,
    min_position_weight: float = 0.10,
    max_position_weight: float = 0.30,
    max_positions: int = 5,
) -> VolatilityTargets:
    """Build bounded inverse-volatility targets, then scale risk only downward."""
    numeric = {
        "regime_ceiling": regime_ceiling,
        "target_annual_volatility": target_annual_volatility,
        "cash_buffer": cash_buffer,
        "min_position_weight": min_position_weight,
        "max_position_weight": max_position_weight,
    }
    if any(isinstance(value, bool) or not math.isfinite(value) for value in numeric.values()):
        raise PortfolioConstructionError("portfolio parameters must be finite numbers")
    if not 0.0 <= regime_ceiling <= 1.0 or not 0.02 <= cash_buffer < 1.0:
        raise PortfolioConstructionError("regime ceiling or cash buffer is outside hard limits")
    if not 0.0 < min_position_weight <= max_position_weight <= 0.30:
        raise PortfolioConstructionError("position bounds must satisfy 0 < min <= max <= 0.30")
    if target_annual_volatility <= 0.0:
        raise PortfolioConstructionError("target annual volatility must be positive")
    if (
        isinstance(target_positions, bool)
        or not isinstance(target_positions, int)
        or target_positions < 0
        or isinstance(max_positions, bool)
        or not isinstance(max_positions, int)
        or not 0 <= max_positions <= 5
    ):
        raise PortfolioConstructionError("position counts must be valid integers capped at five")

    requested_positions = min(target_positions, max_positions)
    if requested_positions == 0:
        return VolatilityTargets({}, {}, {}, 0.0, 0.0, 1.0)

    excluded: dict[str, str] = {}
    candidates: list[str] = []
    seen: set[str] = set()
    for raw_symbol in ordered_symbols:
        symbol = raw_symbol.strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        volatility = annualized_volatilities.get(symbol)
        if volatility is None:
            excluded[symbol] = "missing_volatility"
        elif isinstance(volatility, bool) or not math.isfinite(volatility) or volatility <= 0.0:
            excluded[symbol] = "invalid_volatility"
        else:
            candidates.append(symbol)
        if len(candidates) == requested_positions:
            break

    budget = min(regime_ceiling, 1.0 - cash_buffer)
    feasible_count = min(len(candidates), int((budget + 1e-12) / min_position_weight))
    selected = candidates[:feasible_count]
    for symbol in candidates[feasible_count:]:
        excluded[symbol] = "minimum_weight_infeasible"
    if not selected or budget <= 0.0:
        return VolatilityTargets({}, {}, excluded, 0.0, 0.0, 1.0)

    allocation = min(budget, len(selected) * max_position_weight)
    unscaled = _bounded_inverse_vol_weights(
        selected,
        annualized_volatilities,
        allocation,
        min_position_weight,
        max_position_weight,
    )
    before = expected_annualized_volatility(unscaled, covariance)
    if not math.isfinite(before) or before <= 0.0:
        raise PortfolioConstructionError("covariance produces invalid or zero portfolio volatility")
    scale = min(1.0, target_annual_volatility / before)
    weights = {symbol: weight * scale for symbol, weight in unscaled.items()}
    after = expected_annualized_volatility(weights, covariance)
    return VolatilityTargets(weights, unscaled, excluded, before, after, scale)
