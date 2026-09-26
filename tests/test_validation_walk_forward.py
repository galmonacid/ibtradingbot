from datetime import date, timedelta

import pytest

from src.validation.native_workflow import _apply_trading_session_embargo
from src.validation.walk_forward import (
    WalkForwardError,
    WalkForwardWindow,
    build_expanding_windows,
    stitch_test_observations,
)


def _daily_sessions(start: date, days: int) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range(days))


def test_expanding_windows_are_chronological_and_use_documented_defaults() -> None:
    sessions = _daily_sessions(date(2007, 1, 1), 12 * 366)
    windows = build_expanding_windows(sessions, verified_complete_through=sessions[-1])
    assert windows
    first = windows[0]
    assert first.train[0] == date(2007, 1, 1)
    assert first.train[-1] < date(2015, 1, 1)
    assert first.validation[0] == date(2015, 1, 1)
    assert first.test[0] == date(2017, 1, 1)
    assert first.test[-1] == date(2017, 12, 31)
    assert windows[1].train[: len(first.train)] == first.train
    assert windows[1].validation[0] == date(2015, 7, 1)


def test_incomplete_final_test_window_is_not_emitted() -> None:
    sessions = _daily_sessions(date(2007, 1, 1), 10 * 365 + 100)
    assert build_expanding_windows(sessions, verified_complete_through=sessions[-1]) == ()


def test_embargo_removes_exact_trading_sessions_not_calendar_days() -> None:
    window = WalkForwardWindow(
        0,
        (date(2020, 1, 2),),
        (date(2020, 1, 3), date(2020, 1, 6), date(2020, 1, 10)),
        (date(2020, 1, 13),),
    )
    result = _apply_trading_session_embargo((window,), 2)
    assert result[0].validation == (date(2020, 1, 3),)
    with pytest.raises(ValueError, match="consumes"):
        _apply_trading_session_embargo((window,), 3)


def test_stitching_keeps_earliest_fold_for_overlapping_test_dates() -> None:
    first = WalkForwardWindow(
        0,
        (date(2018, 1, 1),),
        (date(2019, 1, 1),),
        (date(2020, 1, 1), date(2020, 7, 1)),
    )
    second = WalkForwardWindow(
        1,
        (date(2018, 1, 1),),
        (date(2019, 7, 1),),
        (date(2020, 7, 1), date(2021, 1, 1)),
    )
    stitched = stitch_test_observations(
        [
            (1, [(date(2020, 7, 1), "later"), (date(2021, 1, 1), "second")]),
            (0, [(date(2020, 1, 1), "first"), (date(2020, 7, 1), "earliest")]),
        ],
        windows=(first, second),
    )
    assert stitched == (
        (date(2020, 1, 1), "first"),
        (date(2020, 7, 1), "earliest"),
        (date(2021, 1, 1), "second"),
    )


@pytest.mark.parametrize("sessions", [(), (date(2020, 1, 2), date(2020, 1, 1))])
def test_invalid_sessions_fail_closed(sessions: tuple[date, ...]) -> None:
    with pytest.raises(WalkForwardError):
        build_expanding_windows(sessions, verified_complete_through=date(2025, 1, 1))


def test_completeness_provenance_and_exact_stitching_fail_closed() -> None:
    sessions = _daily_sessions(date(2007, 1, 1), 12 * 366)
    with pytest.raises(WalkForwardError, match="completeness"):
        build_expanding_windows(sessions, verified_complete_through=date(2010, 1, 1))

    window = WalkForwardWindow(
        0,
        (date(2018, 1, 1),),
        (date(2019, 1, 1),),
        (date(2020, 1, 1), date(2020, 1, 2)),
    )
    with pytest.raises(WalkForwardError, match="exactly"):
        stitch_test_observations([(0, [(date(2020, 1, 1), "missing")])], windows=(window,))
    with pytest.raises(WalkForwardError, match="exactly"):
        stitch_test_observations(
            [(0, [(date(2020, 1, 1), "ok"), (date(2020, 1, 3), "outside")])],
            windows=(window,),
        )
