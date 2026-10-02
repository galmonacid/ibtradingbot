"""Strict R3.3 development simulator configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class R3DevelopmentConfig:
    contract_version: str
    commission_per_share_usd: float
    minimum_commission_usd: float
    slippage_bps: float
    fx_friction_bps: float
    conversion_bps: float
    monthly_account_fee_gbp: float
    annual_operating_cost_gbp: float
    liquidation_reserve_gbp: float
    bootstrap_paths: int
    paired_block_months: int

    def __post_init__(self) -> None:
        expected: dict[str, int | float | str] = {
            "contract_version": "r3.3-development-v1",
            "commission_per_share_usd": 0.005,
            "minimum_commission_usd": 1.0,
            "slippage_bps": 5.0,
            "fx_friction_bps": 5.0,
            "conversion_bps": 3.0,
            "monthly_account_fee_gbp": 3.0,
            "annual_operating_cost_gbp": 0.0,
            "liquidation_reserve_gbp": 5.03,
            "bootstrap_paths": 2000,
            "paired_block_months": 12,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError(f"{name} must retain the registered value {value}")
        numeric = (
            self.commission_per_share_usd,
            self.minimum_commission_usd,
            self.slippage_bps,
            self.fx_friction_bps,
            self.conversion_bps,
            self.monthly_account_fee_gbp,
            self.annual_operating_cost_gbp,
            self.liquidation_reserve_gbp,
        )
        if any(not math.isfinite(value) or value < 0 for value in numeric):
            raise ValueError("R3.3 costs must be finite and nonnegative")


def load_r3_development_config(path: Path) -> R3DevelopmentConfig:
    content: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError("R3.3 development configuration must be a mapping")
    expected = set(R3DevelopmentConfig.__dataclass_fields__)
    if set(content) != expected:
        raise ValueError(
            f"R3.3 configuration keys mismatch; missing={sorted(expected - set(content))}, "
            f"extra={sorted(set(content) - expected)}"
        )
    return R3DevelopmentConfig(**content)
