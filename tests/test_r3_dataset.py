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
    write_r3_materialization,
)
from src.validation.r3_register import preregister_r3
from src.validation.r3_splits import R3SplitAssignment

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
        preregister_r3(config, timestamp),
        {"contract": "fixture", "counts": {"feature_rows": 1}},
    )

    first = write_r3_materialization(result, tmp_path / "first")
    second = write_r3_materialization(result, tmp_path / "second")

    assert first == second
    report = json.loads((tmp_path / "first/materialization_report.json").read_text())
    assert len(report["dataset_sha256"]) == 64
    assert report["artifact_sha256"]["features"] == first["features"]
