"""In-process orchestration of the trusted historical producer stages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from src.data.canonical_historical import (
    CanonicalCorporateAction,
    CanonicalDataset,
    CanonicalSourceProvenance,
    write_canonical_parquet,
)
from src.data.fmp_reconciliation import (
    FmpReconciliationReport,
    SupplementalQuarantine,
    reconcile_fmp_supplemental,
)
from src.data.fmp_transform import FmpTransformResult
from src.data.membership_audit import (
    ConstituentChange,
    MembershipAuditReport,
    audit_constituent_changes,
    derive_constituent_changes,
)
from src.data.semantic_certification import (
    CanonicalBar,
    CorporateAction,
    CoverageExclusion,
    SecurityIdentity,
    SecurityMembership,
    SemanticCertificationReport,
    TerminalTreatment,
    certify_historical_semantics,
)
from src.data.source_adapters import (
    BoundAuditEvidenceSource,
    BoundIdentitySource,
    BoundMembershipSource,
)
from src.data.tiingo_transform import TiingoTransformResult
from src.data.trusted_historical import (
    DatedSecurityIdentity,
    SecurityIdentityInterval,
    SecurityMembershipInterval,
    build_security_membership_intervals,
)
from src.validation.workflow import TrustedDatasetEvidence, issue_trusted_dataset_evidence


class TrustedProducerError(ValueError):
    """Raised when producer stages cannot establish one content-bound dataset."""


_REQUIRED_GIT_SOURCES = {
    "historical_sp500_constituents",
    "unliftedq/index-constitution",
    "riazarbi/sp500-scraper",
    "historical-index-etf-holdings",
}
_REQUIRED_AUDIT_SOURCES = {"riazarbi/sp500-scraper", "historical-index-etf-holdings"}


@dataclass(frozen=True)
class TrustedProducerBuild:
    canonical: CanonicalDataset
    membership_audit: MembershipAuditReport
    semantic_report: SemanticCertificationReport
    fmp_reconciliation: FmpReconciliationReport | None
    dataset_evidence: TrustedDatasetEvidence
    dataset_evidence_manifest_path: Path
    universe_policy_path: Path


@dataclass(frozen=True)
class UniverseSnapshotCount:
    as_of: date
    source_constituents: int
    eligible_constituents: int


@dataclass(frozen=True)
class UniverseSessionCount:
    session: date
    point_in_time_members: int
    price_eligible_constituents: int


@dataclass(frozen=True)
class UniversePolicyReport:
    policy_version: str
    minimum_investable_constituents: int
    validation_start: date
    certification_start: date
    rule: str
    unavailable_requests: tuple[dict[str, object], ...]
    snapshot_counts: tuple[UniverseSnapshotCount, ...]
    session_counts: tuple[UniverseSessionCount, ...]
    coverage_exclusions: tuple[CoverageExclusion, ...]
    quality_quarantines: tuple[dict[str, object], ...]
    sha256: str


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _digest(value: object) -> str:
    raw = json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _subtract_unavailable_ranges(
    membership: SecurityMembershipInterval,
    unavailable: tuple[tuple[date, date], ...],
) -> tuple[SecurityMembershipInterval, ...]:
    """Remove failed request windows from a half-open membership interval."""
    pieces = [(membership.effective_from, membership.effective_to)]
    for unavailable_start, unavailable_end_inclusive in sorted(unavailable):
        unavailable_end = unavailable_end_inclusive + timedelta(days=1)
        next_pieces: list[tuple[date, date | None]] = []
        for start, end in pieces:
            bounded_end = end or date.max
            if unavailable_end <= start or unavailable_start >= bounded_end:
                next_pieces.append((start, end))
                continue
            if start < unavailable_start:
                next_pieces.append((start, unavailable_start))
            if unavailable_end < bounded_end:
                next_pieces.append((unavailable_end, end))
        pieces = next_pieces
    return tuple(
        SecurityMembershipInterval(
            membership.source_version, membership.security_id, start, end
        )
        for start, end in pieces
        if end is None or start < end
    )


def _intersect_membership_with_identities(
    membership: SecurityMembershipInterval,
    identity_intervals: tuple[SecurityIdentityInterval, ...],
) -> tuple[SecurityMembershipInterval, ...]:
    """Clip source membership to dated tradable identity intervals."""
    result: list[SecurityMembershipInterval] = []
    membership_end = membership.effective_to or date.max
    for identity in identity_intervals:
        if identity.security_id != membership.security_id:
            continue
        identity_start = identity.effective_from
        identity_end = identity.effective_to or date.max
        start = max(membership.effective_from, identity_start)
        end = min(membership_end, identity_end)
        if start < end:
            result.append(
                SecurityMembershipInterval(
                    membership.source_version,
                    membership.security_id,
                    start,
                    None if end == date.max else end,
                )
            )
    return tuple(result)


def build_trusted_historical_dataset(
    output_directory: Path,
    *,
    membership_source: BoundMembershipSource,
    identity_source: BoundIdentitySource,
    qa_evidence_sources: tuple[BoundAuditEvidenceSource, BoundAuditEvidenceSource],
    tiingo_source: TiingoTransformResult,
    fmp_source: FmpTransformResult | None,
    sessions: tuple[date, ...],
    benchmark_security_id: str,
    primary_changes: tuple[ConstituentChange, ...],
    audit_sample_size: int,
    audit_seed: int,
    exclusions: tuple[CoverageExclusion, ...],
    terminal_treatments: tuple[TerminalTreatment, ...],
    fmp_quarantines: tuple[SupplementalQuarantine, ...] = (),
    minimum_investable_constituents: int = 400,
    producer_version: str = "trusted-historical-producer-v1",
) -> TrustedProducerBuild:
    """Run every offline trust stage and issue content-bound dataset evidence."""
    verified_sources = (
        membership_source.snapshot,
        identity_source.snapshot,
        *(source.snapshot for source in qa_evidence_sources),
    )
    if any(not source.checkout_verified for source in verified_sources):
        raise TrustedProducerError("producer requires Git-checkout-verified source snapshots")
    if any(not source.source_native for source in qa_evidence_sources):
        raise TrustedProducerError("producer requires source-native independent QA snapshots")
    source_names = {source.source_name for source in verified_sources}
    if source_names != _REQUIRED_GIT_SOURCES or len(verified_sources) != 4:
        raise TrustedProducerError("producer requires the four configured Git source roles")
    if minimum_investable_constituents < 1:
        raise TrustedProducerError("minimum investable constituent count must be positive")
    if not tiingo_source.intended_plan_verified:
        raise TrustedProducerError("producer requires the independently derived Tiingo plan")
    unavailable_by_security: dict[str, list[tuple[date, date]]] = {}
    for row in tiingo_source.unavailable:
        unavailable_by_security.setdefault(row.security_id, []).append((row.start, row.end))
    if benchmark_security_id in unavailable_by_security:
        raise TrustedProducerError("Tiingo benchmark history is unavailable")
    bars = tiingo_source.bars
    membership_snapshots = membership_source.memberships
    identity_intervals = identity_source.parsed.identity_intervals
    source_version = membership_source.snapshot.manifest_sha256
    identity_actions: list[CanonicalCorporateAction] = []
    for delisting in identity_source.parsed.delistings:
        matches = [
            row
            for row in identity_intervals
            if row.symbol == delisting.symbol and row.effective_to == delisting.event_date
        ]
        if len(matches) != 1:
            raise TrustedProducerError("identity delisting is not bound to one ended security")
        identity_actions.append(
            CanonicalCorporateAction(
                matches[0].security_id,
                delisting.symbol,
                delisting.event_date,
                "delisting",
                0.0,
            )
        )
    actions = tuple(
        sorted(
            row
            for row in tiingo_source.actions + tuple(identity_actions)
        )
    )
    identities = DatedSecurityIdentity(identity_intervals)
    all_memberships = build_security_membership_intervals(
        membership_snapshots, identities, source_version=source_version
    )
    availability_memberships = tuple(
        piece
        for row in all_memberships
        for piece in _subtract_unavailable_ranges(
            row, tuple(unavailable_by_security.get(row.security_id, ()))
        )
    )
    identity_memberships = tuple(
        clipped
        for row in availability_memberships
        for clipped in _intersect_membership_with_identities(row, identity_intervals)
    )
    bar_keys = {(row.security_id, row.date) for row in bars}
    bar_dates_by_security: dict[str, set[date]] = {}
    for security_id, day in bar_keys:
        bar_dates_by_security.setdefault(security_id, set()).add(day)
    memberships = tuple(
        row
        for row in identity_memberships
        if any(
            row.effective_from <= day
            and (row.effective_to is None or day < row.effective_to)
            for day in bar_dates_by_security.get(row.security_id, ())
        )
    )
    bars_by_session = bar_keys
    caller_exclusions = {(row.security_id, row.session): row for row in exclusions}

    def universe_ledger(
        current_memberships: tuple[SecurityMembershipInterval, ...],
    ) -> tuple[
        tuple[CoverageExclusion, ...],
        tuple[UniverseSessionCount, ...],
        date,
        date,
        tuple[date, ...],
        tuple[UniverseSnapshotCount, ...],
    ]:
        generated_exclusions: list[CoverageExclusion] = []
        session_count_rows: list[UniverseSessionCount] = []
        for session in sessions:
            active_ids = {
                row.security_id
                for row in current_memberships
                if row.effective_from <= session
                and (row.effective_to is None or session < row.effective_to)
            }
            eligible_ids = {
                security_id
                for security_id in active_ids
                if (security_id, session) in bars_by_session
                and (security_id, session) not in caller_exclusions
            }
            for security_id in sorted(active_ids - eligible_ids):
                key = (security_id, session)
                if key not in caller_exclusions and key not in bars_by_session:
                    generated_exclusions.append(
                        CoverageExclusion(
                            security_id, session, "provider_confirmed_missing"
                        )
                    )
            session_count_rows.append(
                UniverseSessionCount(session, len(active_ids), len(eligible_ids))
            )
        effective = tuple(
            sorted(
                exclusions + tuple(generated_exclusions),
                key=lambda row: (row.session, row.security_id),
            )
        )
        suffix_minimum = 10**9
        start: date | None = None
        for session_row in reversed(session_count_rows):
            suffix_minimum = min(
                suffix_minimum, session_row.price_eligible_constituents
            )
            if suffix_minimum >= minimum_investable_constituents:
                start = session_row.session
        if start is None:
            raise TrustedProducerError(
                "Tiingo-covered universe never sustains the configured minimum"
            )
        certification = start - timedelta(days=400)
        certified_sessions = tuple(day for day in sessions if day >= certification)
        snapshot_count_rows: list[UniverseSnapshotCount] = []
        for snapshot in membership_snapshots:
            source_ids = {
                identities.resolve_snapshot_symbol(symbol, snapshot.as_of)
                for symbol in snapshot.symbols
            }
            investable = {
                row.security_id
                for row in current_memberships
                if row.security_id in source_ids
                and row.effective_from <= snapshot.as_of
                and (row.effective_to is None or snapshot.as_of < row.effective_to)
            }
            snapshot_count_rows.append(
                UniverseSnapshotCount(snapshot.as_of, len(source_ids), len(investable))
            )
            if snapshot.as_of >= start and len(investable) < minimum_investable_constituents:
                raise TrustedProducerError(
                    "Tiingo-covered point-in-time universe falls below configured minimum"
                )
        return (
            effective,
            tuple(session_count_rows),
            start,
            certification,
            certified_sessions,
            tuple(snapshot_count_rows),
        )

    (
        effective_exclusions,
        session_counts,
        validation_start,
        certification_start,
        certification_sessions,
        snapshot_counts,
    ) = universe_ledger(memberships)
    derived_changes = derive_constituent_changes(membership_snapshots, identities)
    if tuple(sorted(primary_changes)) != derived_changes:
        raise TrustedProducerError("audit population is not derived from primary membership")
    membership_security_ids = {membership.security_id for membership in all_memberships}
    if any(change.security_id not in membership_security_ids for change in primary_changes):
        raise TrustedProducerError("audited change is not linked to canonical membership")
    independent_evidence = tuple(
        row for source in qa_evidence_sources for row in source.evidence
    )
    source_ranges = {
        source.snapshot.source_name: (
            min(row.effective_date for row in source.evidence),
            max(row.effective_date for row in source.evidence),
        )
        for source in qa_evidence_sources
    }
    overlap_start = max(value[0] for value in source_ranges.values())
    overlap_end = min(value[1] for value in source_ranges.values())
    audit_population = tuple(
        row for row in primary_changes if overlap_start <= row.effective_date <= overlap_end
    )
    if len(audit_population) < audit_sample_size:
        raise TrustedProducerError("independent QA overlap has too few primary events")
    audit = audit_constituent_changes(
        audit_population,
        independent_evidence,
        sample_size=audit_sample_size,
        seed=audit_seed,
        require_every_source=False,
        minimum_corroborated_events=min(50, audit_sample_size),
    )
    if set(audit.independent_sources) != _REQUIRED_AUDIT_SOURCES:
        raise TrustedProducerError("membership audit is not bound to configured QA sources")
    contributing_sources = {
        evidence.source for event in audit.audited_events for evidence in event.evidence
    }
    if contributing_sources != _REQUIRED_AUDIT_SOURCES:
        raise TrustedProducerError("each configured QA source must corroborate sampled events")
    if not audit.passed:
        raise TrustedProducerError("independent membership audit failed")
    semantic_actions: dict[tuple[str, date], CorporateAction] = {}
    for action in actions:
        if action.action_type == "delisting":
            continue
        key = (action.security_id, action.action_date)
        current = semantic_actions.get(key, CorporateAction(*key))
        semantic_actions[key] = CorporateAction(
            *key,
            split_ratio=(
                current.split_ratio * action.value
                if action.action_type == "split"
                else current.split_ratio
            ),
            cash_dividend=(
                current.cash_dividend + action.value
                if action.action_type == "dividend"
                else current.cash_dividend
            ),
        )
    last_by_security = {
        security_id: max(
            row.effective_from for row in identity_intervals if row.security_id == security_id
        )
        for security_id in {row.security_id for row in identity_intervals}
    }

    def certify_universe() -> SemanticCertificationReport:
        certified_memberships = tuple(
            SecurityMembershipInterval(
                row.source_version,
                row.security_id,
                max(row.effective_from, certification_start),
                row.effective_to,
            )
            for row in memberships
            if row.effective_to is None or row.effective_to > certification_start
        )
        memberships_by_security = {
            security_id: tuple(
                row for row in certified_memberships if row.security_id == security_id
            )
            for security_id in {row.security_id for row in certified_memberships}
        }

        def active_member(security_id: str, day: date) -> bool:
            return any(
                row.effective_from <= day
                and (row.effective_to is None or day < row.effective_to)
                for row in memberships_by_security.get(security_id, ())
            )

        certified_bars = tuple(
            row
            for row in bars
            if row.date >= certification_start
            and (
                row.security_id == benchmark_security_id
                or active_member(row.security_id, row.date)
            )
        )
        certified_actions = tuple(
            row
            for row in semantic_actions.values()
            if row.effective_date > certification_start
            and (
                row.security_id == benchmark_security_id
                or active_member(row.security_id, row.effective_date)
            )
        )
        certified_security_ids = {row.security_id for row in certified_memberships} | {
            benchmark_security_id
        }
        supplied_terminal_ids = {row.security_id for row in terminal_treatments}
        derived_terminal_treatments: list[TerminalTreatment] = []
        for security_id in sorted(certified_security_ids - supplied_terminal_ids):
            final_identity = max(
                (row for row in identity_intervals if row.security_id == security_id),
                key=lambda row: row.effective_from,
            )
            if final_identity.effective_to is None:
                continue
            last_bar = max(
                (
                    row.date
                    for row in certified_bars
                    if row.security_id == security_id
                    and row.date < final_identity.effective_to
                ),
                default=None,
            )
            if last_bar is not None:
                derived_terminal_treatments.append(
                    TerminalTreatment(
                        security_id,
                        last_bar,
                        "zero",
                        0.0,
                        "conservative-zero policy from pinned identity delisting",
                    )
                )
        effective_terminal_treatments = tuple(
            sorted(terminal_treatments + tuple(derived_terminal_treatments))
        )
        return certify_historical_semantics(
            sessions=certification_sessions,
            memberships=tuple(
                SecurityMembership(row.security_id, row.effective_from, row.effective_to)
                for row in certified_memberships
            ),
            identities=tuple(
                SecurityIdentity(
                    row.security_id,
                    row.effective_from,
                    row.effective_to,
                    row.effective_from == last_by_security[row.security_id]
                    and row.effective_to is not None,
                )
                for row in identity_intervals
                if row.security_id in certified_security_ids
            ),
            bars=tuple(
                CanonicalBar(row.security_id, row.date, row.close, row.adjusted_close)
                for row in certified_bars
            ),
            benchmark_security_id=benchmark_security_id,
            exclusions=tuple(
                row for row in effective_exclusions if row.session >= certification_start
            ),
            terminal_treatments=effective_terminal_treatments,
            corporate_actions=tuple(sorted(certified_actions)),
        )

    semantics = certify_universe()
    action_finding_codes = {
        "ACTION_WITHOUT_BARS",
        "CORPORATE_ACTION_FACTOR_MISMATCH",
        "INVALID_DIVIDEND_FACTOR",
        "UNEXPLAINED_ADJUSTMENT_FACTOR_CHANGE",
    }
    quality_findings = tuple(
        row
        for row in semantics.findings
        if row.code in action_finding_codes and row.session is not None
    )
    quality_quarantines: tuple[dict[str, object], ...] = ()
    if quality_findings:
        if any(row.security_id == benchmark_security_id for row in quality_findings):
            raise TrustedProducerError("benchmark corporate-action reconciliation failed")
        affected: list[tuple[SecurityMembershipInterval, date, str]] = []
        for membership_row in memberships:
            matching = tuple(
                finding
                for finding in quality_findings
                if finding.security_id == membership_row.security_id
                and finding.session is not None
                and membership_row.effective_from <= finding.session
                and (
                    membership_row.effective_to is None
                    or finding.session < membership_row.effective_to
                )
            )
            if matching:
                first = min(matching, key=lambda finding: finding.session or date.max)
                assert first.session is not None
                affected.append((membership_row, first.session, first.code))
        if not affected:
            raise TrustedProducerError("corporate-action finding cannot be quarantined")
        affected_rows = {row for row, _session, _code in affected}
        memberships = tuple(
            sorted(
                (
                    *(row for row in memberships if row not in affected_rows),
                    *(
                        SecurityMembershipInterval(
                            row.source_version,
                            row.security_id,
                            row.effective_from,
                            finding_session,
                        )
                        for row, finding_session, _code in affected
                        if row.effective_from < finding_session
                    ),
                )
            )
        )
        quality_quarantines = tuple(
            {
                "security_id": row.security_id,
                "effective_from": finding_session,
                "effective_to": row.effective_to,
                "reason": code,
            }
            for row, finding_session, code in affected
        )
        (
            effective_exclusions,
            session_counts,
            validation_start,
            certification_start,
            certification_sessions,
            snapshot_counts,
        ) = universe_ledger(memberships)
        semantics = certify_universe()
    if not semantics.passed:
        output_directory.mkdir(parents=True, exist_ok=True)
        (output_directory / "semantic_report.failed.json").write_text(
            json.dumps(asdict(semantics), default=_json_default, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_directory / "universe_probe.json").write_text(
            json.dumps(
                {
                    "minimum_investable_constituents": minimum_investable_constituents,
                    "validation_start": validation_start,
                    "certification_start": certification_start,
                    "unavailable_requests": [asdict(row) for row in tiingo_source.unavailable],
                    "snapshot_counts": [asdict(row) for row in snapshot_counts],
                    "session_counts": [asdict(row) for row in session_counts],
                    "coverage_exclusions": [asdict(row) for row in effective_exclusions],
                    "quality_quarantines": quality_quarantines,
                },
                default=_json_default,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise TrustedProducerError("historical semantic certification failed")
    fmp_reconciliation = None
    if fmp_source is not None:
        fmp_reconciliation = reconcile_fmp_supplemental(
            canonical_bars=bars,
            canonical_actions=actions,
            prices=fmp_source.prices,
            dividends=fmp_source.dividends,
            delistings=fmp_source.delistings,
            quarantines=fmp_quarantines,
        )
        if not fmp_reconciliation.passed or fmp_reconciliation.findings:
            raise TrustedProducerError("supplemental FMP reconciliation failed")
    elif fmp_quarantines:
        raise TrustedProducerError("FMP quarantines require an FMP source")
    git_provenance = tuple(
        CanonicalSourceProvenance(
            source.source_name,
            "git",
            source.manifest_sha256,
            source.retrieved_at.isoformat(),
            source.licence,
            repository_url=source.repository_url,
            commit_sha=source.commit_sha,
        )
        for source in verified_sources
    )
    provider_provenance = (tiingo_source.provenance,) + (
        (fmp_source.provenance,) if fmp_source is not None else ()
    )
    source_hashes = tuple(
        row.manifest_sha256
        for row in sorted(git_provenance + provider_provenance, key=lambda item: item.source_name)
    )
    canonical = write_canonical_parquet(
        output_directory / "canonical",
        bars=bars,
        identities=identity_intervals,
        memberships=memberships,
        actions=actions,
        source_provenance=git_provenance + provider_provenance,
        transformation_version=producer_version,
    )
    dataset_hash = hashlib.sha256(canonical.manifest_path.read_bytes()).hexdigest()
    unavailable_payload: tuple[dict[str, object], ...] = tuple(
        asdict(row) for row in tiingo_source.unavailable
    )
    universe_payload = {
        "policy_version": "tiingo-availability-intersection-v1",
        "minimum_investable_constituents": minimum_investable_constituents,
        "validation_start": validation_start,
        "certification_start": certification_start,
        "rule": (
            "Primary point-in-time membership intersected with Tiingo request availability; "
            "failed request windows remove only overlapping membership time, never other history. "
            "Semantic certification begins 400 calendar days before the sustained-floor "
            "validation start so every validation feature lookback is covered."
        ),
        "unavailable_requests": unavailable_payload,
        "snapshot_counts": [asdict(row) for row in snapshot_counts],
        "session_counts": [asdict(row) for row in session_counts],
        "coverage_exclusions": [asdict(row) for row in effective_exclusions],
        "quality_quarantines": quality_quarantines,
    }
    universe_hash = _digest(universe_payload)
    universe_policy = UniversePolicyReport(
        str(universe_payload["policy_version"]),
        minimum_investable_constituents,
        validation_start,
        certification_start,
        str(universe_payload["rule"]),
        unavailable_payload,
        tuple(snapshot_counts),
        tuple(session_counts),
        effective_exclusions,
        quality_quarantines,
        universe_hash,
    )
    universe_policy_path = output_directory / "universe_policy.json"
    universe_policy_path.write_text(
        json.dumps(asdict(universe_policy), default=_json_default, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence = issue_trusted_dataset_evidence(
        producer_id=_digest(
            {
                "sources": source_hashes,
                "dataset": dataset_hash,
                "universe_policy": universe_hash,
                "fmp_reconciliation": (
                    {
                        key: value
                        for key, value in asdict(fmp_reconciliation).items()
                        if key != "_attestation"
                    }
                    if fmp_reconciliation is not None
                    else None
                ),
            }
        ),
        producer_version=producer_version,
        dataset_manifest_sha256=dataset_hash,
        universe_policy_sha256=universe_hash,
        membership_audit=audit,
        semantic_report=semantics,
    )
    evidence_manifest_path = output_directory / "dataset_evidence.json"
    evidence_payload = {
        key: value for key, value in asdict(evidence).items() if key != "_attestation"
    }
    evidence_manifest_path.write_text(
        json.dumps(evidence_payload, default=_json_default, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_directory / "membership_audit.json").write_text(
        audit.to_json(), encoding="utf-8"
    )
    (output_directory / "semantic_report.json").write_text(
        semantics.to_json(), encoding="utf-8"
    )
    return TrustedProducerBuild(
        canonical,
        audit,
        semantics,
        fmp_reconciliation,
        evidence,
        evidence_manifest_path,
        universe_policy_path,
    )
