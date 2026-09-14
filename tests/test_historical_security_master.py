from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.config.settings import load_config
from src.data.historical_security_master import (
    HISTORICAL_SECURITY_MASTER_COLUMNS,
    HistoricalSecurityMasterError,
    load_historical_security_master,
)
from src.data.point_in_time_universe import (
    MembershipInterval,
    PointInTimeUniverseError,
    filter_point_in_time_universe,
    resolve_membership,
)

ROOT = Path(__file__).parents[1]


def _metadata_row(symbol: str, *, benchmark: bool = False) -> str:
    return f"master-v1,{symbol},{str(benchmark).lower()},true,true,false,false,true"


def _write_master(path: Path, rows: list[str]) -> None:
    path.write_text(
        ",".join(HISTORICAL_SECURITY_MASTER_COLUMNS) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def test_master_allows_more_than_fifty_distinct_with_at_most_fifty_active(
    tmp_path: Path,
) -> None:
    path = tmp_path / "master.csv"
    symbols = [f"S{index:03d}" for index in range(80)]
    _write_master(path, [_metadata_row("SPY", benchmark=True), *map(_metadata_row, symbols)])
    securities = load_historical_security_master(path, benchmark="SPY")
    intervals = tuple(
        MembershipInterval(
            "pit-v1",
            symbol,
            date(2000 if index < 40 else 2010, 1, 1),
            date(2010, 1, 1) if index < 40 else None,
        )
        for index, symbol in enumerate(symbols)
    )

    assert len(securities) == 81
    assert len(resolve_membership(intervals, date(2005, 1, 1)).symbols) == 40
    assert len(resolve_membership(intervals, date(2015, 1, 1)).symbols) == 40


def test_master_rejects_missing_or_wrong_benchmark(tmp_path: Path) -> None:
    path = tmp_path / "master.csv"
    _write_master(path, [_metadata_row("AAA")])
    with pytest.raises(HistoricalSecurityMasterError, match="configured benchmark"):
        load_historical_security_master(path, benchmark="SPY")


def test_filter_rejects_missing_metadata_and_active_cap(tmp_path: Path) -> None:
    path = tmp_path / "master.csv"
    symbols = [f"S{index:03d}" for index in range(51)]
    _write_master(path, [_metadata_row("SPY", benchmark=True), *map(_metadata_row, symbols)])
    securities = load_historical_security_master(path, benchmark="SPY")
    config = load_config(ROOT / "config.example.yaml")
    as_of = date(2020, 1, 1)

    missing = (MembershipInterval("pit-v1", "UNKNOWN", as_of, None),)
    with pytest.raises(PointInTimeUniverseError, match="lacks instrument metadata"):
        filter_point_in_time_universe((), securities, missing, as_of, config)

    too_many = tuple(MembershipInterval("pit-v1", symbol, as_of, None) for symbol in symbols)
    with pytest.raises(PointInTimeUniverseError, match="active membership exceeds"):
        filter_point_in_time_universe((), securities, too_many, as_of, config)
