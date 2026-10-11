"""Separate, fixed-budget Momentum/Ridge/XGBoost diagnostic learners."""

from __future__ import annotations

import hashlib
import pickle
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import LearningObservation


@dataclass(frozen=True)
class IterationModel:
    family: str
    estimator: Any
    scaler: Any
    training_rows: int
    training_dates: int
    cutoff: datetime

    def score(self, rows: Sequence[LearningObservation]) -> list[float]:
        import numpy as np

        if not rows:
            return []
        if self.family == "momentum":
            index = R3_FEATURE_NAMES.index("momentum_252_skip21")
            return [row.features[index] for row in rows]
        matrix = np.asarray([row.features for row in rows], dtype=float)
        if self.scaler is not None:
            matrix = self.scaler.transform(matrix)
        scores = [float(value) for value in self.estimator.predict(matrix)]
        if len(scores) != len(rows) or not all(np.isfinite(scores)):
            raise ValueError("non-finite or incomplete model output")
        return scores

    def payload(self) -> bytes:
        return pickle.dumps(self, protocol=5)

    def manifest(self) -> dict[str, object]:
        return {
            "family": self.family,
            "training_rows": self.training_rows,
            "training_dates": self.training_dates,
            "training_cutoff": self.cutoff.isoformat(),
            "feature_names": R3_FEATURE_NAMES,
            "model_sha256": hashlib.sha256(self.payload()).hexdigest(),
            "weights": "equal total per date, normalized to mean row weight 1",
        }


def fit_iteration_model(
    family: str,
    observations: Sequence[LearningObservation],
    cutoff: datetime,
    *,
    ridge_alpha: float,
    xgboost_parameters: dict[str, int | float],
    seed: int,
) -> IterationModel:
    """Fit a purged input set; recheck label maturity at the fit boundary.

    Mean-one row weights preserve equal total weight per date and give XGBoost's
    Hessian/regularization parameters an explicit scale. Legacy R3 is unchanged.
    """
    if cutoff.utcoffset() is None:
        raise ValueError("aware training cutoff required")
    if family not in ("momentum", "ridge", "xgboost"):
        raise ValueError("unregistered model family")
    if family == "momentum":
        return IterationModel(family, None, None, 0, 0, cutoff)
    rows = sorted(
        (
            row
            for row in observations
            if row.target is not None
            and row.label_available_at is not None
            and row.label_available_at <= cutoff
            and row.decision_date < cutoff.date()
        ),
        key=lambda row: (row.decision_date, row.security_id),
    )
    if not rows:
        raise ValueError("no matured training rows")
    if len({(row.security_id, row.decision_date) for row in rows}) != len(rows):
        raise ValueError("duplicate training observation")
    import numpy as np

    matrix = np.asarray([row.features for row in rows], dtype=float)
    targets = np.asarray([row.target for row in rows], dtype=float)
    counts = Counter(row.decision_date for row in rows)
    weights = np.asarray([len(rows) / (len(counts) * counts[row.decision_date]) for row in rows])
    scaler = None
    if family == "ridge":
        from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
        from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

        scaler = StandardScaler().fit(matrix, sample_weight=weights)
        estimator: Any = Ridge(alpha=ridge_alpha).fit(
            scaler.transform(matrix), targets, sample_weight=weights
        )
    else:
        from xgboost import XGBRegressor

        estimator = XGBRegressor(
            objective="reg:squarederror",
            tree_method="hist",
            n_jobs=1,
            random_state=seed,
            **xgboost_parameters,
        ).fit(matrix, targets, sample_weight=weights)
    return IterationModel(family, estimator, scaler, len(rows), len(counts), cutoff)
