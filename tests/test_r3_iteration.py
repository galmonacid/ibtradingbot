from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import LearningObservation
from src.learning.r3_iteration import fit_iteration_model
from src.research.r3_iteration import (
    load_config,
    monthly_diagnostic,
    paired_month,
    purged_training,
    rank_ic,
    write_json,
)


def observation(name: str, day: date, value: float | None) -> LearningObservation:
    return LearningObservation(
        name,
        day,
        None
        if value is None
        else datetime.combine(day, datetime.min.time(), UTC) + timedelta(days=31),
        tuple(index / 100 for index in range(len(R3_FEATURE_NAMES))),
        value,
    )


def test_selection_retains_missing_outcomes_and_is_invariant_to_labels() -> None:
    rows = [observation("A", date(2020, 1, 31), None), observation("B", date(2020, 1, 31), 0.1)]
    result = monthly_diagnostic(rows, [2.0, 1.0], top_k=1)
    assert result["selected_ids"] == ["A"]
    assert result["selected_missing"] == 1
    assert result["top_mean_excess_if_complete"] is None
    changed = [observation("A", date(2020, 1, 31), -99.0), rows[1]]
    assert monthly_diagnostic(changed, [2.0, 1.0], top_k=1)["selected_ids"] == ["A"]


def test_pair_cancels_common_missing_picks_but_retains_differential_uncertainty() -> None:
    rows = [
        observation("A", date(2020, 1, 31), None),
        observation("B", date(2020, 1, 31), 0.1),
        observation("C", date(2020, 1, 31), None),
    ]
    left = monthly_diagnostic(rows, [3.0, 2.0, 1.0], top_k=2)
    right = monthly_diagnostic(rows, [3.0, 1.0, 2.0], top_k=2)
    pair = paired_month(left, right, scenarios=[-0.1, 0.1], drags=[0, 50])
    assert pair["known_contribution"] == pytest.approx(0.05)
    assert pair["missing_absolute_weight"] == 0.5
    assert pair["paired_excess_if_resolved"] is None
    assert pair["common_missing_value_break_even"] == pytest.approx(0.1)
    assert pair["scenarios_not_bounds"][-1]["paired_excess"] == pytest.approx(-0.005)
    same = paired_month(left, left, scenarios=[0.1], drags=[0])
    assert same["paired_excess_if_resolved"] == 0


def test_purge_checks_exit_maturity_and_period_origin() -> None:
    sessions = tuple(date(2020, 1, 1) + timedelta(days=i) for i in range(100))
    boundary = sessions[80]
    cutoff = datetime.combine(boundary, datetime.min.time(), UTC)
    good = observation("good", sessions[0], 0.1)
    overlap = observation("overlap", sessions[10], 0.1)
    late = replace(good, security_id="late", label_available_at=cutoff)
    old = observation("old", date(2019, 1, 1), 0.1)
    exits = {
        (row.security_id, row.decision_date): datetime.combine(
            sessions[49] if row.security_id == "overlap" else sessions[48], datetime.min.time(), UTC
        )
        for row in (good, overlap, late, old)
    }
    assert purged_training((good, overlap, late, old), exits, sessions, boundary, cutoff) == (good,)


@pytest.mark.parametrize("family", ["ridge", "xgboost"])
def test_training_and_predictions_ignore_future_labels_and_reproduce(family: str) -> None:
    if family == "xgboost":
        pytest.importorskip("xgboost")
    config = load_config(Path("config.r3-iteration.yaml"))
    rows = [
        replace(
            observation(f"S{i}", date(2019, 1, 31), i / 100),
            features=tuple(i * (j + 1) / 100 for j in range(len(R3_FEATURE_NAMES))),
        )
        for i in range(40)
    ]
    future = observation("future", date(2021, 1, 31), 0.3)
    cutoff = datetime(2020, 1, 1, tzinfo=UTC)
    kwargs = dict(
        ridge_alpha=config["ridge_alpha"], xgboost_parameters=config["xgboost"], seed=config["seed"]
    )
    left = fit_iteration_model(family, [*rows, future], cutoff, **kwargs)
    right = fit_iteration_model(family, [*rows, replace(future, target=99)], cutoff, **kwargs)
    assert left.training_rows == 40
    assert left.manifest()["model_sha256"] == right.manifest()["model_sha256"]
    assert left.score([future]) == right.score([replace(future, target=-99)])
    if family == "ridge":
        assert left.scaler.mean_[0] == pytest.approx(0.195)
    else:
        assert left.estimator.get_params()["n_jobs"] == 1
        assert left.estimator.get_params()["max_depth"] == 3


def test_rank_ic_ties_and_constant_prediction() -> None:
    assert rank_ic([1, 1, 3], [2, 2, 4]) == pytest.approx(1)
    assert rank_ic([1, 1, 1], [2, 3, 4]) is None


def test_immutable_output_and_invalid_configuration(tmp_path: Path) -> None:
    path = tmp_path / "register.json"
    write_json(path, {"registered": True})
    with pytest.raises(FileExistsError):
        write_json(path, {"registered": False})
    config = tmp_path / "config.yaml"
    config.write_text(Path("config.r3-iteration.yaml").read_text() + "seed: 7\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_config(config)


def test_unknown_model_never_falls_back() -> None:
    with pytest.raises(ValueError, match="unregistered"):
        fit_iteration_model(
            "other", [], datetime.now(UTC), ridge_alpha=10, xgboost_parameters={}, seed=1
        )
