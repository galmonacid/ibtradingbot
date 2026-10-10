"""Strict configuration for the R3 Step 3 source-feasibility audit."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SourceSample:
    cik: str
    issuer: str
    cases: tuple[str, ...]
    security_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.cik) != 10 or not self.cik.isdigit():
            raise ValueError("sample CIKs must be ten digits")
        if not self.issuer or not self.cases or not self.security_ids:
            raise ValueError("sample issuer, cases and security identities are required")


@dataclass(frozen=True)
class R3Step3Config:
    contract_version: str
    run_timestamp: str
    sample_seed: int
    processing_latency_hours: int
    required_protocol_folds: int
    initial_train_years: int
    validation_years: int
    test_years: int
    step_years: int
    purge_sessions: int
    source_request_limit: int
    sec_user_agent: str
    corrected_dataset_identity: str
    corrected_scoring_sha256: str
    corrected_report_sha256: str
    sample: tuple[SourceSample, ...]

    def __post_init__(self) -> None:
        if self.contract_version != "r3-step3-source-feasibility-v1":
            raise ValueError("unexpected Step 3 contract version")
        parsed = datetime.fromisoformat(self.run_timestamp)
        if parsed.tzinfo is None:
            raise ValueError("run timestamp must be timezone-aware")
        fixed = {
            "sample_seed": 20261002,
            "processing_latency_hours": 24,
            "required_protocol_folds": 9,
            "initial_train_years": 8,
            "validation_years": 2,
            "test_years": 1,
            "step_years": 1,
            "purge_sessions": 31,
        }
        for name, value in fixed.items():
            if getattr(self, name) != value:
                raise ValueError(f"{name} must remain frozen at {value}")
        if not 1 <= self.source_request_limit <= 64:
            raise ValueError("source request limit must remain bounded")
        if len(self.sample) != 11 or len({row.cik for row in self.sample}) != 11:
            raise ValueError("Step 3 requires the frozen eleven-issuer sample")
        for digest in (
            self.corrected_dataset_identity,
            self.corrected_scoring_sha256,
            self.corrected_report_sha256,
        ):
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("preserved evidence identities must be SHA-256 values")

    @property
    def sha256(self) -> str:
        return sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


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


def load_r3_step3_config(path: Path) -> R3Step3Config:
    raw: object = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(raw, dict):
        raise ValueError("Step 3 configuration must be a mapping")
    expected = set(R3Step3Config.__dataclass_fields__)
    if set(raw) != expected:
        raise ValueError("Step 3 configuration keys do not match the frozen schema")
    sample = raw.pop("sample")
    if not isinstance(sample, list):
        raise ValueError("sample must be a list")
    rows = tuple(
        SourceSample(
            cik=str(row["cik"]),
            issuer=str(row["issuer"]),
            cases=tuple(str(value) for value in row["cases"]),
            security_ids=tuple(str(value) for value in row["security_ids"]),
        )
        for row in sample
    )
    return R3Step3Config(**raw, sample=rows)
