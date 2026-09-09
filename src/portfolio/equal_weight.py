"""Long-only equal-weight portfolio construction."""

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum


class Regime(StrEnum):
    """Market regimes understood by the Phase 1 portfolio constructor."""

    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


def build_equal_weight_targets(
    ordered_symbols: Sequence[str],
    *,
    target_positions: int,
    regime_ceiling: float,
    cash_buffer: float,
    max_position_weight: float,
    max_positions: int,
) -> dict[str, float]:
    """Select candidates in order and allocate an equal, safely capped weight.

    Duplicate and blank symbols are ignored. Any allocation prevented by a
    concentration limit remains cash rather than being redistributed.
    """
    if (
        not isinstance(target_positions, int)
        or isinstance(target_positions, bool)
        or target_positions < 0
    ):
        raise ValueError("target_positions must be a non-negative integer")
    if (
        not isinstance(max_positions, int)
        or isinstance(max_positions, bool)
        or max_positions < 0
        or max_positions > 5
    ):
        raise ValueError("max_positions must be an integer between 0 and 5")
    for name, value in (
        ("regime_ceiling", regime_ceiling),
        ("cash_buffer", cash_buffer),
        ("max_position_weight", max_position_weight),
    ):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number")
    if not 0.0 <= regime_ceiling <= 1.0:
        raise ValueError("regime_ceiling must be between 0 and 1")
    if not 0.0 <= cash_buffer < 1.0:
        raise ValueError("cash_buffer must be between 0 and 1")
    if not 0.0 <= max_position_weight <= 0.30:
        raise ValueError("max_position_weight must be between 0 and 0.30")

    selected: list[str] = []
    seen: set[str] = set()
    count = min(target_positions, max_positions)
    for raw_symbol in ordered_symbols:
        symbol = raw_symbol.strip()
        if symbol and symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
        if len(selected) == count:
            break
    if not selected:
        return {}

    total_weight = min(regime_ceiling, 1.0 - cash_buffer)
    weight = min(max_position_weight, total_weight / len(selected))
    if weight <= 0.0:
        return {}
    return {symbol: weight for symbol in selected}
