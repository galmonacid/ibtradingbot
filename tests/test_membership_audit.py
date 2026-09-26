from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from src.data.membership_audit import (
    ConstituentChange,
    IndependentEvidence,
    MembershipAuditError,
    audit_constituent_changes,
    derive_constituent_changes,
)
from src.data.trusted_historical import (
    DatedSecurityIdentity,
    MembershipSnapshot,
    SecurityIdentityInterval,
)


def _events(count: int = 120) -> tuple[ConstituentChange, ...]:
    start = date(2000, 1, 1)
    return tuple(
        ConstituentChange(
            f"event-{index:03d}",
            f"security-{index:03d}",
            f"S{index:03d}",
            "add" if index % 2 == 0 else "remove",
            start + timedelta(days=index),
        )
        for index in range(count)
    )


def _evidence(events: tuple[ConstituentChange, ...]) -> tuple[IndependentEvidence, ...]:
    return tuple(
        IndependentEvidence(
            source,
            event.symbol,
            event.action,
            event.effective_date + timedelta(days=offset),
        )
        for event in events
        for source, offset in (("holdings", 0), ("scraper", 1))
    )


def test_seeded_audit_is_stable_and_accepts_dates_within_tolerance() -> None:
    events = _events()
    evidence = _evidence(events)

    first = audit_constituent_changes(events, evidence, sample_size=75, seed=42)
    second = audit_constituent_changes(
        tuple(reversed(events)), tuple(reversed(evidence)), sample_size=75, seed=42
    )

    assert first.passed
    assert first.to_json() == second.to_json()
    payload = json.loads(first.to_json())
    assert payload["independent_sources"] == ["holdings", "scraper"]
    assert len(payload["audited_events"]) == 75


def test_missing_or_conflicting_evidence_fails_closed_and_quarantines() -> None:
    events = _events(50)
    evidence = list(_evidence(events))
    evidence = [row for row in evidence if not (row.symbol == "S010" and row.source == "holdings")]
    bad = evidence.index(next(row for row in evidence if row.symbol == "S020"))
    row = evidence[bad]
    evidence[bad] = IndependentEvidence(row.source, row.symbol, "remove", row.effective_date)

    report = audit_constituent_changes(events, tuple(evidence), sample_size=50, seed=1)

    assert not report.passed
    unresolved = {row.event.event_id: row for row in report.audited_events if not row.resolved}
    assert set(unresolved) == {"event-010", "event-020"}
    assert unresolved["event-010"].quarantine_from == events[10].effective_date - timedelta(days=1)
    assert unresolved["event-010"].quarantine_to == events[10].effective_date + timedelta(days=2)


def test_partial_source_coverage_can_meet_explicit_corroboration_floor() -> None:
    events = _events(75)
    evidence = tuple(
        row
        for row in _evidence(events)
        if not (row.source == "holdings" and int(row.symbol[1:]) >= 50)
        and not (row.source == "scraper" and int(row.symbol[1:]) >= 60)
    )
    report = audit_constituent_changes(
        events,
        evidence,
        sample_size=75,
        seed=7,
        require_every_source=False,
        minimum_corroborated_events=50,
    )
    assert report.passed
    assert report.corroborated_events == 60
    assert {row.source for event in report.audited_events for row in event.evidence} == {
        "holdings",
        "scraper",
    }


@pytest.mark.parametrize("sample_size", [49, 101])
def test_sample_size_contract_is_enforced(sample_size: int) -> None:
    events = _events(120)
    with pytest.raises(MembershipAuditError, match="between 50 and 100"):
        audit_constituent_changes(events, _evidence(events), sample_size=sample_size, seed=1)


def test_two_sources_and_unique_evidence_are_required() -> None:
    events = _events(50)
    evidence = _evidence(events)
    single_source = tuple(row for row in evidence if row.source == "holdings")
    with pytest.raises(MembershipAuditError, match="at least two"):
        audit_constituent_changes(events, single_source, sample_size=50, seed=1)
    with pytest.raises(MembershipAuditError, match="duplicate source observations"):
        audit_constituent_changes(events, evidence + (evidence[0],), sample_size=50, seed=1)


def test_multiple_source_native_matches_fail_as_ambiguous() -> None:
    events = _events(50)
    evidence = _evidence(events)
    ambiguous = IndependentEvidence(
        "holdings", events[0].symbol, events[0].action, events[0].effective_date + timedelta(days=1)
    )

    report = audit_constituent_changes(events, evidence + (ambiguous,), sample_size=50, seed=1)

    finding = next(row for row in report.audited_events if row.event == events[0])
    assert not finding.resolved
    assert finding.discrepancies == ("holdings: ambiguous evidence",)


def test_distinct_ids_cannot_inflate_one_semantic_event_to_fifty() -> None:
    events = tuple(
        ConstituentChange(f"event-{index}", "SEC", "AAA", "add", date(2020, 1, 2))
        for index in range(50)
    )
    with pytest.raises(MembershipAuditError, match="duplicate semantic"):
        audit_constituent_changes(events, (), sample_size=50, seed=7)


def test_change_population_is_derived_from_consecutive_snapshots() -> None:
    identities = DatedSecurityIdentity(
        (
            SecurityIdentityInterval("A", "AAA", date(2019, 1, 1), None),
            SecurityIdentityInterval("B", "BBB", date(2019, 1, 1), None),
        )
    )
    changes = derive_constituent_changes(
        (
            MembershipSnapshot(date(2020, 1, 1), ("AAA",)),
            MembershipSnapshot(date(2020, 1, 2), ("BBB",)),
        ),
        identities,
    )
    assert {(row.security_id, row.action) for row in changes} == {("A", "remove"), ("B", "add")}


def test_removal_uses_snapshot_identity_when_source_observation_lags_delisting() -> None:
    identities = DatedSecurityIdentity(
        (
            SecurityIdentityInterval("A", "AAA", date(2019, 1, 1), date(2020, 1, 2)),
            SecurityIdentityInterval("B", "BBB", date(2019, 1, 1), None),
        )
    )
    changes = derive_constituent_changes(
        (
            MembershipSnapshot(date(2020, 1, 3), ("AAA",)),
            MembershipSnapshot(date(2020, 1, 6), ("BBB",)),
        ),
        identities,
    )
    removal = next(row for row in changes if row.action == "remove")
    assert removal.security_id == "A"
    assert removal.effective_date == date(2020, 1, 6)
