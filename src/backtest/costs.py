"""Deterministic transaction-cost assumptions for research fills."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class CostModel:
    """Commission, adverse execution slippage, and currency friction."""

    commission_per_order: float = 0.35
    slippage_bps_each_side: float = 5.0
    fx_buffer_bps: float = 5.0

    def __post_init__(self) -> None:
        for name, value in (
            ("commission_per_order", self.commission_per_order),
            ("slippage_bps_each_side", self.slippage_bps_each_side),
            ("fx_buffer_bps", self.fx_buffer_bps),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.slippage_bps_each_side >= 10_000.0:
            raise ValueError("slippage_bps_each_side must be below 10000")

    @property
    def fx_rate(self) -> float:
        return self.fx_buffer_bps / 10_000.0

    def execution_price(self, reference_price: float, side: Side) -> float:
        """Return a price moved adversely by configured slippage."""
        if not math.isfinite(reference_price) or reference_price <= 0.0:
            raise ValueError("reference_price must be finite and positive")
        direction = 1.0 if side == "buy" else -1.0
        return reference_price * (1.0 + direction * self.slippage_bps_each_side / 10_000.0)

    def fx_cost(self, executed_notional: float) -> float:
        if not math.isfinite(executed_notional) or executed_notional < 0.0:
            raise ValueError("executed_notional must be finite and non-negative")
        return executed_notional * self.fx_rate
