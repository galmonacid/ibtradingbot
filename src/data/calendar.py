"""Versioned trading-session calendars for causal weekly scheduling."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path


class CalendarError(ValueError):
    """Raised when a supplied session calendar is invalid."""


@dataclass(frozen=True)
class TradingCalendar:
    exchange: str
    version: str
    sessions: tuple[date, ...]
    week_ends: tuple[date, ...]
    source_sha256: str


def load_trading_calendar(path: Path) -> TradingCalendar:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CalendarError(f"cannot read trading calendar {path}: {error}") from error
    try:
        rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    except UnicodeDecodeError as error:
        raise CalendarError("trading calendar must be UTF-8") from error
    if not rows:
        raise CalendarError("trading calendar is empty")
    columns = ("exchange", "version", "date", "is_week_end")
    if tuple(rows[0]) != columns:
        raise CalendarError("trading calendar must use the canonical columns")
    sessions: list[date] = []
    week_ends: list[date] = []
    exchanges: set[str] = set()
    versions: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise CalendarError(f"malformed calendar row on line {line_number}")
        try:
            session = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError) as error:
            raise CalendarError(f"invalid calendar date on line {line_number}") from error
        exchange = row["exchange"].strip()
        version = row["version"].strip()
        is_week_end = row["is_week_end"].strip().lower()
        if not exchange or not version:
            raise CalendarError(f"blank calendar metadata on line {line_number}")
        if is_week_end not in ("true", "false"):
            raise CalendarError(f"invalid is_week_end flag on line {line_number}")
        if session.weekday() >= 5:
            raise CalendarError(f"weekend calendar session on line {line_number}")
        sessions.append(session)
        exchanges.add(exchange)
        versions.add(version)
        if is_week_end == "true":
            week_ends.append(session)
    if sessions != sorted(sessions) or len(sessions) != len(set(sessions)):
        raise CalendarError("trading calendar dates must be unique and increasing")
    if len(exchanges) != 1 or len(versions) != 1:
        raise CalendarError("calendar exchange and version must be consistent")
    if not week_ends:
        raise CalendarError("trading calendar contains no completed weeks")
    expected_week_ends: dict[tuple[int, int], date] = {}
    for session in sessions:
        iso = session.isocalendar()
        expected_week_ends[(iso.year, iso.week)] = session
    if set(week_ends) != set(expected_week_ends.values()):
        raise CalendarError("is_week_end must mark exactly the final session of every week")
    return TradingCalendar(
        exchanges.pop(),
        versions.pop(),
        tuple(sessions),
        tuple(week_ends),
        sha256(raw).hexdigest(),
    )


def weekly_signal_dates(
    available_sessions: tuple[date, ...], calendar: TradingCalendar
) -> tuple[date, ...]:
    """Return completed-week closes using known calendar sessions, not future prices."""

    available = set(available_sessions)
    return tuple(session for session in calendar.week_ends if session in available)
