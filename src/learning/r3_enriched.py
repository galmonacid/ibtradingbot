"""Separate causal-price plus sparse-fundamental learners for one ablation."""

from __future__ import annotations

import hashlib
import math
import pickle
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from src.features.r3 import R3_FEATURE_NAMES

RATIO_NAMES = (
    "liabilities_assets",
    "annual_net_income_assets",
    "annual_operating_cash_flow_assets",
    "annual_gross_profit_assets",
)
ENRICHED_FEATURE_NAMES = R3_FEATURE_NAMES + tuple(
    name + suffix for name in RATIO_NAMES for suffix in ("_value", "_missing")
)


@dataclass(frozen=True)
class EnrichedObservation:
    security_id: str
    decision_date: date
    label_available_at: datetime | None
    features: tuple[float, ...]
    target: float | None

    def __post_init__(self) -> None:
        if not self.security_id or len(self.features) != len(ENRICHED_FEATURE_NAMES):
            raise ValueError("enriched observation schema mismatch")
        if any(not math.isfinite(value) for value in self.features):
            raise ValueError("enriched features must be finite")
        if (self.target is None) != (self.label_available_at is None):
            raise ValueError("target and availability must be present together")
        if self.label_available_at is not None and self.label_available_at.utcoffset() is None:
            raise ValueError("aware target availability required")


@dataclass(frozen=True)
class EnrichedModel:
    family: str
    estimator: Any
    scaler: Any
    cutoff: datetime
    training_rows: int
    training_dates: int

    def score(self, rows: Sequence[EnrichedObservation]) -> list[float]:
        import numpy as np

        if not rows:
            return []
        matrix = np.asarray([row.features for row in rows], dtype=float)
        if self.scaler is not None:
            matrix = self.scaler.transform(matrix)
        result = [float(value) for value in self.estimator.predict(matrix)]
        if len(result) != len(rows) or not all(math.isfinite(value) for value in result):
            raise ValueError("invalid enriched model scores")
        return result

    def payload(self) -> bytes:
        return pickle.dumps(self, protocol=5)

    def manifest(self) -> dict[str, object]:
        return {
            "family": self.family,
            "feature_names": ENRICHED_FEATURE_NAMES,
            "cutoff": self.cutoff.isoformat(),
            "training_rows": self.training_rows,
            "training_dates": self.training_dates,
            "model_sha256": hashlib.sha256(self.payload()).hexdigest(),
        }


def fit_enriched(
    family: str,
    rows: Sequence[EnrichedObservation],
    *,
    cutoff: datetime,
    ridge_alpha: float,
    xgboost_parameters: dict[str, int | float],
    seed: int,
) -> EnrichedModel:
    if family not in ("ridge", "xgboost") or cutoff.utcoffset() is None:
        raise ValueError("registered enriched family and aware cutoff required")
    eligible = sorted(
        (
            row
            for row in rows
            if row.target is not None
            and row.label_available_at is not None
            and row.label_available_at < cutoff
            and row.decision_date < cutoff.date()
        ),
        key=lambda row: (row.decision_date, row.security_id),
    )
    if not eligible or len({(r.security_id, r.decision_date) for r in eligible}) != len(eligible):
        raise ValueError("nonempty, unique matured training observations required")
    import numpy as np

    matrix = np.asarray([row.features for row in eligible], dtype=float)
    targets = np.asarray([row.target for row in eligible], dtype=float)
    counts = Counter(row.decision_date for row in eligible)
    weights = np.asarray(
        [len(eligible) / (len(counts) * counts[row.decision_date]) for row in eligible]
    )
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
    return EnrichedModel(family, estimator, scaler, cutoff, len(eligible), len(counts))
