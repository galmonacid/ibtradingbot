"""Source-native parsing for independent S&P 500 membership QA snapshots.

These observations intentionally retain only what the independent source says.  In
particular, they do not borrow security identifiers or event dates from the primary
membership dataset; identity resolution and date-tolerance matching belong at the
later audit boundary.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal


class SourceNativeQaError(ValueError):
    """Raised when a native QA snapshot cannot be interpreted safely."""


ISHARES_IVV_ROLE: Literal["riazarbi/sp500-scraper:ishares/ivv"] = (
    "riazarbi/sp500-scraper:ishares/ivv"
)
WIKIPEDIA_ROLE: Literal["riazarbi/sp500-scraper:wikipedia/sp500"] = (
    "riazarbi/sp500-scraper:wikipedia/sp500"
)
SourceRole = Literal[
    "riazarbi/sp500-scraper:ishares/ivv",
    "riazarbi/sp500-scraper:wikipedia/sp500",
]
ChangeAction = Literal["add", "remove"]

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]*$")
_ISHARES_SYMBOL = re.compile(r"^[A-Za-z0-9*./ -]{1,32}$")
_ISHARES_COLUMNS = (
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
)
_WIKIPEDIA_COLUMNS = {
    (
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
    ),
    (
        "Symbol",
        "Security",
        "SEC filings",
        "GICS Sector",
        "GICS Sub-Industry",
        "Headquarters Location",
        "Date added",
        "CIK",
        "Founded",
        "date",
    ),
    (
        "Symbol",
        "GICS Sector",
        "GICS Sub-Industry",
        "Headquarters Location",
        "Date added",
        "CIK",
        "Founded",
        "date",
    ),
    (
        "Symbol",
        "Security",
        "GICS Sector",
        "GICS Sub-Industry",
        "Headquarters Location",
        "Date added",
        "CIK",
        "Founded",
        "date",
    ),
    (
        "Symbol",
        "Company",
        "GICS Sector",
        "GICS Sub-Industry",
        "Headquarters Location",
        "Date added",
        "CIK",
        "Founded",
        "date",
    ),
}
_SHIFTED_WIKIPEDIA_COLUMNS = tuple(f"X{number}" for number in range(1, 18)) + ("date",)
_SHIFTED_EMBEDDED_HEADER = (
    "Symbol",
    "Security",
    "GICS Sector",
    "GICS Sub-Industry",
    "Headquarters Location",
    "Date added",
    "CIK",
    "Founded",
)


@dataclass(frozen=True, order=True)
class NativeMembershipSnapshot:
    """One source's membership assertion on its own observation date."""

    source_role: SourceRole
    as_of: date
    symbols: tuple[str, ...]


@dataclass(frozen=True, order=True)
class NativeChangeObservation:
    """A change inferred solely from two consecutive source snapshots."""

    source_role: SourceRole
    observed_on: date
    symbol: str
    action: ChangeAction


def parse_riazarbi_snapshot_directory(
    directory: Path,
    *,
    source_role: SourceRole,
    minimum_members: int = 450,
    maximum_members: int = 550,
) -> tuple[NativeMembershipSnapshot, ...]:
    """Parse one pinned riazarb dataset directory of ``YYYYMMDD.csv`` files."""
    if source_role not in {ISHARES_IVV_ROLE, WIKIPEDIA_ROLE}:
        raise SourceNativeQaError("unsupported source role")
    if minimum_members <= 0 or maximum_members < minimum_members:
        raise SourceNativeQaError("membership count bounds are invalid")
    if not directory.is_dir():
        raise SourceNativeQaError("snapshot directory does not exist")
    paths = sorted(directory.glob("*.csv"))
    if not paths:
        raise SourceNativeQaError("snapshot directory contains no CSV files")

    snapshots: list[NativeMembershipSnapshot] = []
    for path in paths:
        as_of = _filename_date(path)
        symbols = _parse_snapshot(path, as_of, source_role)
        if not minimum_members <= len(symbols) <= maximum_members:
            raise SourceNativeQaError(f"membership count outside configured bounds in {path.name}")
        snapshots.append(NativeMembershipSnapshot(source_role, as_of, symbols))
    if any(
        left.as_of >= right.as_of for left, right in zip(snapshots, snapshots[1:], strict=False)
    ):
        raise SourceNativeQaError("snapshot dates must be unique and strictly increasing")
    return tuple(snapshots)


