"""Validation for daily-bar files used by the Phase 0 fixture pipeline."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REQUIRED_COLUMNS = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)


class DataQualityError(ValueError):
    """Raised when a daily-bar record cannot safely be used as a fixture."""


@dataclass(frozen=True)
class DailyBarSummary:
    row_count: int
    symbols: tuple[str, ...]
    first_date: str
    last_date: str


def validate_daily_bars(path: Path) -> DailyBarSummary:
    """Validate required fields and basic OHLCV integrity without correcting data."""
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise DataQualityError(f"cannot read daily bars {path}: {error}") from error
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or set(REQUIRED_COLUMNS) - set(reader.fieldnames):
            raise DataQualityError("daily bars are missing one or more required columns")
        seen: set[tuple[str, str]] = set()
        dates: list[date] = []
        symbols: set[str] = set()
        last_date_by_symbol: dict[str, date] = {}
        for line_number, row in enumerate(reader, start=2):
            try:
                bar_date = date.fromisoformat(row["date"])
                symbol = row["symbol"].strip()
                opening, high, low, close, adjusted_close = (
                    float(row[key]) for key in ("open", "high", "low", "close", "adjusted_close")
                )
                volume = int(row["volume"])
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid value on line {line_number}") from error
            if not symbol:
                raise DataQualityError(f"blank symbol on line {line_number}")
            if (bar_date.isoformat(), symbol) in seen:
                raise DataQualityError(f"duplicate date/symbol on line {line_number}")
            if not all(
                math.isfinite(value) for value in (opening, high, low, close, adjusted_close)
            ):
                raise DataQualityError(f"non-finite price on line {line_number}")
            if min(opening, high, low, close, adjusted_close) <= 0 or volume <= 0:
                raise DataQualityError(f"non-positive price or volume on line {line_number}")
            if low > min(opening, close) or high < max(opening, close) or high < low:
                raise DataQualityError(f"impossible OHLC relationship on line {line_number}")
            seen.add((bar_date.isoformat(), symbol))
            if symbol in last_date_by_symbol and bar_date <= last_date_by_symbol[symbol]:
                raise DataQualityError(f"non-monotonic date for {symbol} on line {line_number}")
            last_date_by_symbol[symbol] = bar_date
            dates.append(bar_date)
            symbols.add(symbol)
    if not dates:
        raise DataQualityError("daily bars file is empty")
    return DailyBarSummary(
        len(dates), tuple(sorted(symbols)), min(dates).isoformat(), max(dates).isoformat()
    )
