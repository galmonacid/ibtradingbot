from dataclasses import replace
from datetime import date

import pytest

from src.backtest.costs import CostModel
from src.validation.provenance import (
    ValidationProvenanceError,
    create_validation_run_identity,
    session_list_sha256,
)


def test_validation_run_identity_is_deterministic_and_binds_every_input() -> None:
    values = {
        "canonical_manifest_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "strategy_version": "phase3-v1",
        "strategy_definition_sha256": "e" * 64,
        "baseline_costs": CostModel(0.35, 5.0, 5.0),
        "stressed_costs": CostModel(0.70, 10.0, 5.0),
        "calendar_sessions_sha256": session_list_sha256((date(2020, 1, 2), date(2020, 1, 3))),
        "validation_spec_sha256": "c" * 64,
        "git_revision": "d" * 40,
        "git_dirty": False,
        "dataset_evidence_sha256": "f" * 64,
        "universe_policy_sha256": "1" * 64,
    }
    first = create_validation_run_identity(**values)  # type: ignore[arg-type]
    second = create_validation_run_identity(**values)  # type: ignore[arg-type]

    assert first == second
    assert len(first.validation_run_id) == 64
    with pytest.raises(ValidationProvenanceError, match="does not match"):
        replace(first, config_sha256="e" * 64)
    with pytest.raises(ValidationProvenanceError, match="does not match"):
        replace(first, universe_policy_sha256="2" * 64)


def test_session_identity_rejects_noncanonical_sequences() -> None:
    with pytest.raises(ValidationProvenanceError, match="sorted"):
        session_list_sha256((date(2020, 1, 3), date(2020, 1, 2)))