def derive_native_change_observations(
    snapshots: tuple[NativeMembershipSnapshot, ...],
) -> tuple[NativeChangeObservation, ...]:
    """Diff consecutive snapshots, dating each observation at the later snapshot."""
    observations: list[NativeChangeObservation] = []
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        if previous.source_role != current.source_role:
            raise SourceNativeQaError("cannot diff snapshots from different source roles")
        if previous.as_of >= current.as_of:
            raise SourceNativeQaError("snapshots must be strictly chronological")
        old, new = set(previous.symbols), set(current.symbols)
        observations.extend(
            NativeChangeObservation(current.source_role, current.as_of, symbol, "remove")
            for symbol in sorted(old - new)
        )
        observations.extend(
            NativeChangeObservation(current.source_role, current.as_of, symbol, "add")
            for symbol in sorted(new - old)
        )
    return tuple(observations)


def _filename_date(path: Path) -> date:
    if not re.fullmatch(r"\d{8}", path.stem):
        raise SourceNativeQaError(f"snapshot filename is not YYYYMMDD: {path.name}")
    try:
        parsed = date.fromisoformat(f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:]}")
    except ValueError as error:
        raise SourceNativeQaError(
            f"snapshot filename contains an invalid date: {path.name}"
        ) from error
    return parsed


def _parse_snapshot(path: Path, as_of: date, source_role: SourceRole) -> tuple[str, ...]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as error:
        raise SourceNativeQaError(f"cannot read snapshot {path.name}") from error
    with handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        if source_role == ISHARES_IVV_ROLE:
            if columns != _ISHARES_COLUMNS:
                raise SourceNativeQaError(f"unsupported iShares IVV schema in {path.name}")
            symbol_column = "symbol"
        else:
            shifted_wikipedia = columns == _SHIFTED_WIKIPEDIA_COLUMNS
            if columns not in _WIKIPEDIA_COLUMNS and not shifted_wikipedia:
                raise SourceNativeQaError(f"unsupported Wikipedia schema in {path.name}")
            symbol_column = "X1" if shifted_wikipedia else "Symbol"

        symbols: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise SourceNativeQaError(f"malformed row {line_number} in {path.name}")
            if row["date"] != as_of.isoformat():
                raise SourceNativeQaError(f"row date disagrees with filename in {path.name}")
            if source_role == WIKIPEDIA_ROLE and shifted_wikipedia and line_number == 2:
                if (
                    tuple(row[f"X{number}"] for number in range(1, 9)) != _SHIFTED_EMBEDDED_HEADER
                    or row["X9"]
                    or any(not row[f"X{number}"] for number in range(10, 18))
                ):
                    raise SourceNativeQaError(
                        f"unrecognized shifted Wikipedia header in {path.name}"
                    )
                embedded_symbol = row["X10"].strip()
                if not _SYMBOL.fullmatch(embedded_symbol):
                    raise SourceNativeQaError(f"invalid shifted constituent symbol in {path.name}")
                symbols.add(embedded_symbol)
                continue
            if (
                source_role == WIKIPEDIA_ROLE
                and shifted_wikipedia
                and any(row[f"X{number}"] for number in range(9, 18))
            ):
                raise SourceNativeQaError(f"unexpected shifted fields in {path.name}")
            if source_role == ISHARES_IVV_ROLE and row["asset_class"].strip() != "Equity":
                continue
            symbol = row[symbol_column].strip()
            symbol_pattern = _ISHARES_SYMBOL if source_role == ISHARES_IVV_ROLE else _SYMBOL
            if not symbol_pattern.fullmatch(symbol):
                raise SourceNativeQaError(
                    f"invalid constituent symbol on line {line_number} in {path.name}"
                )
            if symbol in symbols:
                if source_role == ISHARES_IVV_ROLE:
                    # Holdings exports may split one issuer position across tax lots.
                    continue
                raise SourceNativeQaError(f"duplicate constituent symbol in {path.name}")
            symbols.add(symbol)
    if not symbols:
        raise SourceNativeQaError(f"snapshot contains no constituents: {path.name}")
    return tuple(sorted(symbols))
