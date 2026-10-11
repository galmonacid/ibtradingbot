from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import LearningObservation
from src.learning.r3_enriched import RATIO_NAMES, fit_enriched
from src.research.r3_fundamental_iteration import admitted_sample_map, enrich, indexed_ratios
from src.research.r3_iteration import monthly_diagnostic


def _row(security_id: str, day: date, target: float | None = None) -> LearningObservation:
    return LearningObservation(
        security_id,
        day,
        None
        if target is None
        else datetime.combine(day, datetime.min.time(), UTC) + timedelta(days=35),
        tuple(index / 10 for index in range(len(R3_FEATURE_NAMES))),
        target,
    )


def _source(day: date, *, first_value: float | None, available: datetime | None) -> dict:
    cutoff = datetime.combine(day, datetime.min.time(), UTC)
    return {
        "cik": "0000000001",
        "decision_at": cutoff.isoformat(),
        "ratios": [
            {
                "name": name,
                "value": first_value if index == 0 else None,
                "available_at": available.isoformat() if index == 0 and available else None,
            }
            for index, name in enumerate(RATIO_NAMES)
        ],
    }


def test_only_manual_single_identity_is_admitted() -> None:
    good = {
        "security_ids": ["A"],
        "cik": "0000000001",
        "join_status": "manually_matched_sample_only",
    }
    ambiguous = {
        "security_ids": ["B", "C"],
        "cik": "0000000002",
        "join_status": "ambiguous_multiple_security_ids",
    }
    assert admitted_sample_map([good, ambiguous], ["A"], {"0000000001"}) == {"A": "0000000001"}
    with pytest.raises(ValueError, match="ambiguous"):
        admitted_sample_map([good, ambiguous], ["B"], {"0000000002"})


def test_sparse_join_retains_every_price_row_and_timestamp_boundary() -> None:
    day = date(2020, 1, 31)
    cutoff = datetime.combine(day, datetime.min.time(), UTC)
    rows = (_row("A", day), _row("B", day))
    source = _source(day, first_value=0.25, available=cutoff)
    enriched, coverage = enrich(
        rows,
        {("A", day): cutoff, ("B", day): cutoff},
        {"A": "0000000001"},
        indexed_ratios({"monthly": [source]}),
    )
    assert len(enriched) == len(rows)
    assert enriched[0].features[-8:] == (0.25, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    assert enriched[1].features[-8:] == (0.0, 1.0) * 4
    assert coverage["observed_ratio_counts"] == {"liabilities_assets": 1}
    assert monthly_diagnostic(enriched, [2, 1], top_k=1)["selected_ids"] == ["A"]
    source["ratios"][0]["available_at"] = (cutoff + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="future"):
        enrich(
            rows,
            {("A", day): cutoff, ("B", day): cutoff},
            {"A": "0000000001"},
            indexed_ratios({"monthly": [source]}),
        )


def test_missing_ratio_never_drops_issuer_or_looks_ahead() -> None:
    day = date(2020, 1, 31)
    cutoff = datetime.combine(day, datetime.min.time(), UTC)
    missing = _source(day, first_value=None, available=None)
    output, _ = enrich(
        (_row("A", day),),
        {("A", day): cutoff},
        {"A": "0000000001"},
        indexed_ratios({"monthly": [missing]}),
    )
    assert output[0].features[-8:] == (0.0, 1.0) * 4


def test_early_close_source_is_usable_after_price_feature_cutoff() -> None:
    day = date(2020, 11, 27)
    source_close = datetime(2020, 11, 27, 18, tzinfo=UTC)
    price_cutoff = datetime(2020, 11, 27, 21, tzinfo=UTC)
    source = _source(day, first_value=0.4, available=source_close)
    source["decision_at"] = source_close.isoformat()
    output, _ = enrich((_row("A", day),), {("A", day): price_cutoff},
                       {"A": "0000000001"}, indexed_ratios({"monthly": [source]}))
    assert output[0].features[-8:] == (0.4, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)


def test_enriched_fit_uses_only_matured_labels() -> None:
    pytest.importorskip("xgboost")
    day = date(2019, 1, 31)
    cutoff = datetime(2020, 1, 1, tzinfo=UTC)
    base = tuple((index + 1) / 100 for index in range(len(R3_FEATURE_NAMES)))
    from src.learning.r3_enriched import EnrichedObservation

    rows = [
        EnrichedObservation(
            f"S{i}",
            day,
            datetime(2019, 3, 1, tzinfo=UTC),
            base + (i / 100, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
            i / 100,
        )
        for i in range(120)
    ]
    future = EnrichedObservation(
        "F",
        day,
        datetime(2021, 1, 1, tzinfo=UTC),
        base + (0.0, 1.0) * 4,
        99.0,
    )
    params = {
        "n_estimators": 5,
        "max_depth": 2,
        "learning_rate": 0.1,
        "min_child_weight": 10.0,
        "reg_lambda": 1.0,
        "reg_alpha": 0.0,
        "subsample": 1.0,
        "colsample_bytree": 1.0,
    }
    left = fit_enriched(
        "xgboost",
        [*rows, future],
        cutoff=cutoff,
        ridge_alpha=10.0,
        xgboost_parameters=params,
        seed=7,
    )
    right = fit_enriched(
        "xgboost", rows, cutoff=cutoff, ridge_alpha=10.0, xgboost_parameters=params, seed=7
    )
    assert left.training_rows == 120
    assert left.score(rows[:10]) == right.score(rows[:10])
