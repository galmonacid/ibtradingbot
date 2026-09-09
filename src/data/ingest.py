"""Deterministic, quarantine-first ingestion of research daily bars."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from src.config.settings import AppConfig

CANONICAL_COLUMNS = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)


class IngestionError(ValueError):
    """Raised when a daily-bar source cannot be interpreted as the canonical schema."""


@dataclass(frozen=True, order=True)
class PriceBar:
    """A validated immutable daily price observation."""

    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


@dataclass(frozen=True)
class QuarantinedRecord:
    """An unusable source row and every reason it was quarantined."""

    values: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class QualityNotice:
    """A usable row with an explicit condition that deserves provenance."""

    line_number: int
    values: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class IngestionResult:
    """Canonical valid bars, quarantined rows, and immutable source identity."""

    bars: tuple[PriceBar, ...]
    quarantined: tuple[QuarantinedRecord, ...]
    notices: tuple[QualityNotice, ...]
    source_sha256: str


@dataclass(frozen=True)
class _ParsedRow:
    line_number: int
    values: tuple[tuple[str, str], ...]
    bar: PriceBar


def _frozen_values(row: dict[str, str | None]) -> tuple[tuple[str, str], ...]:
    return tuple((key, "" if row.get(key) is None else str(row[key])) for key in CANONICAL_COLUMNS)


def _parse_row(line_number: int, row: dict[str, str | None]) -> tuple[_ParsedRow | None, list[str]]:
    values = _frozen_values(row)
    reasons: list[str] = []
    if None in row:
        reasons.append("unexpected_columns")
    if None in row or any(row.get(column) is None for column in CANONICAL_COLUMNS):
        reasons.append("invalid_column_count")
    try:
        bar_date = date.fromisoformat(values[0][1])
    except ValueError:
        bar_date = date.min
        reasons.append("invalid_date")
    symbol = values[1][1].strip().upper()
    if not symbol:
        reasons.append("blank_symbol")
    try:
        prices = tuple(float(value) for _, value in values[2:7])
        prices_valid = True
    except ValueError:
        prices = (math.nan,) * 5
        prices_valid = False
        reasons.append("invalid_price_type")
    try:
        volume = int(values[7][1])
        volume_valid = True
    except ValueError:
        volume = 0
        volume_valid = False
        reasons.append("invalid_volume_type")
    if prices_valid:
        opening, high, low, close, adjusted_close = prices
        if not all(math.isfinite(value) for value in prices):
            reasons.append("non_finite_price")
        if any(value <= 0 for value in prices):
            reasons.append("non_positive_price")
        if low > min(opening, close) or high < max(opening, close) or high < low:
            reasons.append("impossible_ohlc")
    if volume_valid and volume <= 0:
        reasons.append("non_positive_volume")
    if reasons:
        return None, reasons
    return (
        _ParsedRow(
            line_number=line_number,
            values=values,
            bar=PriceBar(
                date=bar_date,
                symbol=symbol,
                open=prices[0],
                high=prices[1],
                low=prices[2],
                close=prices[3],
                adjusted_close=prices[4],
                volume=volume,
            ),
        ),
        [],
    )


def ingest_daily_bars(path: Path, config: AppConfig) -> IngestionResult:
    """Read CSV bars, retaining valid rows and quarantining defects deterministically.

    Output bar and quarantine ordering does not depend on source row order. Duplicate
    keys quarantine every occurrence, avoiding an arbitrary "first row wins" repair.
    """
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise IngestionError(f"cannot read daily bars {path}: {error}") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IngestionError("daily bars must be UTF-8") from error

    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None or tuple(reader.fieldnames) != CANONICAL_COLUMNS:
        raise IngestionError("daily bars must use the exact canonical column order")

    parsed: list[_ParsedRow] = []
    quarantined: list[QuarantinedRecord] = []
    for line_number, row in enumerate(reader, start=2):
        candidate, reasons = _parse_row(line_number, row)
        if candidate is None:
            quarantined.append(
                QuarantinedRecord(_frozen_values(row), tuple(sorted(reasons)))
            )
        else:
            parsed.append(candidate)

    by_key: dict[tuple[date, str], list[_ParsedRow]] = defaultdict(list)
    for candidate in parsed:
        by_key[(candidate.bar.date, candidate.bar.symbol)].append(candidate)
    unique: list[_ParsedRow] = []
    for candidates in by_key.values():
        if len(candidates) == 1:
            unique.append(candidates[0])
        else:
            for candidate in candidates:
                quarantined.append(
                    QuarantinedRecord(candidate.values, ("duplicate_key",))
                )

    anomaly_reasons: dict[_ParsedRow, set[str]] = defaultdict(set)
    notice_reasons: dict[_ParsedRow, set[str]] = defaultdict(set)
    by_symbol: dict[str, list[_ParsedRow]] = defaultdict(list)
    for candidate in unique:
        by_symbol[candidate.bar.symbol].append(candidate)
    for candidates in by_symbol.values():
        source_order = sorted(candidates, key=lambda item: item.line_number)
        for previous, current in zip(source_order, source_order[1:], strict=False):
            if current.bar.date <= previous.bar.date:
                anomaly_reasons[current].add("non_monotonic_date")
        candidates.sort(key=lambda item: item.bar.date)
        for previous, current in zip(candidates, candidates[1:], strict=False):
            adjusted_move = abs(current.bar.adjusted_close / previous.bar.adjusted_close - 1)
            if adjusted_move >= config.suspicious_adjusted_move:
                anomaly_reasons[current].add("suspicious_adjusted_move")
            raw_ratio = max(
                current.bar.close / previous.bar.close,
                previous.bar.close / current.bar.close,
            )
            if (
                raw_ratio >= config.likely_split_min_ratio
                and adjusted_move <= config.likely_split_adjusted_tolerance
            ):
                notice_reasons[current].add("adjusted_split_detected")

        run_start = 0
        while run_start < len(candidates):
            run_end = run_start + 1
            price = candidates[run_start].bar.adjusted_close
            while run_end < len(candidates) and candidates[run_end].bar.adjusted_close == price:
                run_end += 1
            if run_end - run_start >= config.stale_adjusted_price_sessions:
                first_stale = run_start + config.stale_adjusted_price_sessions - 1
                for candidate in candidates[first_stale:run_end]:
                    anomaly_reasons[candidate].add("stale_adjusted_price")
            run_start = run_end

    valid: list[PriceBar] = []
    notices: list[QualityNotice] = []
    for candidate in unique:
        detected_anomalies = anomaly_reasons.get(candidate)
        if detected_anomalies:
            quarantined.append(
                QuarantinedRecord(
                    candidate.values,
                    tuple(sorted(detected_anomalies)),
                )
            )
        else:
            valid.append(candidate.bar)
            candidate_notices = notice_reasons.get(candidate)
            if candidate_notices:
                notices.append(
                    QualityNotice(
                        candidate.line_number,
                        candidate.values,
                        tuple(sorted(candidate_notices)),
                    )
                )

    valid.sort(key=lambda bar: (bar.date, bar.symbol))
    quarantined.sort(key=lambda item: (item.values, item.reasons))
    notices.sort(key=lambda item: (item.values, item.reasons))
    return IngestionResult(
        tuple(valid),
        tuple(quarantined),
        tuple(notices),
        sha256(raw).hexdigest(),
    )
