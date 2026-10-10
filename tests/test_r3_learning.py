from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.config.r3 import CandidateConfig, load_r3_config
from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import LearningObservation, fit_r3_model, rank_scores
from src.research.r3_development import (
    R3DevelopmentDataset,
    R3DevelopmentRun,
    _score_segment,
    write_r3_development,
)


def _observation(
    security_id: str,
    day: date,
    target: float,
    *,
    available_days_later: int = 31,
) -> LearningObservation:
    values = tuple((index + 1) * target for index in range(len(R3_FEATURE_NAMES)))
    return LearningObservation(
        security_id,
        day,
        datetime.combine(day, datetime.min.time(), UTC)
        + timedelta(days=available_days_later),
        values,
        target,
    )


def test_ridge_uses_only_matured_rows_and_is_deterministic() -> None:
    start = date(2020, 1, 31)
    rows = tuple(
        _observation(f"S{index % 3}", start + timedelta(days=31 * index), index / 100)
        for index in range(12)
    )
    cutoff = datetime(2020, 10, 1, tzinfo=UTC)
    candidate = CandidateConfig("R3-L-a10", "ridge", alpha=10.0)
    left = fit_r3_model(candidate, rows, training_cutoff=cutoff, fitted_at=cutoff)
    right = fit_r3_model(candidate, rows, training_cutoff=cutoff, fitted_at=cutoff)
    assert left.training_rows < len(rows)
    assert left.training_dates == left.training_rows
    assert left.estimator_sha256 == right.estimator_sha256
    scoring = (_observation("B", date(2021, 1, 1), 0.2), _observation("A", date(2021, 1, 1), 0.1))
    assert left.score(scoring) == right.score(scoring)


@pytest.mark.parametrize(
    "candidate",
    [
        CandidateConfig("R3-T-l7", "hist_gradient_boosting", max_leaf_nodes=7),
        CandidateConfig("R3-T-l15", "hist_gradient_boosting", max_leaf_nodes=15),
    ],
)
def test_histogram_gradient_boosting_has_registered_shallow_variants(
    candidate: CandidateConfig,
) -> None:
    start = date(2018, 1, 31)
    rows = tuple(
        _observation(f"S{index % 20:02d}", start + timedelta(days=index), (index % 11) / 100)
        for index in range(240)
    )
    cutoff = datetime(2020, 1, 1, tzinfo=UTC)
    model = fit_r3_model(candidate, rows, training_cutoff=cutoff, fitted_at=cutoff)
    assert model.training_rows == len(rows)
    assert len(model.score(rows[:3])) == 3


def test_momentum_control_and_tie_break_need_no_fit() -> None:
    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    model = fit_r3_model(
        CandidateConfig("R3-M", "momentum"), (), training_cutoff=cutoff, fitted_at=cutoff
    )
    left = _observation("B", date(2024, 1, 31), 1.0)
    right = _observation("A", date(2024, 1, 31), 1.0)
    scores = model.score((left, right))
    assert rank_scores(scores) == ("A", "B")


def test_future_label_mutation_cannot_change_fitted_model() -> None:
    cutoff = datetime(2020, 6, 1, tzinfo=UTC)
    matured = _observation("A", date(2020, 1, 1), 0.1)
    future = _observation("B", date(2020, 5, 1), 0.2, available_days_later=365)
    mutated = LearningObservation(
        future.security_id,
        future.decision_date,
        future.label_available_at,
        future.features,
        99.0,
    )
    candidate = CandidateConfig("R3-L-a1", "ridge", alpha=1.0)
    left = fit_r3_model(candidate, (matured, future), training_cutoff=cutoff, fitted_at=cutoff)
    right = fit_r3_model(candidate, (matured, mutated), training_cutoff=cutoff, fitted_at=cutoff)
    assert left.estimator_sha256 == right.estimator_sha256


def test_refits_add_only_labels_matured_by_each_cutoff() -> None:
    config = load_r3_config(__import__("pathlib").Path("config.r3.yaml"))
    candidate = CandidateConfig("R3-L-a1", "ridge", alpha=1.0)
    training = (
        _observation("A", date(2019, 1, 31), 0.1),
        _observation("B", date(2019, 1, 31), 0.2),
    )
    january = _observation("A", date(2020, 1, 31), 0.3)
    april = _observation("A", date(2020, 4, 30), 0.4, available_days_later=365)
    july = _observation("A", date(2020, 7, 31), 0.5, available_days_later=365)
    observations = training + (january, april, july)
    training_keys = frozenset((row.security_id, row.decision_date) for row in training)
    score_keys = frozenset(
        (row.security_id, row.decision_date) for row in (january, april, july)
    )
    dataset = R3DevelopmentDataset(
        observations=observations,
        split_keys={(0, "train"): training_keys},
        scoring_keys={(0, "validation"): score_keys},
        ready_folds=(0,),
        dataset_sha256="d" * 64,
        split_sha256="s" * 64,
        scoring_sha256="e" * 64,
        evidence_limitations=(),
        config_sha256=config.sha256,
    )

    _, models = _score_segment(
        candidate,
        dataset,
        training_keys=training_keys,
        score_keys=score_keys,
        config=config,
    )

    assert [model.training_rows for model in models] == [2, 3, 3]


def test_development_writer_refuses_existing_evidence_directory(tmp_path: object) -> None:
    from pathlib import Path

    output = Path(str(tmp_path)) / "preserved"
    output.mkdir()
    run = R3DevelopmentRun({}, {}, (), ())

    with pytest.raises(FileExistsError, match="refusing to overwrite immutable development"):
        write_r3_development(run, output)
