from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from src.data.source_native_qa import (
    ISHARES_IVV_ROLE,
    WIKIPEDIA_ROLE,
    NativeChangeObservation,
    SourceNativeQaError,
    derive_native_change_observations,
    parse_riazarbi_snapshot_directory,
)

ISHARES_HEADER = [
    "symbol",
    "name",
    "sector",
    "asset_class",
    "market_value",
    "weight_pct",
    "notional_value",
    "shares",
    "CUSIP",
    "ISIN",
    "SEDOL",
    "price",
    "location",
    "exchange",
    "market_currency",
    "fx_rate",
    "accrual_date",
    "date",
]
WIKI_OLD_HEADER = [
    "Symbol",
    "Security",
    "SEC filings",
    "GICS Sector",
    "GICS Sub-Industry",
    "Headquarters Location",
    "Date first added",
    "CIK",
    "Founded",
    "date",
]
WIKI_CURRENT_HEADER = [
    "Symbol",
    "Security",
    "GICS Sector",
    "GICS Sub-Industry",
    "Headquarters Location",
    "Date added",
    "CIK",
    "Founded",
    "date",
]


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _ivv(symbol: str, asset_class: str, day: str) -> list[str]:
    return [
        symbol,
        symbol,
        "Industrials",
        asset_class,
        "1",
        "1",
        "1",
        "1",
        "x",
        "x",
        "x",
        "1",
        "United States",
        "NYSE",
        "USD",
        "1",
        "-",
        day,
    ]


def test_ivv_filters_cash_and_derives_source_native_changes(tmp_path: Path) -> None:
    _write(
        tmp_path / "20240102.csv",
        ISHARES_HEADER,
        [
            _ivv("AAA", "Equity", "2024-01-02"),
            _ivv("BBB", "Equity", "2024-01-02"),
            _ivv("USD", "Cash", "2024-01-02"),
        ],
    )
    _write(
        tmp_path / "20240103.csv",
        ISHARES_HEADER,
        [
            _ivv("BBB", "Equity", "2024-01-03"),
            _ivv("CCC", "Equity", "2024-01-03"),
        ],
    )

    snapshots = parse_riazarbi_snapshot_directory(
        tmp_path, source_role=ISHARES_IVV_ROLE, minimum_members=2, maximum_members=3
    )

    assert snapshots[0].symbols == ("AAA", "BBB")
    assert derive_native_change_observations(snapshots) == (
        NativeChangeObservation(ISHARES_IVV_ROLE, date(2024, 1, 3), "AAA", "remove"),
        NativeChangeObservation(ISHARES_IVV_ROLE, date(2024, 1, 3), "CCC", "add"),
    )


def test_ivv_preserves_provider_native_symbol_notation(tmp_path: Path) -> None:
    _write(
        tmp_path / "20061031.csv",
        ISHARES_HEADER,
        [
            _ivv("AHEB GR", "Equity", "2006-10-31"),
            _ivv("FCX*", "Equity", "2006-10-31"),
            _ivv("FCX*", "Equity", "2006-10-31"),
        ],
    )

    snapshots = parse_riazarbi_snapshot_directory(
        tmp_path, source_role=ISHARES_IVV_ROLE, minimum_members=2, maximum_members=2
    )

    assert snapshots[0].symbols == ("AHEB GR", "FCX*")


@pytest.mark.parametrize("header", [WIKI_OLD_HEADER, WIKI_CURRENT_HEADER])
def test_wikipedia_accepts_real_schema_generations(tmp_path: Path, header: list[str]) -> None:
    day = "2023-03-27"
    row_by_column = {
        "Symbol": "BRK.B",
        "Security": "Berkshire Hathaway",
        "SEC filings": "reports",
        "GICS Sector": "Financials",
        "GICS Sub-Industry": "Multi-Sector Holdings",
        "Headquarters Location": "Omaha, Nebraska",
        "Date first added": "2010-02-16",
        "Date added": "2010-02-16",
        "CIK": "1067983",
        "Founded": "1839",
        "date": day,
    }
    _write(tmp_path / "20230327.csv", header, [[row_by_column[column] for column in header]])

    snapshots = parse_riazarbi_snapshot_directory(
        tmp_path, source_role=WIKIPEDIA_ROLE, minimum_members=1, maximum_members=1
    )

    assert snapshots[0].symbols == ("BRK.B",)


def test_recovers_exact_known_shifted_wikipedia_snapshot(tmp_path: Path) -> None:
    header = [*(f"X{number}" for number in range(1, 18)), "date"]
    shifted_header = [
        "Symbol",
        "Security",
        "GICS Sector",
        "GICS Sub-Industry",
        "Headquarters Location",
        "Date added",
        "CIK",
        "Founded",
        "",
        "MMM",
        "3M",
        "Industrials",
        "Industrial Conglomerates",
        "Saint Paul, Minnesota",
        "1957-03-04",
        "66740",
        "1902",
        "2024-02-05",
    ]
    normal_row = [
        "AOS",
        "A. O. Smith",
        "Industrials",
        "Building Products",
        "Milwaukee",
        "2017-07-26",
        "91142",
        "1916",
        *("" for _ in range(9)),
        "2024-02-05",
    ]
    _write(tmp_path / "20240205.csv", header, [shifted_header, normal_row])

    snapshots = parse_riazarbi_snapshot_directory(
        tmp_path, source_role=WIKIPEDIA_ROLE, minimum_members=2, maximum_members=2
    )
    assert snapshots[0].symbols == ("AOS", "MMM")


def test_rejects_row_date_that_does_not_match_filename(tmp_path: Path) -> None:
    _write(tmp_path / "20240102.csv", ISHARES_HEADER, [_ivv("AAA", "Equity", "2024-01-03")])

    with pytest.raises(SourceNativeQaError, match="row date disagrees"):
        parse_riazarbi_snapshot_directory(
            tmp_path, source_role=ISHARES_IVV_ROLE, minimum_members=1, maximum_members=1
        )
