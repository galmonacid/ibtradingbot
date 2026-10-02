"""Strict configuration for the R3.1 offline economics and exposure audit."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass(frozen=True)
class R3FeasibilityConfig:
    strategy_version: str = "r3.1-feasibility-v1"
    initial_capital_gbp: float = 3000.0
    target_profit_gbp: float = 300.0
    target_positions: int = 4
    cash_buffer: float = 0.02
    max_position_weight: float = 0.30
    volatility_ceiling: float = 0.12
    minimum_price_usd: float = 10.0
    legacy_liquidity_usd: float = 500_000_000.0
    r3_liquidity_usd: float = 20_000_000.0
    capacity_fraction: float = 0.0001
    legacy_min_order_gbp: float = 150.0
    round_trip_cost_ceiling: float = 0.01
    commission_per_share_usd: float = 0.005
    commission_min_usd: float = 1.0
    slippage_bps: float = 5.0
    fx_friction_bps: float = 5.0
    conversion_bps: float = 3.0
    monthly_account_minimum_gbp: float = 3.0
    annual_data_gbp: float | None = None
    annual_hosting_gbp: float | None = None
    annual_software_gbp: float | None = None
    research_cost_from_capital_gbp: float = 0.0
    commission_offset_treatment: Literal[
        "no_offset_full_monthly_minimum",
        "eligible_commissions_offset_monthly_minimum",
    ] = "no_offset_full_monthly_minimum"
    whole_share_us_stocks_assumed_permitted: bool = False
    account_tariff_evidence: str | None = None
    account_permissions_evidence: str | None = None
    account_tariff_verified: bool = False
    account_permissions_verified: bool = False
    operating_costs_verified: bool = False
    fractional_shares: bool = False
    scope_decision: Literal[
        "stop_on_open_evidence", "proceed_with_open_evidence"
    ] = "stop_on_open_evidence"
    scope_decision_recorded_at: str | None = None
    scope_decision_note: str | None = None

    def __post_init__(self) -> None:
        if self.strategy_version != "r3.1-feasibility-v1":
            raise ValueError("strategy_version must identify the R3.1 feasibility contract")
        if self.initial_capital_gbp != 3000 or self.target_profit_gbp != 300:
            raise ValueError("R3 requires £3,000 initial capital and profit strictly above £300")
        if self.target_positions != 4:
            raise ValueError("R3.1 must use the registered four-stock center")
        fixed = {
            "cash_buffer": (self.cash_buffer, 0.02),
            "max_position_weight": (self.max_position_weight, 0.30),
            "volatility_ceiling": (self.volatility_ceiling, 0.12),
            "minimum_price_usd": (self.minimum_price_usd, 10.0),
            "legacy_liquidity_usd": (self.legacy_liquidity_usd, 500_000_000.0),
            "r3_liquidity_usd": (self.r3_liquidity_usd, 20_000_000.0),
            "capacity_fraction": (self.capacity_fraction, 0.0001),
            "legacy_min_order_gbp": (self.legacy_min_order_gbp, 150.0),
            "round_trip_cost_ceiling": (self.round_trip_cost_ceiling, 0.01),
        }
        for name, (actual, expected) in fixed.items():
            if actual != expected:
                raise ValueError(f"{name} must retain the predeclared R3.1 value {expected}")
        numeric = (
            self.commission_per_share_usd,
            self.commission_min_usd,
            self.slippage_bps,
            self.fx_friction_bps,
            self.conversion_bps,
            self.monthly_account_minimum_gbp,
            self.research_cost_from_capital_gbp,
        )
        if any(
            isinstance(value, bool) or not math.isfinite(value) or value < 0
            for value in numeric
        ):
            raise ValueError("cost assumptions must be finite nonnegative numbers")
        if self.commission_min_usd < 0.35 or self.slippage_bps < 5 or self.fx_friction_bps < 5:
            raise ValueError("R3.1 cost assumptions cannot weaken the retained conservative floors")
        for name in ("annual_data_gbp", "annual_hosting_gbp", "annual_software_gbp"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value < 0
            ):
                raise ValueError(f"{name} must be null or a finite nonnegative number")
        if self.commission_offset_treatment not in (
            "no_offset_full_monthly_minimum",
            "eligible_commissions_offset_monthly_minimum",
        ):
            raise ValueError("unknown commission-offset treatment")
        for name in (
            "whole_share_us_stocks_assumed_permitted",
            "account_tariff_verified",
            "account_permissions_verified",
            "operating_costs_verified",
            "fractional_shares",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        if self.account_tariff_verified and not self.account_tariff_evidence:
            raise ValueError("verified tariff status requires documentary evidence")
        if self.account_permissions_verified and not self.account_permissions_evidence:
            raise ValueError("verified permission status requires documentary evidence")
        if self.operating_costs_verified and any(
            getattr(self, name) is None
            for name in ("annual_data_gbp", "annual_hosting_gbp", "annual_software_gbp")
        ):
            raise ValueError("verified operating costs require every annual cost value")
        if self.fractional_shares:
            raise ValueError("R3.1 cannot assume fractional-share permission")
        if self.scope_decision not in (
            "stop_on_open_evidence",
            "proceed_with_open_evidence",
        ):
            raise ValueError("unknown R3.1 scope decision")
        if self.scope_decision == "proceed_with_open_evidence":
            if not self.scope_decision_recorded_at or not self.scope_decision_note:
                raise ValueError("proceeding with open evidence requires a dated decision and note")
            try:
                date.fromisoformat(self.scope_decision_recorded_at)
            except ValueError as error:
                raise ValueError("scope decision date must be ISO formatted") from error

    @property
    def sha256(self) -> str:
        return sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def load_r3_feasibility_config(path: Path) -> R3FeasibilityConfig:
    """Load a unique-key mapping and reject unknown or implicit policy changes."""

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
    content: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    if not isinstance(content, dict):
        raise ValueError("R3.1 feasibility configuration must be a mapping")
    allowed = {item.name for item in fields(R3FeasibilityConfig)}
    if set(content) - allowed:
        raise ValueError("unknown R3.1 feasibility configuration keys")
    if content.get("strategy_version") != "r3.1-feasibility-v1":
        raise ValueError("an explicit R3.1 strategy_version is required")
    return R3FeasibilityConfig(**content)
