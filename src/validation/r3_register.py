"""Content-bound accessed-data and bounded-trial registration for R3."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal

from src.config.r3 import EXPECTED_CANDIDATES, R3Config


def _canonical_sha(value: object) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode()
    ).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True)
class DataAccessRecord:
    source_id: str
    content_sha256: str
    period_start: str
    period_end: str
    accessed_at: datetime
    purpose: str
    previously_inspected: bool

    def __post_init__(self) -> None:
        if not self.source_id or not self.purpose or not _valid_sha(self.content_sha256):
            raise ValueError("data access requires source, purpose and canonical content hash")
        if self.accessed_at.tzinfo is None:
            raise ValueError("data access timestamp must be timezone-aware")
        if self.period_start > self.period_end:
            raise ValueError("data access period must be ordered")


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    candidate_id: str
    config_sha256: str
    dataset_sha256: str | None
    split_sha256: str | None
    status: Literal["pre_registered", "completed", "failed", "blocked"]
    recorded_at: datetime
    outcome_sha256: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.trial_id or self.recorded_at.tzinfo is None:
            raise ValueError("trial identity and aware timestamp are required")
        if not _valid_sha(self.config_sha256):
            raise ValueError("trial configuration hash must be canonical")
        for value in (self.dataset_sha256, self.split_sha256, self.outcome_sha256):
            if value is not None and not _valid_sha(value):
                raise ValueError("optional trial hashes must be canonical")
        if self.status in ("failed", "blocked") and not self.failure_reason:
            raise ValueError("failed or blocked trials require a reason")
        if self.status == "completed" and self.outcome_sha256 is None:
            raise ValueError("completed trials require a content-bound outcome")


@dataclass(frozen=True)
class LegacyControlRecord:
    candidate_id: Literal["V1", "V2"]
    status: Literal["rejected"]
    report_sha256: str
    inspected_period_start: str
    inspected_period_end: str
    result_summary: str

    def __post_init__(self) -> None:
        if not _valid_sha(self.report_sha256) or not self.result_summary:
            raise ValueError("legacy controls require a report hash and result summary")
        if self.inspected_period_start > self.inspected_period_end:
            raise ValueError("legacy inspected period must be ordered")


@dataclass(frozen=True)
class R3ExperimentRegister:
    registration_version: str
    config_sha256: str
    legacy_controls: tuple[LegacyControlRecord, ...]
    data_accesses: tuple[DataAccessRecord, ...]
    trials: tuple[TrialRecord, ...]

    def __post_init__(self) -> None:
        if self.registration_version != "r3-register-v1" or not _valid_sha(self.config_sha256):
            raise ValueError("invalid R3 register identity")
        trial_ids = tuple(row.trial_id for row in self.trials)
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("trial IDs must be unique; failed trials cannot be overwritten")
        allowed = {row.candidate_id for row in EXPECTED_CANDIDATES}
        if any(row.candidate_id not in allowed for row in self.trials):
            raise ValueError("trial falls outside the bounded six-configuration budget")
        if tuple(row.candidate_id for row in self.legacy_controls) != ("V1", "V2"):
            raise ValueError("the rejected V1/V2 controls must remain in the experiment register")

    @property
    def sha256(self) -> str:
        return _canonical_sha(asdict(self))


def preregister_r3(config: R3Config, recorded_at: datetime) -> R3ExperimentRegister:
    if recorded_at.tzinfo is None:
        raise ValueError("registration timestamp must be timezone-aware")
    trials = tuple(
        TrialRecord(
            f"{candidate.candidate_id}-registered",
            candidate.candidate_id,
            config.sha256,
            None,
            None,
            "pre_registered",
            recorded_at,
        )
        for candidate in config.candidates
    )
    legacy = (
        LegacyControlRecord(
            "V1",
            "rejected",
            "19dbd834da6264650a58120255d649c2575d137a7fa992a4f84a84c0f15c7fdb",
            "2021-07-01",
            "2026-06-30",
            "OOS CAGR -0.17%; Sharpe 0.001; maximum drawdown 15.03%",
        ),
        LegacyControlRecord(
            "V2",
            "rejected",
            "eff58a1d823f5814cb546f3898eddf625ff7000c079c013213db8bc6f13b6db1",
            "2021-07-01",
            "2026-06-30",
            "GBP 3000 CAGR -2.9947%; 49 fills; 23 completed episodes",
        ),
    )
    return R3ExperimentRegister("r3-register-v1", config.sha256, legacy, (), trials)


@dataclass(frozen=True)
class R3Readiness:
    ready: bool
    research_scope: Literal["development_only", "qualification"]
    blockers: tuple[str, ...]
    config_sha256: str
    register_sha256: str


def assess_r3_readiness(config: R3Config, register: R3ExperimentRegister) -> R3Readiness:
    blockers: list[str] = []
    if register.config_sha256 != config.sha256:
        blockers.append("register_config_mismatch")
    registered = tuple(
        row.candidate_id for row in register.trials if row.status == "pre_registered"
    )
    expected = tuple(row.candidate_id for row in config.candidates)
    if registered != expected:
        blockers.append("six_candidate_budget_not_fully_preregistered")
    flags = {
        "r3_1_research_not_accepted": config.r3_1_research_accepted,
        "account_tariff_unverified": config.account_tariff_verified,
        "account_permissions_unverified": config.account_permissions_verified,
        "operating_costs_unverified": config.operating_costs_verified,
        "data_qualification_gaps_open": config.data_qualification_gaps_closed,
    }
    blockers.extend(name for name, satisfied in flags.items() if not satisfied)
    return R3Readiness(
        not blockers,
        "qualification" if not blockers else "development_only",
        tuple(sorted(blockers)),
        config.sha256,
        register.sha256,
    )
