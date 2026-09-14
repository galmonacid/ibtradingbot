from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.data.point_in_time_universe import (
    POINT_IN_TIME_UNIVERSE_COLUMNS,
    PointInTimeUniverseError,
    load_membership_intervals,
    resolve_membership,
)


def _write(path: Path, rows: list[str], *, header: str | None = None) -> None:
    path.write_text(
        (header or ",".join(POINT_IN_TIME_UNIVERSE_COLUMNS)) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def test_membership_resolution_respects_future_entry_and_exclusive_removal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "membership.csv"
    _write(
        path,
        [
            "pit-v1,AAA,2020-01-01,2020-06-01",
            "pit-v1,BBB,2020-03-01,",
        ],
    )
    intervals = load_membership_intervals(path, expected_source_version="pit-v1")

    assert resolve_membership(intervals, date(2020, 2, 29)).symbols == ("AAA",)
    assert resolve_membership(intervals, date(2020, 3, 1)).symbols == ("AAA", "BBB")
    assert resolve_membership(intervals, date(2020, 6, 1)).symbols == ("BBB",)


def test_future_rows_do_not_change_historical_membership_prefix(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix.csv"
    extended = tmp_path / "extended.csv"
    _write(prefix, ["pit-v1,AAA,2020-01-01,"])
    _write(
        extended,
        [
            "pit-v1,ZZZ,2030-01-01,",
            "pit-v1,AAA,2020-01-01,",
            "pit-v1,BBB,2029-01-01,2029-12-01",
        ],
    )

    before = resolve_membership(load_membership_intervals(prefix), date(2025, 1, 1))
    after = resolve_membership(load_membership_intervals(extended), date(2025, 1, 1))
    assert after.symbols == before.symbols == ("AAA",)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            ["pit-v1,AAA,2020-01-01,", "pit-v1,AAA,2021-01-01,2022-01-01"],
            "overlapping",
        ),
        (
            ["pit-v1,AAA,2020-01-01,2021-01-01", "pit-v2,BBB,2020-01-01,"],
            "exactly one source_version",
        ),
        (["pit-v1,AAA,2021-01-01,2021-01-01"], "must be after"),
    ],
)
def test_loader_rejects_invalid_intervals_and_versions(
    tmp_path: Path, rows: list[str], message: str
) -> None:
    path = tmp_path / "invalid.csv"
    _write(path, rows)
    with pytest.raises(PointInTimeUniverseError, match=message):
        load_membership_intervals(path)


def test_loader_rejects_wrong_schema_and_expected_version(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.csv"
    _write(wrong, ["pit-v1,AAA,2020-01-01,"], header="symbol,source_version,from,to")
    with pytest.raises(PointInTimeUniverseError, match="exact canonical"):
        load_membership_intervals(wrong)

    valid = tmp_path / "valid.csv"
    _write(valid, ["pit-v1,AAA,2020-01-01,"])
    with pytest.raises(PointInTimeUniverseError, match="expected version"):
        load_membership_intervals(valid, expected_source_version="pit-v2")


def test_disjoint_reentry_intervals_are_valid(tmp_path: Path) -> None:
    path = tmp_path / "reentry.csv"
    _write(
        path,
        [
            "pit-v1,AAA,2022-01-01,",
            "pit-v1,AAA,2020-01-01,2021-01-01",
        ],
    )
    intervals = load_membership_intervals(path)

    assert resolve_membership(intervals, date(2021, 6, 1)).symbols == ()
    assert resolve_membership(intervals, date(2022, 1, 1)).symbols == ("AAA",)
