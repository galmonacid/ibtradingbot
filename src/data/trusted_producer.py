"""In-process orchestration of the trusted historical producer stages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from src.data.canonical_historical import (
    CanonicalCorporateAction,
    CanonicalDataset,
    CanonicalSourceProvenance,
    write_canonical_parquet,
)
from src.data.execution_audit import ExecutionAuditReport
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
    build_security_membership_intervals,
)
from src.validation.workflow import TrustedProducerEvidence, issue_trusted_producer_evidence


class TrustedProducerError(ValueError):
    """Raised when producer stages cannot establish one content-bound dataset."""


_REQUIRED_GIT_SOURCES = {
    "historical_sp500_constituents",
    "unliftedq/index-constitution",
    "riazarbi/sp500-scraper",
    "historical-spy-holdings",
}
_REQUIRED_AUDIT_SOURCES = {"riazarbi/sp500-scraper", "historical-spy-holdings"}


@dataclass(frozen=True)
class TrustedProducerBuild:
    canonical: CanonicalDataset
    membership_audit: MembershipAuditReport
    semantic_report: SemanticCertificationReport
    fmp_reconciliation: FmpReconciliationReport
    trusted_evidence: TrustedProducerEvidence
    evidence_manifest_path: Path


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _digest(value: object) -> str:
    raw = json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def build_trusted_historical_dataset(
    output_directory: Path,
    *,
    membership_source: BoundMembershipSource,
    identity_source: BoundIdentitySource,
    qa_evidence_sources: tuple[BoundAuditEvidenceSource, BoundAuditEvidenceSource],
    tiingo_source: TiingoTransformResult,
    fmp_source: FmpTransformResult,
    sessions: tuple[date, ...],
    benchmark_security_id: str,
    primary_changes: tuple[ConstituentChange, ...],
    audit_sample_size: int,
    audit_seed: int,
    exclusions: tuple[CoverageExclusion, ...],
    terminal_treatments: tuple[TerminalTreatment, ...],
    fmp_quarantines: tuple[SupplementalQuarantine, ...],
    execution_audit: ExecutionAuditReport,
    producer_version: str = "trusted-historical-producer-v1",
) -> TrustedProducerBuild:
    """Run every offline trust stage and issue content-bound validation evidence."""
    verified_sources = (
        membership_source.snapshot,
        identity_source.snapshot,
        *(source.snapshot for source in qa_evidence_sources),
    )
    source_names = {source.source_name for source in verified_sources}
    if source_names != _REQUIRED_GIT_SOURCES or len(verified_sources) != 4:
        raise TrustedProducerError("producer requires the four configured Git source roles")
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
    actions = tuple(sorted(tiingo_source.actions + tuple(identity_actions)))
    identities = DatedSecurityIdentity(identity_intervals)
    memberships = build_security_membership_intervals(
        membership_snapshots, identities, source_version=source_version
    )
    derived_changes = derive_constituent_changes(membership_snapshots, identities)
    if tuple(sorted(primary_changes)) != derived_changes:
        raise TrustedProducerError("audit population is not derived from primary membership")
    membership_security_ids = {membership.security_id for membership in memberships}
    if any(change.security_id not in membership_security_ids for change in primary_changes):
        raise TrustedProducerError("audited change is not linked to canonical membership")
    audit = audit_constituent_changes(
        primary_changes,
        tuple(row for source in qa_evidence_sources for row in source.evidence),
        sample_size=audit_sample_size,
        seed=audit_seed,
    )
    if set(audit.independent_sources) != _REQUIRED_AUDIT_SOURCES:
        raise TrustedProducerError("membership audit is not bound to configured QA sources")
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
    semantics = certify_historical_semantics(
        sessions=sessions,
        memberships=tuple(
            SecurityMembership(row.security_id, row.effective_from, row.effective_to)
            for row in memberships
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
        ),
        bars=tuple(
            CanonicalBar(row.security_id, row.date, row.close, row.adjusted_close) for row in bars
        ),
        benchmark_security_id=benchmark_security_id,
        exclusions=exclusions,
        terminal_treatments=terminal_treatments,
        corporate_actions=tuple(sorted(semantic_actions.values())),
    )
    if not semantics.passed:
        raise TrustedProducerError("historical semantic certification failed")
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
    provider_provenance = (tiingo_source.provenance, fmp_source.provenance)
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
    evidence = issue_trusted_producer_evidence(
        producer_id=_digest(
            {
                "sources": source_hashes,
                "dataset": dataset_hash,
                "fmp_reconciliation": {
                    key: value
                    for key, value in asdict(fmp_reconciliation).items()
                    if key != "_attestation"
                },
            }
        ),
        producer_version=producer_version,
        dataset_manifest_sha256=dataset_hash,
        membership_audit=audit,
        semantic_report=semantics,
        execution_audit=execution_audit,
    )
    evidence_manifest_path = output_directory / "producer_evidence.json"
    evidence_payload = {
        key: value for key, value in asdict(evidence).items() if key != "_attestation"
    }
    evidence_manifest_path.write_text(
        json.dumps(evidence_payload, default=_json_default, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return TrustedProducerBuild(
        canonical, audit, semantics, fmp_reconciliation, evidence, evidence_manifest_path
    )
