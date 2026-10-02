from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.config.r3 import CandidateConfig
from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import LearningObservation, fit_r3_model, rank_scores


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

