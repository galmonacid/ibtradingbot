"""Explicit, strict configuration for the fixed Phase 3 V2 research candidate."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields, replace
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass(frozen=True)
class V2Config:
    strategy_version: str = "monthly-momentum-v2"
    target_positions: int = 4
    numerator_offset: int = 21
    stock_sma: int = 200
    spy_sma: int = 200
    selection_schedule: Literal["monthly", "penultimate_monthly", "biweekly"] = "monthly"
    biweekly_anchor: date | None = None
    volatility_ceiling: float = 0.12
    long_covariance_window: int = 63
    discretionary_band: float = 0.03
    cash_buffer: float = 0.02
    max_position_weight: float = 0.30
    soft_position_weight: float = 0.15
    soft_drawdown: float = 0.10
    hard_drawdown: float = 0.15
    min_order_value_gbp: float = 150.0
    minimum_price_usd: float = 10.0
    minimum_median_dollar_volume_20d: float = 500_000_000.0
    commission_per_order_usd: float = 0.35
    slippage_bps: float = 5.0
    fx_buffer_bps: float = 5.0
    execution_delay_sessions: int = 1
    max_fx_age_days: int = 4

    def __post_init__(self) -> None:
        choices = {
            "target_positions": (3, 4, 5),
            "numerator_offset": (10, 21, 42),
            "stock_sma": (160, 200, 240),
            "spy_sma": (160, 200, 240),
            "long_covariance_window": (42, 63, 84),
        }
        for key, allowed in choices.items():
            value = getattr(self, key)
            if type(value) is not int or value not in allowed:
                raise ValueError(f"{key} must be one of {allowed}")
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in choices or field.name in (
                "strategy_version",
                "selection_schedule",
                "biweekly_anchor",
                "execution_delay_sessions",
                "max_fx_age_days",
            ):
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{field.name} must be finite numeric")
        if self.strategy_version != "monthly-momentum-v2":
            raise ValueError("strategy_version must identify V2")
        if self.selection_schedule not in ("monthly", "penultimate_monthly", "biweekly"):
            raise ValueError("unknown selection_schedule")
        if self.biweekly_anchor is not None and type(self.biweekly_anchor) is not date:
            raise ValueError("biweekly_anchor must be a date")
        if self.selection_schedule == "biweekly" and self.biweekly_anchor is None:
            raise ValueError("biweekly schedule requires an explicit anchored completed week")
        if self.volatility_ceiling not in (0.10, 0.12, 0.14):
            raise ValueError("volatility_ceiling outside predeclared sensitivity design")
        if self.discretionary_band not in (0.0, 0.03, 0.05):
            raise ValueError("discretionary_band outside predeclared sensitivity design")
        if not 0.02 <= self.cash_buffer < 1.0:
            raise ValueError("cash_buffer must preserve at least 2% cash")
        if not 0 < self.max_position_weight <= 0.30:
            raise ValueError("max_position_weight exceeds hard safety limits")
        if self.soft_position_weight != 0.15 or self.soft_drawdown != 0.10:
            raise ValueError("soft drawdown controls are fixed")
        if self.hard_drawdown != 0.15:
            raise ValueError("hard drawdown circuit breaker is fixed")
        floors = {
            "min_order_value_gbp": 150,
            "minimum_price_usd": 10,
            "minimum_median_dollar_volume_20d": 500_000_000,
            "commission_per_order_usd": 0.35,
            "slippage_bps": 5,
            "fx_buffer_bps": 5,
        }
        for key, minimum in floors.items():
            if getattr(self, key) < minimum:
                raise ValueError(f"{key} cannot be below {minimum}")
        if type(self.max_fx_age_days) is not int or not 0 <= self.max_fx_age_days <= 7:
            raise ValueError("max_fx_age_days must be an integer from zero through seven")
        if type(self.execution_delay_sessions) is not int or self.execution_delay_sessions < 1:
            raise ValueError("execution must occur at least one session after decision")

    @property
    def sha256(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()


def load_v2_config(path: Path) -> V2Config:
    """Reject unknown keys, ambiguous duplicate keys and unsafe types/values."""

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[str, object]:
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if not isinstance(key, str) or key in result:
                raise ValueError("configuration keys must be unique strings")
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    content = yaml.load(path.read_text(), Loader=UniqueLoader)
    if not isinstance(content, dict):
        raise ValueError("V2 configuration must be a mapping")
    if set(content) - {item.name for item in fields(V2Config)}:
        raise ValueError("unknown V2 configuration keys")
    if content.get("strategy_version") != "monthly-momentum-v2":
        raise ValueError("an explicit V2 strategy_version is required")
    if isinstance(content.get("biweekly_anchor"), str):
        content["biweekly_anchor"] = date.fromisoformat(content["biweekly_anchor"])
    return V2Config(**content)


def sensitivity_configs(biweekly_anchor: date) -> tuple[tuple[str, V2Config], ...]:
    """The 16 fixed one-axis variants; never optimize the account halt."""
    baseline = V2Config()
    variants: list[tuple[str, V2Config]] = []
    axes: dict[str, tuple[Any, Any]] = {
        "target_positions": (3, 5),
        "numerator_offset": (10, 42),
        "stock_sma": (160, 240),
        "spy_sma": (160, 240),
        "volatility_ceiling": (0.10, 0.14),
        "long_covariance_window": (42, 84),
        "discretionary_band": (0.0, 0.05),
    }
    for axis, values in axes.items():
        for value in values:
            variants.append((f"{axis}={value}", replace(baseline, **{axis: value})))
    variants.append(
        (
            "selection_schedule=penultimate_monthly",
            replace(baseline, selection_schedule="penultimate_monthly"),
        )
    )
    variants.append(
        (
            "selection_schedule=biweekly",
            replace(baseline, selection_schedule="biweekly", biweekly_anchor=biweekly_anchor),
        )
    )
    return tuple(variants)
