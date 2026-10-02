"""Deterministic, causal scoring for the bounded R3 candidate set."""

from __future__ import annotations

import hashlib
import json
import math
import pickle
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Protocol, cast

from src.config.r3 import CandidateConfig
from src.features.r3 import R3_FEATURE_NAMES

MOMENTUM_FEATURE_INDEX = R3_FEATURE_NAMES.index("momentum_252_skip21")


class _Predictor(Protocol):
    def predict(self, values: Any) -> Any: ...


@dataclass(frozen=True)
class LearningObservation:
    security_id: str
    decision_date: date
    label_available_at: datetime | None
    features: tuple[float, ...]
    target: float | None

    def __post_init__(self) -> None:
        if not self.security_id or len(self.features) != len(R3_FEATURE_NAMES):
            raise ValueError("learning observation must use the fixed R3 feature schema")
        if any(not math.isfinite(value) for value in self.features):
            raise ValueError("features must be finite")
        if self.target is not None and not math.isfinite(self.target):
            raise ValueError("target must be finite when present")
        if (self.target is None) != (self.label_available_at is None):
            raise ValueError("target and label availability must be present together")
        if self.label_available_at is not None and self.label_available_at.tzinfo is None:
            raise ValueError("label availability must be timezone-aware")


@dataclass(frozen=True)
class FittedR3Model:
    candidate: CandidateConfig
    feature_names: tuple[str, ...]
    fitted_at: datetime
    training_cutoff: datetime
    training_rows: int
    training_dates: int
    estimator_sha256: str
    dependency_versions: dict[str, str]
    _scaler: object | None
    _estimator: object | None

    def __post_init__(self) -> None:
        if self.fitted_at.tzinfo is None or self.training_cutoff.tzinfo is None:
            raise ValueError("model timestamps must be timezone-aware")
        if self.feature_names != R3_FEATURE_NAMES:
            raise ValueError("model feature schema differs from the registered R3 schema")
        if self.candidate.family == "momentum":
            if self._scaler is not None or self._estimator is not None:
                raise ValueError("momentum control cannot contain a fitted estimator")
        elif self._estimator is None or self.training_rows <= 0 or self.training_dates <= 0:
            raise ValueError("learned candidates require fitted training evidence")

    def score(self, observations: Sequence[LearningObservation]) -> dict[str, float]:
        ordered = tuple(sorted(observations, key=lambda row: row.security_id))
        if len({row.security_id for row in ordered}) != len(ordered):
            raise ValueError("one scoring row per security is required")
        if not ordered:
            return {}
        if self.candidate.family == "momentum":
            return {
                row.security_id: row.features[MOMENTUM_FEATURE_INDEX] for row in ordered
            }
        try:
            import numpy as np
        except ImportError as error:  # pragma: no cover - guarded by the research extra
            raise RuntimeError("install the research extra for R3 inference") from error
        matrix = np.asarray([row.features for row in ordered], dtype=float)
        if self._scaler is not None:
            matrix = cast(Any, self._scaler).transform(matrix)
        predictions = cast(_Predictor, self._estimator).predict(matrix)
        result = {
            row.security_id: float(value)
            for row, value in zip(ordered, predictions, strict=True)
        }
        if any(not math.isfinite(value) for value in result.values()):
            raise ValueError("model produced a non-finite score")
        return result

    def manifest(self) -> dict[str, object]:
        return {
            "candidate": asdict(self.candidate),
            "feature_names": list(self.feature_names),
            "fitted_at": self.fitted_at.isoformat(),
            "training_cutoff": self.training_cutoff.isoformat(),
            "training_rows": self.training_rows,
            "training_dates": self.training_dates,
            "estimator_sha256": self.estimator_sha256,
            "dependency_versions": dict(sorted(self.dependency_versions.items())),
        }


def _date_equal_weights(rows: Sequence[LearningObservation]) -> list[float]:
    counts = Counter(row.decision_date for row in rows)
    return [1.0 / counts[row.decision_date] for row in rows]


def _artifact_hash(candidate: CandidateConfig, scaler: object | None, estimator: object) -> str:
    payload = pickle.dumps((asdict(candidate), R3_FEATURE_NAMES, scaler, estimator), protocol=5)
    return hashlib.sha256(payload).hexdigest()


def fit_r3_model(
    candidate: CandidateConfig,
    observations: Iterable[LearningObservation],
    *,
    training_cutoff: datetime,
    fitted_at: datetime,
    seed: int = 20260926,
) -> FittedR3Model:
    """Fit only labels available by ``training_cutoff``, weighting each date equally."""
    if training_cutoff.tzinfo is None or fitted_at.tzinfo is None:
        raise ValueError("training timestamps must be timezone-aware")
    if fitted_at < training_cutoff:
        raise ValueError("fitted_at cannot precede the training cutoff")
    rows = tuple(
        sorted(
            (
                row
                for row in observations
                if row.target is not None
                and row.label_available_at is not None
                and row.label_available_at <= training_cutoff
                and row.decision_date < training_cutoff.date()
            ),
            key=lambda row: (row.decision_date, row.security_id),
        )
    )
    versions: dict[str, str] = {}
    if candidate.family == "momentum":
        identity = hashlib.sha256(
            json.dumps(asdict(candidate), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return FittedR3Model(
            candidate,
            R3_FEATURE_NAMES,
            fitted_at,
            training_cutoff,
            0,
            0,
            identity,
            versions,
            None,
            None,
        )
    if not rows:
        raise ValueError("no matured causal training rows are available")
    try:
        import numpy as np
        import sklearn  # type: ignore[import-untyped]
        from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore[import-untyped]
        from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
        from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
    except ImportError as error:  # pragma: no cover - guarded by the research extra
        raise RuntimeError("install the research extra for R3 model fitting") from error
    versions = {"numpy": np.__version__, "scikit-learn": sklearn.__version__}
    matrix = np.asarray([row.features for row in rows], dtype=float)
    target = np.asarray([cast(float, row.target) for row in rows], dtype=float)
    weights = np.asarray(_date_equal_weights(rows), dtype=float)
    scaler: object | None = None
    if candidate.family == "ridge":
        scaler = StandardScaler().fit(matrix, sample_weight=weights)
        transformed = cast(Any, scaler).transform(matrix)
        estimator: object = Ridge(alpha=cast(float, candidate.alpha)).fit(
            transformed, target, sample_weight=weights
        )
    else:
        estimator = HistGradientBoostingRegressor(
            loss="squared_error",
            learning_rate=0.05,
            max_iter=200,
            l2_regularization=1.0,
            min_samples_leaf=100,
            max_leaf_nodes=cast(int, candidate.max_leaf_nodes),
            early_stopping=False,
            random_state=seed,
        ).fit(matrix, target, sample_weight=weights)
    return FittedR3Model(
        candidate,
        R3_FEATURE_NAMES,
        fitted_at,
        training_cutoff,
        len(rows),
        len({row.decision_date for row in rows}),
        _artifact_hash(candidate, scaler, estimator),
        versions,
        scaler,
        estimator,
    )


def rank_scores(scores: dict[str, float]) -> tuple[str, ...]:
    """Descending score with the registered stable-ID tie break."""
    if any(not key or not math.isfinite(value) for key, value in scores.items()):
        raise ValueError("scores require stable identities and finite values")
    return tuple(sorted(scores, key=lambda security_id: (-scores[security_id], security_id)))
