"""Strict, versioned configuration for the R3 research contract.

This module registers the bounded experiment.  It deliberately contains no
model fitting or broker behavior; those belong to later roadmap phases.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import yaml

CandidateFamily = Literal["momentum", "ridge", "hist_gradient_boosting"]
R3ScopeDecision = Literal["proceed_with_open_label_evidence"]


@dataclass(frozen=True)
class CandidateConfig:
    candidate_id: str
    family: CandidateFamily
    alpha: float | None = None
    max_leaf_nodes: int | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must be non-blank")
        if self.family == "momentum":
            if self.alpha is not None or self.max_leaf_nodes is not None:
                raise ValueError("momentum has no learned hyperparameters")
        elif self.family == "ridge":
            if self.alpha not in (1.0, 10.0, 100.0) or self.max_leaf_nodes is not None:
                raise ValueError("ridge alpha must be one of the registered values")
        elif self.family == "hist_gradient_boosting":
            if self.max_leaf_nodes not in (7, 15) or self.alpha is not None:
                raise ValueError("tree leaf count must be one of the registered values")
        else:
            raise ValueError("unknown R3 candidate family")


@dataclass(frozen=True)
class SensitivityConfig:
    sensitivity_id: str
    axis: Literal[
        "target_positions", "volatility_ceiling", "market_sma_sessions", "liquidity_min_usd"
    ]
    value: int | float


EXPECTED_CANDIDATES = (
    CandidateConfig("R3-M", "momentum"),
    CandidateConfig("R3-L-a1", "ridge", alpha=1.0),
    CandidateConfig("R3-L-a10", "ridge", alpha=10.0),
    CandidateConfig("R3-L-a100", "ridge", alpha=100.0),
    CandidateConfig("R3-T-l7", "hist_gradient_boosting", max_leaf_nodes=7),
    CandidateConfig("R3-T-l15", "hist_gradient_boosting", max_leaf_nodes=15),
)

EXPECTED_SENSITIVITIES = (
    SensitivityConfig("positions-3", "target_positions", 3),
    SensitivityConfig("positions-5", "target_positions", 5),
    SensitivityConfig("volatility-10pct", "volatility_ceiling", 0.10),
    SensitivityConfig("volatility-14pct", "volatility_ceiling", 0.14),
    SensitivityConfig("market-sma-160", "market_sma_sessions", 160),
    SensitivityConfig("market-sma-240", "market_sma_sessions", 240),
    SensitivityConfig("liquidity-10m", "liquidity_min_usd", 10_000_000.0),
    SensitivityConfig("liquidity-50m", "liquidity_min_usd", 50_000_000.0),
)


@dataclass(frozen=True)
class R3Config:
    strategy_version: str
    initial_capital_gbp: float
    target_profit_gbp: float
    target_return: float
    target_positions: int
    incumbent_rank: int
    max_holdings: int
    cash_buffer: float
    max_position_weight: float
    soft_drawdown: float
    hard_drawdown: float
    soft_position_weight: float
    volatility_ceiling: float
    resize_band: float
    minimum_price_usd: float
    liquidity_min_usd: float
    capacity_fraction: float
    round_trip_cost_ceiling: float
    market_sma_sessions: int
    feature_version: str
    label_version: str
    transform_version: str
    seed: int
    initial_train_years: int
    validation_years: int
    test_years: int
    step_years: int
    purge_sessions: int
    refit_months: int
    max_fx_age_days: int
    candidates: tuple[CandidateConfig, ...]
    sensitivities: tuple[SensitivityConfig, ...]
    r3_1_phase_closed: bool
    r3_1_research_accepted: bool
    account_tariff_verified: bool
    account_permissions_verified: bool
    operating_costs_verified: bool
    data_qualification_gaps_closed: bool
    r3_2_scope_decision: R3ScopeDecision
    r3_2_scope_decision_recorded_at: str
    r3_2_scope_decision_note: str

    def __post_init__(self) -> None:
        if self.strategy_version != "r3.2-contract-v1":
            raise ValueError("strategy_version must identify the R3.2 contract")
        fixed: dict[str, int | float] = {
            "initial_capital_gbp": 3000.0,
            "target_profit_gbp": 300.0,
            "target_return": 0.10,
            "target_positions": 4,
            "incumbent_rank": 8,
            "max_holdings": 5,
            "cash_buffer": 0.02,
            "max_position_weight": 0.30,
            "soft_drawdown": 0.10,
            "hard_drawdown": 0.15,
            "soft_position_weight": 0.15,
            "volatility_ceiling": 0.12,
            "resize_band": 0.03,
            "minimum_price_usd": 10.0,
            "liquidity_min_usd": 20_000_000.0,
            "capacity_fraction": 0.0001,
            "round_trip_cost_ceiling": 0.01,
            "market_sma_sessions": 200,
            "seed": 20260926,
            "initial_train_years": 8,
            "validation_years": 2,
            "test_years": 1,
            "step_years": 1,
            "purge_sessions": 31,
            "refit_months": 3,
            "max_fx_age_days": 6,
        }
        for name, expected in fixed.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} must retain the registered R3 value {expected}")
        if not all((self.feature_version, self.label_version, self.transform_version)):
            raise ValueError("feature, label and transform versions are required")
        if self.candidates != EXPECTED_CANDIDATES:
            raise ValueError("R3 requires exactly the six ordered candidate configurations")
        if self.sensitivities != EXPECTED_SENSITIVITIES:
            raise ValueError("R3 requires exactly the eight ordered sensitivity neighbors")
        for name in (
            "r3_1_phase_closed",
            "r3_1_research_accepted",
            "account_tariff_verified",
            "account_permissions_verified",
            "operating_costs_verified",
            "data_qualification_gaps_closed",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        if not self.r3_1_phase_closed:
            raise ValueError("R3.2 cannot start until R3.1 is explicitly closed")
        if self.r3_2_scope_decision != "proceed_with_open_label_evidence":
            raise ValueError("R3.2 scope decision must preserve the open label evidence")
        if self.r3_2_scope_decision_recorded_at != "2026-09-28":
            raise ValueError("R3.2 scope decision date must be 2026-09-28")
        if not self.r3_2_scope_decision_note.strip():
            raise ValueError("R3.2 scope decision note must be non-blank")

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return sha256(payload).hexdigest()


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate configuration key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return float(value)


def load_r3_config(path: Path) -> R3Config:
    content: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(content, dict):
        raise ValueError("R3 configuration must be a mapping")
    expected_keys = set(R3Config.__dataclass_fields__)
    if set(content) != expected_keys:
        missing = sorted(expected_keys - set(content))
        extra = sorted(set(content) - expected_keys)
        raise ValueError(f"R3 configuration keys mismatch; missing={missing}, extra={extra}")
    candidate_rows = content.pop("candidates")
    sensitivity_rows = content.pop("sensitivities")
    if not isinstance(candidate_rows, list) or not isinstance(sensitivity_rows, list):
        raise ValueError("candidates and sensitivities must be lists")
    candidates = tuple(CandidateConfig(**row) for row in candidate_rows)
    sensitivities = tuple(SensitivityConfig(**row) for row in sensitivity_rows)
    for field in (
        "initial_capital_gbp",
        "target_profit_gbp",
        "target_return",
        "cash_buffer",
        "max_position_weight",
        "soft_drawdown",
        "hard_drawdown",
        "soft_position_weight",
        "volatility_ceiling",
        "resize_band",
        "minimum_price_usd",
        "liquidity_min_usd",
        "capacity_fraction",
        "round_trip_cost_ceiling",
    ):
        content[field] = _finite_number(content[field], field)
    return R3Config(**content, candidates=candidates, sensitivities=sensitivities)
