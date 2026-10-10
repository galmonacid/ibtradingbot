"""Date-only later-period design and existing price-feature coverage, never selection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from src.validation.walk_forward import build_expanding_windows


def plan_period(
    sessions: Sequence[date],
    independent_sessions: Sequence[date],
    *,
    requested_start: date,
    complete_through: date,
    feature_keys: Iterable[tuple[str, date, bool]],
) -> dict[str, Any]:
    """Verify the cropped calendar and count eligibility without reading future targets.

    Feature counts describe the existing canonical slice, not historical-universe
    completeness. Full monthly endpoints come from the independent exchange calendar.
    """
    selected = tuple(day for day in sessions if requested_start <= day <= complete_through)
    expected = tuple(
        day for day in independent_sessions if requested_start <= day <= complete_through
    )
    if not expected or selected != expected:
        raise ValueError("local calendar does not match independent exchange sessions")
    windows = build_expanding_windows(
        selected, verified_complete_through=complete_through,
        initial_train_years=8, validation_years=2, test_years=1, step_months=12,
    )
    month_ends = {
        day for day, following in zip(independent_sessions, independent_sessions[1:], strict=False)
        if (day.year, day.month) != (following.year, following.month)
        and requested_start <= day <= complete_through
    }
    counts: Counter[date] = Counter()
    excluded: Counter[date] = Counter()
    partial_month_rows = 0
    seen: set[tuple[str, date]] = set()
    for security_id, day, usable in feature_keys:
        if not requested_start <= day <= complete_through:
            continue
        key = (security_id, day)
        if key in seen:
            raise ValueError("duplicate security/decision date")
        seen.add(key)
        if day not in month_ends:
            if day == complete_through and day in selected:
                partial_month_rows += 1
                continue
            raise ValueError("feature decision date is not a complete exchange month end")
        (counts if usable else excluded)[day] += 1
    folds = []
    for window in windows:
        segments = {}
        for name, days in (
            ("train", window.train), ("validation", window.validation), ("test", window.test)
        ):
            decisions = sorted(month_ends.intersection(days))
            segments[name] = {
                "start": days[0].isoformat(), "end": days[-1].isoformat(),
                "sessions": len(days), "monthly_decisions": len(decisions),
                "usable_price_feature_rows": sum(counts[day] for day in decisions),
                "excluded_price_feature_rows": sum(excluded[day] for day in decisions),
                "dates_without_usable_price_features": [
                    day.isoformat() for day in decisions if not counts[day]
                ],
            }
        folds.append({"index": window.index, "segments": segments})
    return {
        "actual_origin": selected[0].isoformat(), "folds": folds,
        "complete_calendar_folds": len(folds),
        "excluded_terminal_partial_month_rows": partial_month_rows,
        "calendar_verified_through": complete_through.isoformat(),
        "monthly_coverage": [
            {"date": day.isoformat(), "usable": counts[day], "excluded": excluded[day]}
            for day in sorted(month_ends)
        ],
        "development_only": True, "model_fitting_permitted": False,
        "full_universe_coverage_verified": False,
        "qualification_permitted": False,
        "limitations": [
            "Calendar completeness is not price, label, action or issuer coverage.",
            "Existing price-feature slice omits failed source histories.",
            "SEC sample cannot establish full-universe causal feature coverage.",
            "No labels read; actual label-overlap purging remains required at materialization.",
            "31-session purge, maturation and training-only preprocessing remain mandatory.",
            "All these historical dates are development data, not an untouched test.",
            "No model, cost, portfolio or risk configuration is replaced by this design.",
        ],
    }
