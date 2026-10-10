"""Calendar design must not silently turn coverage into readiness."""
from datetime import date, datetime
from pathlib import Path

import pytest

from src.cli.r3_later_period import materialize
from src.research.r3_later_period import plan_period


@pytest.fixture
def sessions() -> tuple[date, ...]:
    xcals = pytest.importorskip("exchange_calendars")
    return tuple(day.date() for day in xcals.get_calendar(
        "XNYS", start="2010-01-01", end="2027-01-10"
    ).sessions)


def plan(sessions: tuple[date, ...], keys: tuple = ()) -> dict:
    return plan_period(
        sessions, sessions, requested_start=date(2010, 1, 1),
        complete_through=date(2026, 9, 15), feature_keys=keys,
    )


def test_exact_windows_exclude_partial_year_and_expand(sessions: tuple[date, ...]) -> None:
    report = plan(sessions)
    assert report["actual_origin"] == "2010-01-04"
    assert report["complete_calendar_folds"] == 6
    first, last = report["folds"][0], report["folds"][-1]
    assert first["segments"]["train"]["end"] == "2018-01-03"
    assert first["segments"]["validation"]["start"] == "2018-01-04"
    assert first["segments"]["test"]["start"] == "2020-01-06"
    assert last["segments"]["test"]["end"] == "2026-01-02"
    assert last["segments"]["train"]["start"] == "2010-01-04"
    assert not report["model_fitting_permitted"]
    assert not report["full_universe_coverage_verified"]
    assert not report["qualification_permitted"]


def test_missing_session_rejected(sessions: tuple[date, ...]) -> None:
    with pytest.raises(ValueError, match="independent exchange"):
        plan_period(sessions[1:], sessions, requested_start=date(2010, 1, 1),
                    complete_through=date(2026, 9, 15), feature_keys=())


def test_coverage_is_separate_from_eligibility_and_calendar(sessions: tuple[date, ...]) -> None:
    report = plan(sessions, (("a", date(2010, 1, 29), True),
                             ("b", date(2010, 1, 29), False),
                             ("a", date(2026, 9, 15), True)))
    assert report["monthly_coverage"][0] == {
        "date": "2010-01-29", "usable": 1, "excluded": 1
    }
    assert report["excluded_terminal_partial_month_rows"] == 1
    assert report["monthly_coverage"][-1]["date"] == "2026-08-31"
    assert report["folds"][0]["segments"]["train"]["dates_without_usable_price_features"]
    assert report["complete_calendar_folds"] == plan(sessions)["complete_calendar_folds"]


@pytest.mark.parametrize("keys,match", [
    ((("a", date(2010, 1, 29), True), ("a", date(2010, 1, 29), False)), "duplicate"),
    ((("a", date(2010, 1, 28), True),), "month end"),
])
def test_bad_keys_fail(sessions: tuple[date, ...], keys: tuple, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        plan(sessions, keys)


def test_immutable_output(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    output.write_text("preserve")
    with pytest.raises(FileExistsError):
        materialize(tmp_path / "absent", output, datetime.fromisoformat("2026-10-07T00:00Z"))
    assert output.read_text() == "preserve"


def test_cannot_shorten_registered_windows(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(Path("config.r3-later-period.yaml").read_text().replace(
        "initial_train_years: 8", "initial_train_years: 4"
    ))
    with pytest.raises(ValueError, match="separate contract"):
        materialize(config, tmp_path / "out", datetime.fromisoformat("2026-10-07T00:00Z"))


def test_source_tampering_fails_before_planning(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    source = tmp_path / "calendar.csv"
    source.write_text("tampered")
    config.write_text(Path("config.r3-later-period.yaml").read_text().replace(
        "data/local/phase3_v2/calendar.csv", str(source)
    ))
    with pytest.raises(ValueError, match="hash mismatch"):
        materialize(config, tmp_path / "out", datetime.fromisoformat("2026-10-07T00:00Z"))
    assert not (tmp_path / "out").exists()


def test_duplicate_config_keys_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(Path("config.r3-later-period.yaml").read_text() + "test_years: 1\n")
    with pytest.raises(ValueError, match="duplicate config key"):
        materialize(config, tmp_path / "out", datetime.fromisoformat("2026-10-07T00:00Z"))
