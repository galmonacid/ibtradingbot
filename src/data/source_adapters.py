"""Strict adapters for the pinned open-source Phase 3 inputs."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.data.membership_audit import IndependentEvidence
from src.data.source_native_qa import (
    ISHARES_IVV_ROLE,
    WIKIPEDIA_ROLE,
    SourceRole,
    derive_native_change_observations,
    parse_riazarbi_snapshot_directory,
)
from src.data.trusted_historical import (
    MembershipSnapshot,
    SecurityIdentityInterval,
    VerifiedSourceSnapshot,
)


class SourceAdapterError(ValueError):
    """Raised when an upstream source does not match its pinned schema or semantics."""


_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]*$")
_MEMBERSHIP_COLUMNS = ("date", "tickers")
_EVENT_COLUMNS = (
    "event_date",
    "event_type",
    "old_symbol",
    "new_symbol",
    "old_name",
    "new_name",
    "source_url",
    "notes",
)
_EVENT_TYPES = {"ticker_change", "delisting", "name_change"}
_MEMBERSHIP_ATTESTATION = object()
_IDENTITY_ATTESTATION = object()
_AUDIT_EVIDENCE_ATTESTATION = object()
_NATIVE_AUDIT_EVIDENCE_ATTESTATION = object()
_DOCUMENTED_PRIMARY_SYMBOL_CORRECTIONS = {"RVTY (Previously PKI)": "RVTY"}


def _bound_file(snapshot: VerifiedSourceSnapshot, root: Path, relative_path: str) -> Path:
    matches = [row for row in snapshot.files if row.path == relative_path]
    if len(matches) != 1:
        raise SourceAdapterError("source data file is not present in its verified manifest")
    path = (root.resolve() / relative_path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise SourceAdapterError("source data file is missing or outside its snapshot root")
    if hashlib.sha256(path.read_bytes()).hexdigest() != matches[0].sha256:
        raise SourceAdapterError("source data file changed after manifest verification")
    return path


@dataclass(frozen=True)
class BoundMembershipSource:
    snapshot: VerifiedSourceSnapshot
    memberships: tuple[MembershipSnapshot, ...]
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _MEMBERSHIP_ATTESTATION:
            raise SourceAdapterError("membership source must be issued by the source transformer")


def transform_membership_source(
    snapshot: VerifiedSourceSnapshot, root: Path, relative_path: str
) -> BoundMembershipSource:
    if snapshot.source_name != "historical_sp500_constituents":
        raise SourceAdapterError("unexpected primary membership source role")
    path = _bound_file(snapshot, root, relative_path)
    memberships = parse_sp500_membership_snapshots(path)
    return BoundMembershipSource(snapshot, memberships, _MEMBERSHIP_ATTESTATION)


@dataclass(frozen=True)
class BoundAuditEvidenceSource:
    snapshot: VerifiedSourceSnapshot
    evidence: tuple[IndependentEvidence, ...]
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation not in {
            _AUDIT_EVIDENCE_ATTESTATION,
            _NATIVE_AUDIT_EVIDENCE_ATTESTATION,
        }:
            raise SourceAdapterError("QA evidence must be issued by the source transformer")

    @property
    def source_native(self) -> bool:
        return self._attestation is _NATIVE_AUDIT_EVIDENCE_ATTESTATION


def transform_audit_evidence_source(
    snapshot: VerifiedSourceSnapshot, root: Path, relative_path: str
) -> BoundAuditEvidenceSource:
    if snapshot.source_name not in {
        "riazarbi/sp500-scraper",
        "historical-index-etf-holdings",
    }:
        raise SourceAdapterError("unexpected independent audit source role")
    path = _bound_file(snapshot, root, relative_path)
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise SourceAdapterError("cannot read independent audit evidence") from error
    evidence: list[IndependentEvidence] = []
    with handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ("symbol", "action", "effective_date"):
            raise SourceAdapterError("unsupported independent audit evidence schema")
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise SourceAdapterError("malformed independent audit evidence row")
            evidence.append(
                IndependentEvidence(
                    snapshot.source_name,
                    _symbol(row["symbol"], "symbol", line_number),
                    row["action"].strip(),
                    _canonical_date(row["effective_date"], "effective_date", line_number),
                )
            )
    if not evidence:
        raise SourceAdapterError("independent audit evidence is empty")
    return BoundAuditEvidenceSource(snapshot, tuple(sorted(evidence)), _AUDIT_EVIDENCE_ATTESTATION)


def transform_riazarbi_audit_source(
    snapshot: VerifiedSourceSnapshot,
    root: Path,
    relative_directory: str,
    *,
    source_role: SourceRole,
) -> BoundAuditEvidenceSource:
    """Derive independent changes directly from a complete pinned snapshot directory."""
    expected_name = {
        WIKIPEDIA_ROLE: "riazarbi/sp500-scraper",
        ISHARES_IVV_ROLE: "historical-index-etf-holdings",
    }[source_role]
    if snapshot.source_name != expected_name:
        raise SourceAdapterError("QA source role does not match its verified manifest")
    directory = (root.resolve() / relative_directory).resolve()
    if not directory.is_relative_to(root.resolve()) or not directory.is_dir():
        raise SourceAdapterError("QA snapshot directory is missing or outside its source root")
    prefix = relative_directory.rstrip("/") + "/"
    manifested = {
        row.path
        for row in snapshot.files
        if row.path.startswith(prefix) and row.path.endswith(".csv")
    }
    actual = {
        path.relative_to(root.resolve()).as_posix()
        for path in directory.glob("*.csv")
        if path.is_file()
    }
    if not manifested or manifested != actual:
        raise SourceAdapterError("QA snapshot directory is not exactly covered by its manifest")
    try:
        observations = derive_native_change_observations(
            parse_riazarbi_snapshot_directory(directory, source_role=source_role)
        )
        evidence = tuple(
            IndependentEvidence(
                snapshot.source_name,
                observation.symbol,
                observation.action,
                observation.observed_on,
            )
            for observation in observations
        )
    except ValueError as error:
        raise SourceAdapterError(str(error)) from error
    if not evidence:
        raise SourceAdapterError("independent QA snapshots contain no membership changes")
    return BoundAuditEvidenceSource(snapshot, evidence, _NATIVE_AUDIT_EVIDENCE_ATTESTATION)


def _canonical_date(value: str, field: str, line_number: int) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise SourceAdapterError(f"{field} must be an ISO date on line {line_number}") from error
    if parsed.isoformat() != value:
        raise SourceAdapterError(
            f"{field} must use canonical YYYY-MM-DD format on line {line_number}"
        )
    return parsed


def _symbol(value: str, field: str, line_number: int, *, optional: bool = False) -> str:
    candidate = value.strip()
    if optional and not candidate:
        return ""
    if not _SYMBOL.fullmatch(candidate):
        raise SourceAdapterError(f"{field} is not a canonical US ticker on line {line_number}")
    return candidate


def parse_sp500_membership_snapshots(
    path: Path, *, minimum_members: int = 440, maximum_members: int = 550
) -> tuple[MembershipSnapshot, ...]:
    """Parse the fja05680/chinobing ``date,tickers`` snapshot format."""
    if minimum_members <= 0 or maximum_members < minimum_members:
        raise SourceAdapterError("membership count bounds are invalid")
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise SourceAdapterError(f"cannot read membership snapshots {path}: {error}") from error
    snapshots: list[MembershipSnapshot] = []
    with handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _MEMBERSHIP_COLUMNS:
            raise SourceAdapterError("unsupported membership schema; expected exactly date,tickers")
        previous: date | None = None
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise SourceAdapterError(f"malformed membership row on line {line_number}")
            as_of = _canonical_date(row["date"], "date", line_number)
            if previous is not None and as_of < previous:
                raise SourceAdapterError("membership snapshot dates must be non-decreasing")
            raw_symbols = row["tickers"].split(",")
            symbols = tuple(
                _symbol(
                    _DOCUMENTED_PRIMARY_SYMBOL_CORRECTIONS.get(value, value),
                    "ticker",
                    line_number,
                )
                for value in raw_symbols
            )
            if len(symbols) != len(set(symbols)):
                raise SourceAdapterError(f"duplicate ticker in membership row {line_number}")
            if not minimum_members <= len(symbols) <= maximum_members:
                raise SourceAdapterError(
                    f"membership count outside [{minimum_members}, {maximum_members}] "
                    f"on line {line_number}"
                )
            snapshot = MembershipSnapshot(as_of, tuple(sorted(symbols)))
            if previous == as_of:
                # The upstream change log can contain multiple same-day transitions. Research
                # signals are formed after close, so the final row is the dated EOD membership.
                snapshots[-1] = snapshot
            else:
                snapshots.append(snapshot)
            previous = as_of
    if not snapshots:
        raise SourceAdapterError("membership snapshot file is empty")
    return tuple(snapshots)


@dataclass(frozen=True, order=True)
class ConstitutionEvent:
    event_date: date
    event_type: str
    old_symbol: str
    new_symbol: str | None
    old_name: str
    new_name: str | None
    source_url: str
    notes: str


@dataclass(frozen=True, order=True)
class TickerChange:
    event_date: date
    old_symbol: str
    new_symbol: str


@dataclass(frozen=True, order=True)
class DelistingRecord:
    event_date: date
    symbol: str
    successor_symbol: str | None


@dataclass(frozen=True)
class ParsedConstitutionEvents:
    events: tuple[ConstitutionEvent, ...]
    ticker_changes: tuple[TickerChange, ...]
    delistings: tuple[DelistingRecord, ...]
    identity_intervals: tuple[SecurityIdentityInterval, ...]


@dataclass(frozen=True)
class BoundIdentitySource:
    snapshot: VerifiedSourceSnapshot
    parsed: ParsedConstitutionEvents
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _IDENTITY_ATTESTATION:
            raise SourceAdapterError("identity source must be issued by the source transformer")


def _security_id(root: str) -> str:
    digest = hashlib.sha256(f"index-constitution-us:{root}".encode()).hexdigest()[:16]
    return f"IC-US-{digest}"


def _identity_intervals(
    events: tuple[ConstitutionEvent, ...],
    coverage_start: date,
    known_symbols: tuple[str, ...],
) -> tuple[SecurityIdentityInterval, ...]:
    change_events = [event for event in events if event.event_type == "ticker_change"]
    if len({event.old_symbol for event in change_events}) != len(change_events):
        raise SourceAdapterError("ticker has multiple successor events")
    changes = {event.old_symbol: event for event in change_events}
    incoming: dict[str, str] = {}
    for event in changes.values():
        assert event.new_symbol is not None
        if event.new_symbol in incoming:
            raise SourceAdapterError(f"multiple ticker predecessors for {event.new_symbol}")
        incoming[event.new_symbol] = event.old_symbol
    symbols = {
        symbol
        for event in events
        for symbol in (event.old_symbol, event.new_symbol)
        if symbol is not None
    }
    for symbol in known_symbols:
        _symbol(symbol, "known_symbol", 0)
        symbols.add(symbol)
    roots = sorted(symbols - set(incoming))
    visited: set[str] = set()
    rows: list[SecurityIdentityInterval] = []
    delisting_events = [event for event in events if event.event_type == "delisting"]
    if len({event.old_symbol for event in delisting_events}) != len(delisting_events):
        raise SourceAdapterError("ticker has multiple delisting events")
    delisted = {event.old_symbol: event.event_date for event in delisting_events}
    for root in roots:
        security_id = _security_id(root)
        current = root
        started = coverage_start
        chain: set[str] = set()
        while True:
            if current in chain:
                raise SourceAdapterError("ticker-change graph contains a cycle")
            chain.add(current)
            visited.add(current)
            change = changes.get(current)
            terminal = delisted.get(current)
            if change is not None and terminal is not None:
                raise SourceAdapterError(f"ticker {current} both changes and delists")
            ended = change.event_date if change is not None else terminal
            if ended is None or ended > coverage_start:
                effective_from = max(started, coverage_start)
                if ended is None or ended > effective_from:
                    rows.append(
                        SecurityIdentityInterval(security_id, current, effective_from, ended)
                    )
            if change is None:
                break
            assert change.new_symbol is not None
            started = change.event_date
            current = change.new_symbol
    if visited != symbols:
        raise SourceAdapterError("ticker-change graph contains a cycle or unreachable identity")
    return tuple(sorted(rows, key=lambda row: (row.security_id, row.effective_from)))


def _temporal_identity_intervals(
    events: tuple[ConstitutionEvent, ...],
    coverage_start: date,
    known_symbols: tuple[str, ...],
) -> tuple[SecurityIdentityInterval, ...]:
    """Build event-time identities without merging a successor's earlier symbol history."""
    symbols = {
        symbol
        for event in events
        for symbol in (event.old_symbol, event.new_symbol)
        if symbol is not None
    } | set(known_symbols)
    active = {symbol: (_security_id(symbol), coverage_start) for symbol in symbols}
    rows: list[SecurityIdentityInterval] = []
    for event in events:
        if event.event_type == "ticker_change":
            assert event.new_symbol is not None
            old = active.pop(event.old_symbol, None)
            if old is None:
                old = (_security_id(event.old_symbol), coverage_start)
            old_security, old_started = old
            if old_started < event.event_date:
                rows.append(
                    SecurityIdentityInterval(
                        old_security, event.old_symbol, old_started, event.event_date
                    )
                )
            replaced = active.pop(event.new_symbol, None)
            if replaced is not None and replaced[1] < event.event_date:
                rows.append(
                    SecurityIdentityInterval(
                        replaced[0], event.new_symbol, replaced[1], event.event_date
                    )
                )
            active[event.new_symbol] = (old_security, event.event_date)
        elif event.event_type == "delisting":
            ended = active.pop(event.old_symbol, None)
            if ended is not None and ended[1] < event.event_date:
                rows.append(
                    SecurityIdentityInterval(
                        ended[0], event.old_symbol, ended[1], event.event_date
                    )
                )
    rows.extend(
        SecurityIdentityInterval(security_id, symbol, started, None)
        for symbol, (security_id, started) in active.items()
    )
    return tuple(sorted(rows, key=lambda row: (row.security_id, row.effective_from, row.symbol)))


