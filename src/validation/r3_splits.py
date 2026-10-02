"""Date-grouped, matured-label R3 chronological splits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from src.features.r3 import R3Label
from src.validation.walk_forward import build_expanding_windows


@dataclass(frozen=True)
class R3SplitAssignment:
    security_id: str
    decision_date: date
    fold_id: int
    split: Literal["train", "validation", "test"]


def build_r3_split_assignments(
    labels: tuple[R3Label, ...],
    sessions: tuple[date, ...],
    *,
    verified_complete_through: date,
    as_of: datetime,
    purge_sessions: int = 31,
) -> tuple[R3SplitAssignment, ...]:
    """Assign complete dates while purging actual label intervals and availability.

    A row is usable only after label maturation. Training and validation labels
    must end and be available before the next segment's 31-session boundary.
    """
    if as_of.tzinfo is None or purge_sessions != 31:
        raise ValueError("aware as_of and the registered 31-session purge are required")
    windows = build_expanding_windows(
        sessions,
        verified_complete_through=verified_complete_through,
        initial_train_years=8,
        validation_years=2,
        test_years=1,
        step_months=12,
    )
    matured = tuple(
        label
        for label in labels
        if label.matured and label.available_at is not None and label.available_at <= as_of
    )
    assignments: list[R3SplitAssignment] = []
    for window in windows:
        validation_boundary = window.validation[0]
        test_boundary = window.test[0]
        validation_boundary_index = sessions.index(validation_boundary)
        test_boundary_index = sessions.index(test_boundary)
        if validation_boundary_index <= purge_sessions or test_boundary_index <= purge_sessions:
            continue
        train_cutoff = sessions[validation_boundary_index - purge_sessions - 1]
        validation_cutoff = sessions[test_boundary_index - purge_sessions - 1]
        for label in matured:
            available_day = (
                label.available_at.date() if label.available_at is not None else date.max
            )
            if (
                label.decision_date in window.train
                and label.exit_at.date() < validation_boundary
                and available_day < validation_boundary
                and label.exit_at.date() <= train_cutoff
            ):
                split: Literal["train", "validation", "test"] = "train"
            elif (
                label.decision_date in window.validation
                and label.exit_at.date() < test_boundary
                and available_day < test_boundary
                and label.exit_at.date() <= validation_cutoff
            ):
                split = "validation"
            elif label.decision_date in window.test:
                split = "test"
            else:
                continue
            assignments.append(
                R3SplitAssignment(label.security_id, label.decision_date, window.index, split)
            )
    return tuple(
        sorted(
            assignments,
            key=lambda row: (row.fold_id, row.split, row.decision_date, row.security_id),
        )
    )
