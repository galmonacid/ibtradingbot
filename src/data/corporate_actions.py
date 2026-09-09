"""Explicit corporate-action inputs required for delisting cash recovery."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

COLUMNS = ("date", "symbol", "event_type", "cash_per_share")


class CorporateActionsError(ValueError):
    """Raised when a corporate-action source is missing or malformed."""


@dataclass(frozen=True)
class DelistingEvent:
    date: date
    symbol: str
    cash_per_share: float

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("delisting symbol must not be blank")
        if not math.isfinite(self.cash_per_share) or self.cash_per_share < 0.0:
            raise ValueError("delisting cash_per_share must be finite and non-negative")


@dataclass(frozen=True)
class CorporateActions:
    delistings: tuple[DelistingEvent, ...]
    source_sha256: str


def load_corporate_actions(path: Path) -> CorporateActions:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CorporateActionsError(f"cannot read corporate actions {path}: {error}") from error
    try:
        reader = csv.DictReader(raw.decode("utf-8").splitlines())
        fieldnames = tuple(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise CorporateActionsError("corporate actions must be UTF-8") from error
    if fieldnames != COLUMNS:
        raise CorporateActionsError("corporate actions must use the canonical columns")
    events: list[DelistingEvent] = []
    for line_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise CorporateActionsError(f"malformed corporate action on line {line_number}")
        if row.get("event_type", "").strip().lower() != "delisting":
            raise CorporateActionsError(f"unsupported event_type on line {line_number}")
        try:
            event_date = date.fromisoformat(row["date"])
            cash_per_share = float(row["cash_per_share"])
        except (KeyError, TypeError, ValueError) as error:
            raise CorporateActionsError(
                f"invalid corporate action on line {line_number}"
            ) from error
        symbol = row.get("symbol", "").strip().upper()
        if not symbol or not math.isfinite(cash_per_share) or cash_per_share < 0.0:
            raise CorporateActionsError(f"invalid corporate action on line {line_number}")
        events.append(DelistingEvent(event_date, symbol, cash_per_share))
    keys = [(event.date, event.symbol) for event in events]
    if len(keys) != len(set(keys)):
        raise CorporateActionsError("duplicate corporate action")
    return CorporateActions(
        tuple(sorted(events, key=lambda event: (event.date, event.symbol))),
        sha256(raw).hexdigest(),
    )
