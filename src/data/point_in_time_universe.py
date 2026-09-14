"""Versioned point-in-time universe membership intervals.

Intervals use an inclusive ``effective_from`` and an exclusive ``effective_to``.
An empty end date represents membership with no known end.  The loader only
describes historical membership; price, liquidity, and instrument eligibility
filters remain the responsibility of the existing universe filtering layer.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.config.settings import AppConfig
from src.data.ingest import PriceBar
from src.data.universe import UniverseSecurity, UniverseSelection, filter_universe

POINT_IN_TIME_UNIVERSE_COLUMNS = (
    "source_version",
    "symbol",
    "effective_from",
    "effective_to",
)


class PointInTimeUniverseError(ValueError):
    """Raised when point-in-time membership data is not canonical or causal."""


@dataclass(frozen=True, order=True)
class MembershipInterval:
    source_version: str
    symbol: str
    effective_from: date
    effective_to: date | None

    def contains(self, as_of: date) -> bool:
        """Return whether the half-open interval contains ``as_of``."""
        return self.effective_from <= as_of and (
            self.effective_to is None or as_of < self.effective_to
        )


@dataclass(frozen=True)
class PointInTimeMembership:
    source_version: str
    as_of: date
    symbols: tuple[str, ...]


def _parse_date(value: str, field: str, line_number: int) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise PointInTimeUniverseError(
            f"{field} must be an ISO date on line {line_number}"
        ) from error
    if value != parsed.isoformat():
        raise PointInTimeUniverseError(
            f"{field} must use canonical YYYY-MM-DD format on line {line_number}"
        )
    return parsed


def load_membership_intervals(
    path: Path, *, expected_source_version: str | None = None
) -> tuple[MembershipInterval, ...]:
    """Load and validate canonical, non-overlapping membership intervals."""
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise PointInTimeUniverseError(
            f"cannot read point-in-time universe {path}: {error}"
        ) from error

    intervals: list[MembershipInterval] = []
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != POINT_IN_TIME_UNIVERSE_COLUMNS:
            raise PointInTimeUniverseError(
                "point-in-time universe must use the exact canonical column order"
            )
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise PointInTimeUniverseError(f"malformed membership row on line {line_number}")
            source_version = row["source_version"].strip()
            symbol_value = row["symbol"].strip()
            if not source_version:
                raise PointInTimeUniverseError(f"blank source_version on line {line_number}")
            if not symbol_value or symbol_value != symbol_value.upper():
                raise PointInTimeUniverseError(
                    f"symbol must be non-blank canonical uppercase on line {line_number}"
                )
            effective_from = _parse_date(
                row["effective_from"].strip(), "effective_from", line_number
            )
            end_value = row["effective_to"].strip()
            effective_to = (
                _parse_date(end_value, "effective_to", line_number) if end_value else None
            )
            if effective_to is not None and effective_to <= effective_from:
                raise PointInTimeUniverseError(
                    f"effective_to must be after effective_from on line {line_number}"
                )
            intervals.append(
                MembershipInterval(source_version, symbol_value, effective_from, effective_to)
            )

    if not intervals:
        raise PointInTimeUniverseError("point-in-time universe contains no membership rows")
    versions = {interval.source_version for interval in intervals}
    if len(versions) != 1:
        raise PointInTimeUniverseError("membership rows must share exactly one source_version")
    source_version = next(iter(versions))
    if expected_source_version is not None and source_version != expected_source_version:
        raise PointInTimeUniverseError(
            "point-in-time universe source_version does not match the expected version"
        )

    ordered = sorted(intervals, key=lambda item: (item.symbol, item.effective_from))
    previous_by_symbol: dict[str, MembershipInterval] = {}
    for interval in ordered:
        previous = previous_by_symbol.get(interval.symbol)
        if previous is not None and (
            previous.effective_to is None or interval.effective_from < previous.effective_to
        ):
            raise PointInTimeUniverseError(
                f"overlapping membership intervals for {interval.symbol}"
            )
        previous_by_symbol[interval.symbol] = interval
    return tuple(ordered)


def resolve_membership(
    intervals: tuple[MembershipInterval, ...], as_of: date
) -> PointInTimeMembership:
    """Resolve membership using only intervals effective on ``as_of``."""
    if not intervals:
        raise PointInTimeUniverseError("cannot resolve empty membership intervals")
    versions = {interval.source_version for interval in intervals}
    if len(versions) != 1:
        raise PointInTimeUniverseError("membership intervals have inconsistent source versions")
    symbols = tuple(sorted(interval.symbol for interval in intervals if interval.contains(as_of)))
    if len(symbols) != len(set(symbols)):
        raise PointInTimeUniverseError("overlapping intervals produced duplicate active symbols")
    return PointInTimeMembership(next(iter(versions)), as_of, symbols)


def filter_point_in_time_universe(
    bars: tuple[PriceBar, ...],
    security_metadata: tuple[UniverseSecurity, ...],
    intervals: tuple[MembershipInterval, ...],
    as_of: date,
    config: AppConfig,
) -> UniverseSelection:
    """Intersect dated membership with instrument, history, price, and liquidity rules."""
    membership = resolve_membership(intervals, as_of)
    if config.benchmark in membership.symbols:
        raise PointInTimeUniverseError("benchmark must not appear in candidate membership")
    if len(membership.symbols) > config.universe_max_symbols:
        raise PointInTimeUniverseError(
            f"active membership exceeds configured maximum of {config.universe_max_symbols}"
        )
    by_symbol = {security.symbol: security for security in security_metadata}
    missing = sorted(set(membership.symbols) - set(by_symbol))
    if missing:
        raise PointInTimeUniverseError(
            "active membership lacks instrument metadata: " + ", ".join(missing)
        )
    benchmark = by_symbol.get(config.benchmark)
    if benchmark is None or not benchmark.is_benchmark:
        raise PointInTimeUniverseError("instrument metadata lacks the configured benchmark")
    active = (benchmark, *(by_symbol[symbol] for symbol in membership.symbols))
    selection = filter_universe(bars, tuple(active), as_of, config)
    return UniverseSelection(
        version=membership.source_version,
        as_of=selection.as_of,
        benchmark=selection.benchmark,
        eligible_symbols=selection.eligible_symbols,
        exclusions=selection.exclusions,
    )
