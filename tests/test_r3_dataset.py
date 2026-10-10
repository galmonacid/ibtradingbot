from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.config.r3 import load_r3_config
from src.features.r3 import R3FeatureRow, R3Label
from src.research.r3_dataset import (
    R3Materialization,
    _development_training_blockers,
    _label_coverage,
    write_r3_materialization,
)
from src.research.r3_development import load_r3_development_dataset
from src.validation.r3_register import preregister_r3
from src.validation.r3_splits import R3ScoringAssignment, R3SplitAssignment

ROOT = Path(__file__).parents[1]


def test_scope_decision_preserves_nonwaivable_training_gates() -> None:
    evidence = ["cash_action_labels_unresolved", "fx_not_vintage_certified"]

    assert (
        _development_training_blockers(
            evidence,
            protocol_ready_folds=(0,),
            outcome_conditioned_cash_action_rows_dropped=0,
            scope_override=True,
        )
        == []
    )
    assert set(
        _development_training_blockers(
            evidence,
            protocol_ready_folds=(),
            outcome_conditioned_cash_action_rows_dropped=1,
            scope_override=True,
        )
    ) == {
        "no_protocol_ready_8y_2y_1y_fold",
        "outcome_conditioned_cash_action_rows_omitted",
    }


def test_materialization_artifacts_are_byte_reproducible(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    timestamp = datetime(2026, 9, 27, 16, tzinfo=UTC)
    config = load_r3_config(ROOT / "config.r3.yaml")
    feature = R3FeatureRow(
        "AAA",
        date(2024, 1, 31),
        timestamp,
        timestamp,
        date(2020, 1, 1),
        None,
        "raw-v1",
        "adjusted-v1",
        tuple(float(index) for index in range(12)),
        (),
        config.feature_version,
    )
    label = R3Label(
        "AAA",
        date(2024, 1, 31),
        timestamp,
        timestamp,
        timestamp,
        0.01,
        None,
        config.label_version,
    )
    result = R3Materialization(
        (feature,),
        (label,),
        (R3SplitAssignment("AAA", date(2024, 1, 31), 0, "train"),),
        (R3ScoringAssignment("AAA", date(2024, 1, 31), 0, "train"),),
        preregister_r3(config, timestamp),
        {"contract": "fixture", "counts": {"feature_rows": 1}},
    )

    first = write_r3_materialization(result, tmp_path / "first")
    second = write_r3_materialization(result, tmp_path / "second")

    assert first == second
    report = json.loads((tmp_path / "first/materialization_report.json").read_text())
    assert len(report["dataset_sha256"]) == 64
    assert report["artifact_sha256"]["features"] == first["features"]
    assert report["artifact_sha256"]["scoring"] == first["scoring"]

    with pytest.raises(FileExistsError, match="refusing to overwrite immutable dataset"):
        write_r3_materialization(result, tmp_path / "first")


def test_loader_keeps_unresolved_label_row_in_scoring_universe(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    timestamp = datetime(2026, 9, 27, 16, tzinfo=UTC)
    decision = date(2024, 1, 31)
    config = load_r3_config(ROOT / "config.r3.yaml")

    def feature(security_id: str) -> R3FeatureRow:
        return R3FeatureRow(
            security_id,
            decision,
            timestamp,
            timestamp,
            date(2020, 1, 1),
            None,
            "raw-v1",
            "adjusted-v1",
            tuple(float(index) for index in range(12)),
            (),
            config.feature_version,
        )

    matured = R3Label(
        "MATURED",
        decision,
        timestamp,
        timestamp,
        timestamp,
        0.01,
        None,
        config.label_version,
    )
    unresolved = R3Label(
        "UNRESOLVED",
        decision,
        timestamp,
        timestamp,
        None,
        None,
        "future outcome unavailable",
        config.label_version,
    )
    result = R3Materialization(
        (feature("MATURED"), feature("UNRESOLVED")),
        (matured, unresolved),
        (R3SplitAssignment("MATURED", decision, 0, "test"),),
        (
            R3ScoringAssignment("MATURED", decision, 0, "test"),
            R3ScoringAssignment("UNRESOLVED", decision, 0, "test"),
        ),
        preregister_r3(config, timestamp),
        {
            "contract": "r3.2-development-dataset-v2-label-independent-scoring",
            "r3_3_development_training_permitted": True,
            "r3_2_phase_closed": True,
            "qualification_permitted": False,
            "counts": {
                "outcome_conditioned_cash_action_rows_dropped_from_label_artifact": 0
            },
            "protocol_ready_fold_ids": [0],
            "evidence_limitations": ["synthetic_fixture_only"],
            "config_sha256": config.sha256,
        },
    )
    output = tmp_path / "corrected"
    write_r3_materialization(result, output)

    loaded = load_r3_development_dataset(output)

    assert loaded.split_keys[(0, "test")] == frozenset({("MATURED", decision)})
    assert loaded.scoring_keys[(0, "test")] == frozenset(
        {("MATURED", decision), ("UNRESOLVED", decision)}
    )


def test_label_coverage_reports_unresolved_rows_without_sector_invention() -> None:
    timestamp = datetime(2026, 9, 27, 16, tzinfo=UTC)
    matured = R3Label(
        "AAA",
        date(2024, 1, 31),
        timestamp,
        timestamp,
        timestamp,
        0.01,
        None,
        "label-v1",
    )
    unresolved = R3Label(
        "BBB",
        date(2024, 1, 31),
        timestamp,
        timestamp,
        None,
        None,
        "unresolved",
        "label-v1",
    )

    coverage = _label_coverage((matured, unresolved), (), as_of=timestamp)

    assert coverage["by_decision_date"] == {
        "2024-01-31": {"available": 1, "total": 2, "unresolved": 1}
    }
    assert coverage["sector_status"] == "unavailable_no_point_in_time_sector_metadata"
