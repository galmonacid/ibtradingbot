"""Deterministic independent audit of constituent-change events."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from src.data.trusted_historical import DatedSecurityIdentity, MembershipSnapshot


class MembershipAuditError(ValueError):
    """Raised when an independent membership audit is not well formed."""


@dataclass(frozen=True, order=True)
class ConstituentChange:
    """A canonical add or remove event from the primary membership source."""

    event_id: str
    security_id: str
    symbol: str
    action: str
    effective_date: date

    def __post_init__(self) -> None:
        if not self.event_id or not self.security_id or not self.symbol:
            raise MembershipAuditError("event identifiers and symbol must be non-blank")
        if self.action not in {"add", "remove"}:
            raise MembershipAuditError("constituent action must be add or remove")


@dataclass(frozen=True, order=True)
class IndependentEvidence:
    """One source-native observation, deliberately free of primary identifiers."""

    source: str
    symbol: str
    action: str
    effective_date: date

    def __post_init__(self) -> None:
        if not self.source or not self.symbol:
            raise MembershipAuditError("independent source and symbol must be non-blank")
        if self.action not in {"add", "remove"}:
            raise MembershipAuditError("independent action must be add or remove")


@dataclass(frozen=True)
class AuditedEvent:
    event: ConstituentChange
    evidence: tuple[IndependentEvidence, ...]
    resolved: bool
    discrepancies: tuple[str, ...]
    quarantine_from: date | None
    quarantine_to: date | None


@dataclass(frozen=True)
class MembershipAuditReport:
    seed: int
    requested_sample_size: int
    date_tolerance_days: int
    independent_sources: tuple[str, ...]
    population_size: int
    audited_events: tuple[AuditedEvent, ...]
    require_every_source: bool
    minimum_corroborated_events: int
    corroborated_events: int
    passed: bool

    def to_json(self) -> str:
        """Serialize with stable field and record ordering for reproducible manifests."""
        return json.dumps(
            asdict(self), default=_json_default, sort_keys=True, separators=(",", ":")
        )


def derive_constituent_changes(
    snapshots: tuple[MembershipSnapshot, ...], identities: DatedSecurityIdentity
) -> tuple[ConstituentChange, ...]:
    """Derive the complete semantic change population from consecutive primary snapshots."""
    if len(snapshots) < 2:
        raise MembershipAuditError("at least two membership snapshots are required for an audit")
    ordered = tuple(sorted(snapshots, key=lambda row: row.as_of))
    if tuple(row.as_of for row in ordered) != tuple(row.as_of for row in snapshots):
        raise MembershipAuditError("membership snapshots must be chronological")
    changes: list[ConstituentChange] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        previous_symbols = set(previous.symbols)
        current_symbols = set(current.symbols)
        for action, symbols, identity_day in (
            ("remove", previous_symbols - current_symbols, previous.as_of),
            ("add", current_symbols - previous_symbols, current.as_of),
        ):
            for symbol in sorted(symbols):
                security_id = identities.resolve_snapshot_symbol(symbol, identity_day)
                semantic = f"{security_id}|{symbol}|{action}|{current.as_of.isoformat()}"
                event_id = hashlib.sha256(semantic.encode()).hexdigest()[:24]
                changes.append(
                    ConstituentChange(event_id, security_id, symbol, action, current.as_of)
                )
    if not changes:
        raise MembershipAuditError("primary membership snapshots contain no changes")
    return tuple(sorted(changes))


def _json_default(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def audit_constituent_changes(
    primary_events: tuple[ConstituentChange, ...],
    independent_evidence: tuple[IndependentEvidence, ...],
    *,
    sample_size: int,
    seed: int,
    date_tolerance_days: int = 1,
    require_every_source: bool = True,
    minimum_corroborated_events: int | None = None,
) -> MembershipAuditReport:
    """Audit a seeded sample against two or more independent evidence sources.

    Every source must corroborate identity, symbol and action, and its date must be
    within the configured tolerance. Missing or conflicting evidence quarantines
    the event's tolerance interval and fails the complete report closed.
    """
    if not 50 <= sample_size <= 100:
        raise MembershipAuditError("sample_size must be between 50 and 100 inclusive")
    if date_tolerance_days < 0:
        raise MembershipAuditError("date_tolerance_days must be non-negative")
    if len(primary_events) < sample_size:
        raise MembershipAuditError("primary population is smaller than requested sample")
    required_corroboration = (
        sample_size if minimum_corroborated_events is None else minimum_corroborated_events
    )
    if not 1 <= required_corroboration <= sample_size:
        raise MembershipAuditError("minimum corroborated events must be within the sample")
    event_ids = [event.event_id for event in primary_events]
    if len(event_ids) != len(set(event_ids)):
        raise MembershipAuditError("primary event_id values must be unique")
    semantic_keys = [
        (event.security_id, event.symbol, event.action, event.effective_date)
        for event in primary_events
    ]
    if len(semantic_keys) != len(set(semantic_keys)):
        raise MembershipAuditError("primary population contains duplicate semantic events")

    evidence_keys = [
        (row.source, row.symbol, row.action, row.effective_date) for row in independent_evidence
    ]
    if len(evidence_keys) != len(set(evidence_keys)):
        raise MembershipAuditError("independent evidence contains duplicate source observations")
    sources = tuple(sorted({row.source for row in independent_evidence if row.source}))
    if len(sources) < 2:
        raise MembershipAuditError("audit requires at least two independent sources")

    ordered = sorted(primary_events)
    sampled = tuple(sorted(random.Random(seed).sample(ordered, sample_size)))
    audited: list[AuditedEvent] = []
    tolerance = timedelta(days=date_tolerance_days)
    for event in sampled:
        candidates = tuple(
            sorted(
                row
                for row in independent_evidence
                if row.symbol == event.symbol
                and row.action == event.action
                and abs((row.effective_date - event.effective_date).days) <= date_tolerance_days
            )
        )
        discrepancies: list[str] = []
        rows_by_source = {
            source: tuple(row for row in candidates if row.source == source) for source in sources
        }
        for source in sources:
            if not rows_by_source[source]:
                discrepancies.append(f"{source}: missing evidence")
            elif len(rows_by_source[source]) > 1:
                discrepancies.append(f"{source}: ambiguous evidence")
        ambiguous = any("ambiguous evidence" in row for row in discrepancies)
        resolved = not ambiguous and (
            not discrepancies if require_every_source else bool(candidates)
        )
        audited.append(
            AuditedEvent(
                event=event,
                evidence=candidates,
                resolved=resolved,
                discrepancies=tuple(discrepancies),
                quarantine_from=None if resolved else event.effective_date - tolerance,
                quarantine_to=(
                    None if resolved else event.effective_date + tolerance + timedelta(days=1)
                ),
            )
        )
    result = tuple(audited)
    corroborated = sum(row.resolved for row in result)
    return MembershipAuditReport(
        seed=seed,
        requested_sample_size=sample_size,
        date_tolerance_days=date_tolerance_days,
        independent_sources=sources,
        population_size=len(primary_events),
        audited_events=result,
        require_every_source=require_every_source,
        minimum_corroborated_events=required_corroboration,
        corroborated_events=corroborated,
        passed=corroborated >= required_corroboration
        and not any(
            "ambiguous evidence" in discrepancy
            for row in result
            for discrepancy in row.discrepancies
        ),
    )