def parse_index_constitution_events(
    path: Path,
    *,
    coverage_start: date,
    known_symbols: tuple[str, ...] = (),
    preserve_symbol_reuse: bool = False,
) -> ParsedConstitutionEvents:
    """Parse pinned ``event/us.csv`` and derive conservative identity histories."""
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise SourceAdapterError(
            f"cannot read index-constitution events {path}: {error}"
        ) from error
    events: list[ConstitutionEvent] = []
    with handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _EVENT_COLUMNS:
            raise SourceAdapterError(
                "unsupported index-constitution event schema; expected canonical event/us.csv"
            )
        seen: set[tuple[date, str, str]] = set()
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise SourceAdapterError(f"malformed event row on line {line_number}")
            event_date = _canonical_date(row["event_date"], "event_date", line_number)
            event_type = row["event_type"].strip()
            if event_type not in _EVENT_TYPES:
                raise SourceAdapterError(f"unsupported event_type on line {line_number}")
            old_symbol = _symbol(row["old_symbol"], "old_symbol", line_number)
            new_value = _symbol(row["new_symbol"], "new_symbol", line_number, optional=True)
            new_symbol = new_value or None
            old_name = row["old_name"].strip()
            new_name = row["new_name"].strip() or None
            source_url = row["source_url"].strip()
            notes = row["notes"].strip()
            if not old_name or not source_url.startswith(("https://", "http://")) or not notes:
                raise SourceAdapterError(f"event evidence is incomplete on line {line_number}")
            if event_type == "ticker_change" and (
                new_symbol is None or new_symbol == old_symbol or new_name is None
            ):
                raise SourceAdapterError(f"ticker_change is incomplete on line {line_number}")
            if event_type == "name_change" and (new_symbol is not None or new_name is None):
                raise SourceAdapterError(f"name_change is inconsistent on line {line_number}")
            if event_type == "delisting" and new_symbol is None and new_name is not None:
                raise SourceAdapterError(
                    f"delisting successor fields are inconsistent on line {line_number}"
                )
            key = (event_date, event_type, old_symbol)
            if key in seen:
                raise SourceAdapterError("duplicate index-constitution event")
            seen.add(key)
            events.append(
                ConstitutionEvent(
                    event_date,
                    event_type,
                    old_symbol,
                    new_symbol,
                    old_name,
                    new_name,
                    source_url,
                    notes,
                )
            )
    if not events:
        raise SourceAdapterError("index-constitution event file is empty")
    normalized = tuple(sorted(events))
    changes = tuple(
        TickerChange(event.event_date, event.old_symbol, event.new_symbol)
        for event in normalized
        if event.event_type == "ticker_change" and event.new_symbol is not None
    )
    delistings = tuple(
        DelistingRecord(event.event_date, event.old_symbol, event.new_symbol)
        for event in normalized
        if event.event_type == "delisting"
    )
    return ParsedConstitutionEvents(
        normalized,
        changes,
        delistings,
        (
            _temporal_identity_intervals(normalized, coverage_start, known_symbols)
            if preserve_symbol_reuse
            else _identity_intervals(normalized, coverage_start, known_symbols)
        ),
    )


def transform_identity_source(
    snapshot: VerifiedSourceSnapshot,
    root: Path,
    relative_path: str,
    *,
    coverage_start: date,
    known_symbols: tuple[str, ...],
    preserve_symbol_reuse: bool = False,
) -> BoundIdentitySource:
    if snapshot.source_name != "unliftedq/index-constitution":
        raise SourceAdapterError("unexpected identity source role")
    path = _bound_file(snapshot, root, relative_path)
    parsed = parse_index_constitution_events(
        path,
        coverage_start=coverage_start,
        known_symbols=known_symbols,
        preserve_symbol_reuse=preserve_symbol_reuse,
    )
    return BoundIdentitySource(snapshot, parsed, _IDENTITY_ATTESTATION)
