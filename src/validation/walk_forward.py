"""Expanding chronological walk-forward windows and overlap-safe OOS stitching."""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta


class WalkForwardError(ValueError):
    """Raised when chronological validation cannot be constructed safely."""


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    train: tuple[date, ...]
    validation: tuple[date, ...]
    test: tuple[date, ...]

    def __post_init__(self) -> None:
        if not self.train or not self.validation or not self.test:
            raise WalkForwardError("every walk-forward segment must be non-empty")
        if not self.train[-1] < self.validation[0] or not self.validation[-1] < self.test[0]:
            raise WalkForwardError("walk-forward segments must be strictly chronological")


def _add_months(value: date, months: int) -> date:
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_expanding_windows(
    sessions: Sequence[date],
    *,
    verified_complete_through: date,
    initial_train_years: int = 8,
    validation_years: int = 2,
    test_years: int = 1,
    step_months: int = 6,
) -> tuple[WalkForwardWindow, ...]:
    """Build expanding folds from an externally verified complete session series.

    ``verified_complete_through`` is the inclusive calendar date through which the
    caller's exchange calendar/data coverage has been checked.  Requiring this
    explicit provenance avoids guessing completeness from the last observed session.
    """
    if min(initial_train_years, validation_years, test_years, step_months) <= 0:
        raise WalkForwardError("window durations and step must be positive")
    ordered = tuple(sessions)
    if not ordered or len(set(ordered)) != len(ordered):
        raise WalkForwardError("sessions must be non-empty and unique")
    if any(later <= earlier for earlier, later in zip(ordered, ordered[1:], strict=False)):
        raise WalkForwardError("sessions must be strictly increasing")
    if verified_complete_through < ordered[-1]:
        raise WalkForwardError("verified completeness cannot precede the last session")

    origin = ordered[0]
    first_validation = _add_months(origin, initial_train_years * 12)
    folds: list[WalkForwardWindow] = []
    index = 0
    while True:
        validation_start = _add_months(first_validation, index * step_months)
        test_start = _add_months(validation_start, validation_years * 12)
        test_end = _add_months(test_start, test_years * 12)
        train = tuple(item for item in ordered if item < validation_start)
        validation = tuple(item for item in ordered if validation_start <= item < test_start)
        test = tuple(item for item in ordered if test_start <= item < test_end)
        if test_end > verified_complete_through + timedelta(days=1):
            break
        if not test:
            raise WalkForwardError("verified test interval contains no sessions")
        if train and validation:
            folds.append(WalkForwardWindow(index, train, validation, test))
        index += 1
    return tuple(folds)


def stitch_test_observations[T](
    fold_observations: Iterable[tuple[int, Sequence[tuple[date, T]]]],
    *,
    windows: Sequence[WalkForwardWindow],
) -> tuple[tuple[date, T], ...]:
    """Stitch tests after proving every observation belongs to its declared fold."""
    window_by_index = {window.index: window for window in windows}
    if len(window_by_index) != len(windows):
        raise WalkForwardError("walk-forward window indices must be unique")
    selected: dict[date, tuple[int, T]] = {}
    observed_folds: set[int] = set()
    for fold_index, observations in sorted(fold_observations, key=lambda item: item[0]):
        if fold_index in observed_folds:
            raise WalkForwardError("each fold must provide exactly one observation series")
        observed_folds.add(fold_index)
        window = window_by_index.get(fold_index)
        if window is None:
            raise WalkForwardError("observations reference an undeclared fold")
        previous: date | None = None
        observed_dates: list[date] = []
        for observed_date, value in observations:
            if previous is not None and observed_date <= previous:
                raise WalkForwardError("each fold's observations must be strictly increasing")
            previous = observed_date
            observed_dates.append(observed_date)
            selected.setdefault(observed_date, (fold_index, value))
        if tuple(observed_dates) != window.test:
            raise WalkForwardError("each fold must contain exactly its declared test observations")
    if observed_folds != set(window_by_index):
        raise WalkForwardError("every declared fold must provide observations")
    return tuple((item_date, selected[item_date][1]) for item_date in sorted(selected))
