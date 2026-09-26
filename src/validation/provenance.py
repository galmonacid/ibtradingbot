"""Immutable content identity for a native Phase 3 validation run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from src.backtest.costs import CostModel


class ValidationProvenanceError(ValueError):
    """Raised when validation provenance is incomplete or malformed."""


def _sha256(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValidationProvenanceError(f"{field} must be a canonical SHA-256")
    return value


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def cost_model_sha256(costs: CostModel) -> str:
    """Return the canonical identity of one transaction-cost model."""
    return _digest(asdict(costs))


def session_list_sha256(sessions: tuple[date, ...]) -> str:
    """Return the canonical identity of a sorted exchange-session sequence."""
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValidationProvenanceError("sessions must be non-empty, sorted, and unique")
    return hashlib.sha256(
        "".join(f"{session.isoformat()}\n" for session in sessions).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ValidationRunIdentity:
    canonical_manifest_sha256: str
    config_sha256: str
    strategy_version: str
    strategy_definition_sha256: str
    baseline_cost_sha256: str
    stressed_cost_sha256: str
    calendar_sessions_sha256: str
    validation_spec_sha256: str
    dataset_evidence_sha256: str | None
    universe_policy_sha256: str | None
    git_revision: str
    git_dirty: bool
    validation_run_id: str

    def __post_init__(self) -> None:
        for field in (
            "canonical_manifest_sha256",
            "config_sha256",
            "strategy_definition_sha256",
            "baseline_cost_sha256",
            "stressed_cost_sha256",
            "calendar_sessions_sha256",
            "validation_spec_sha256",
            "validation_run_id",
        ):
            _sha256(str(getattr(self, field)), field)
        for field in ("dataset_evidence_sha256", "universe_policy_sha256"):
            value = getattr(self, field)
            if value is not None:
                _sha256(value, field)
        if not self.strategy_version.strip():
            raise ValidationProvenanceError("strategy_version must be non-blank")
        if len(self.git_revision) != 40 or any(
            character not in "0123456789abcdef" for character in self.git_revision
        ):
            raise ValidationProvenanceError("git_revision must be a canonical commit SHA")
        if not isinstance(self.git_dirty, bool):
            raise ValidationProvenanceError("git_dirty must be boolean")
        expected = _digest(
            {
                "baseline_cost_sha256": self.baseline_cost_sha256,
                "calendar_sessions_sha256": self.calendar_sessions_sha256,
                "canonical_manifest_sha256": self.canonical_manifest_sha256,
                "config_sha256": self.config_sha256,
                "git_dirty": self.git_dirty,
                "git_revision": self.git_revision,
                "strategy_version": self.strategy_version,
                "strategy_definition_sha256": self.strategy_definition_sha256,
                "stressed_cost_sha256": self.stressed_cost_sha256,
                "validation_spec_sha256": self.validation_spec_sha256,
                "dataset_evidence_sha256": self.dataset_evidence_sha256,
                "universe_policy_sha256": self.universe_policy_sha256,
            }
        )
        if self.validation_run_id != expected:
            raise ValidationProvenanceError("validation_run_id does not match its bound inputs")


def create_validation_run_identity(
    *,
    canonical_manifest_sha256: str,
    config_sha256: str,
    strategy_version: str,
    strategy_definition_sha256: str,
    baseline_costs: CostModel,
    stressed_costs: CostModel,
    calendar_sessions_sha256: str,
    validation_spec_sha256: str,
    git_revision: str,
    git_dirty: bool,
    dataset_evidence_sha256: str | None = None,
    universe_policy_sha256: str | None = None,
) -> ValidationRunIdentity:
    """Issue a deterministic parent identity shared by every native run scenario."""
    baseline_cost_sha256 = cost_model_sha256(baseline_costs)
    stressed_cost_sha256 = cost_model_sha256(stressed_costs)
    values = {
        "canonical_manifest_sha256": _sha256(
            canonical_manifest_sha256, "canonical_manifest_sha256"
        ),
        "config_sha256": _sha256(config_sha256, "config_sha256"),
        "strategy_version": strategy_version,
        "strategy_definition_sha256": _sha256(
            strategy_definition_sha256, "strategy_definition_sha256"
        ),
        "baseline_cost_sha256": baseline_cost_sha256,
        "stressed_cost_sha256": stressed_cost_sha256,
        "calendar_sessions_sha256": _sha256(calendar_sessions_sha256, "calendar_sessions_sha256"),
        "validation_spec_sha256": _sha256(validation_spec_sha256, "validation_spec_sha256"),
        "dataset_evidence_sha256": (
            None
            if dataset_evidence_sha256 is None
            else _sha256(dataset_evidence_sha256, "dataset_evidence_sha256")
        ),
        "universe_policy_sha256": (
            None
            if universe_policy_sha256 is None
            else _sha256(universe_policy_sha256, "universe_policy_sha256")
        ),
        "git_revision": git_revision,
        "git_dirty": git_dirty,
    }
    return ValidationRunIdentity(
        canonical_manifest_sha256=str(values["canonical_manifest_sha256"]),
        config_sha256=str(values["config_sha256"]),
        strategy_version=strategy_version,
        strategy_definition_sha256=str(values["strategy_definition_sha256"]),
        baseline_cost_sha256=baseline_cost_sha256,
        stressed_cost_sha256=stressed_cost_sha256,
        calendar_sessions_sha256=str(values["calendar_sessions_sha256"]),
        validation_spec_sha256=str(values["validation_spec_sha256"]),
        dataset_evidence_sha256=dataset_evidence_sha256,
        universe_policy_sha256=universe_policy_sha256,
        git_revision=git_revision,
        git_dirty=git_dirty,
        validation_run_id=_digest(values),
    )
