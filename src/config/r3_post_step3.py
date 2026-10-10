"""Frozen configuration for the post-Step-3 governance decision package."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True)
class R3PostStep3Config:
    contract_version: str
    run_timestamp: str
    seed: int
    step3_directory: str
    step3_package_identity: str
    step3_failure_register_sha256: str
    corrected_dataset_directory: str
    corrected_dataset_identity: str
    corrected_scoring_sha256: str
    corrected_run_directory: str
    corrected_report_sha256: str
    preserved_r3_3_directory: str
    preserved_r3_3_report_sha256: str
    preserved_r3_3_register_sha256: str
    preserved_r3_3_model_manifest_sha256: str
    price_only_start: str
    sec_sample_start: str
    required_protocol_folds: int
    initial_train_years: int
    validation_years: int
    test_years: int
    step_years: int
    purge_sessions: int
    protocol_amendment_authorized: bool
    step4_authorized: bool

    def __post_init__(self) -> None:
        if self.contract_version != "r3-post-step3-remediation-decision-v1":
            raise ValueError("unexpected post-Step-3 contract version")
        if datetime.fromisoformat(self.run_timestamp).tzinfo is None:
            raise ValueError("run timestamp must be timezone-aware")
        if self.seed != 20261003:
            raise ValueError("decision-package seed is frozen")
        fixed = {
            "required_protocol_folds": 9,
            "initial_train_years": 8,
            "validation_years": 2,
            "test_years": 1,
            "step_years": 1,
            "purge_sessions": 31,
        }
        for name, expected in fixed.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} must remain frozen at {expected}")
        if self.protocol_amendment_authorized or self.step4_authorized:
            raise ValueError("this contract cannot authorize a protocol amendment or Step 4")
        if date.fromisoformat(self.price_only_start) != date(1999, 1, 29):
            raise ValueError("price-only protocol start cannot change")
        if date.fromisoformat(self.sec_sample_start) != date(2009, 7, 23):
            raise ValueError("Step 3 SEC sample start cannot change")
        digests = (
            self.step3_package_identity,
            self.step3_failure_register_sha256,
            self.corrected_dataset_identity,
            self.corrected_scoring_sha256,
            self.corrected_report_sha256,
            self.preserved_r3_3_report_sha256,
            self.preserved_r3_3_register_sha256,
            self.preserved_r3_3_model_manifest_sha256,
        )
        if not all(_is_sha256(value) for value in digests):
            raise ValueError("all preserved evidence identities must be SHA-256 values")

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate configuration key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_r3_post_step3_config(path: Path) -> R3PostStep3Config:
    raw: object = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(raw, dict):
        raise ValueError("post-Step-3 configuration must be a mapping")
    expected = set(R3PostStep3Config.__dataclass_fields__)
    if set(raw) != expected:
        raise ValueError("post-Step-3 configuration keys do not match the frozen schema")
    return R3PostStep3Config(**raw)
