"""R3.2 development-only dataset materialization and evidence audit."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.config.r3 import R3Config
from src.data.calendar import TradingCalendar
from src.data.canonical_historical import VerifiedCanonicalInputs
from src.data.fx import FXHistory
from src.data.r3_evidence import CashActionEvidenceSet
from src.features.r3 import (
    R3_FEATURE_NAMES,
    MembershipEvidence,
    R3Action,
    R3FeatureRow,
    R3Label,
    R3Price,
    build_r3_feature_rows,
    build_r3_labels,
    monthly_decision_dates,
)
from src.validation.r3_register import (
    DataAccessRecord,
    R3ExperimentRegister,
    preregister_r3,
)
from src.validation.r3_splits import R3SplitAssignment, build_r3_split_assignments
from src.validation.walk_forward import build_expanding_windows


@dataclass(frozen=True)
class R3SourceAudit:
    canonical_manifest_bound: bool
    producer_evidence_bound: bool
    universe_policy_bound: bool
    calendar_matches_benchmark: bool
    calendar_independent: bool
    fx_vintage_certified: bool
    dated_primary_common_classification: bool
    dividend_payment_dates: bool
    dividend_withholding: bool
    delisting_payment_dates: bool
    membership_availability_vintage_certified: bool
    development_only: bool = True


@dataclass(frozen=True)
class R3Materialization:
    feature_rows: tuple[R3FeatureRow, ...]
    labels: tuple[R3Label, ...]
    splits: tuple[R3SplitAssignment, ...]
    register: R3ExperimentRegister
    report: dict[str, Any]


def _development_training_blockers(
    evidence_blockers: list[str],
    *,
    protocol_ready_folds: tuple[int, ...],
    outcome_conditioned_cash_action_rows_dropped: int,
    scope_override: bool,
) -> list[str]:
    """Apply a scope decision without waiving structural label-safety gates."""
    blockers = [] if scope_override else list(evidence_blockers)
    if not protocol_ready_folds:
        blockers.append("no_protocol_ready_8y_2y_1y_fold")
    if outcome_conditioned_cash_action_rows_dropped:
        blockers.append("outcome_conditioned_cash_action_rows_omitted")
    return blockers


def _timestamp(day: date, at: time) -> datetime:
    return datetime.combine(day, at, ZoneInfo("America/New_York"))


def _count(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_hash(policy: Mapping[str, object]) -> str:
    content = {key: value for key, value in policy.items() if key != "sha256"}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_rows(
    canonical: VerifiedCanonicalInputs,
    calendar: TradingCalendar,
    fx: FXHistory,
    *,
    first_fx_date: date,
    cash_action_evidence: CashActionEvidenceSet,
) -> tuple[
    tuple[R3Price, ...],
    tuple[MembershipEvidence, ...],
    tuple[R3Action, ...],
    tuple[date, ...],
    str,
]:
    benchmark_ids = {row.security_id for row in canonical.bars if row.symbol == "SPY"}
    if len(benchmark_ids) != 1:
        raise ValueError("canonical data must contain one stable SPY identity")
    benchmark_id = benchmark_ids.pop()
    sessions = calendar.sessions
    first_fx_index = next(
        (index for index, session in enumerate(sessions) if session >= first_fx_date), None
    )
    if first_fx_index is None or first_fx_index < 253:
        raise ValueError("calendar does not contain the required pre-FX feature warm-up")
    warmup_start = sessions[first_fx_index - 253]
    retained_sessions = tuple(session for session in sessions if session >= warmup_start)
    retained_set = set(retained_sessions)
    daily_file = next(row for row in canonical.dataset.files if row.path == "daily_bars.parquet")
    raw_series_id = f"canonical-raw-{daily_file.sha256}"
    adjusted_series_id = f"canonical-adjusted-{daily_file.sha256}"
    prices = tuple(
        R3Price(
            row.security_id,
            row.date,
            row.open,
            row.close,
            row.adjusted_close,
            row.volume,
            _timestamp(row.date, time(9, 30)),
            _timestamp(row.date, time(16, 0)),
            raw_series_id,
            adjusted_series_id,
        )
        for row in canonical.bars
        if row.date in retained_set
    )
    memberships = tuple(
        MembershipEvidence(
            row.security_id,
            row.effective_from,
            row.effective_to,
            _timestamp(row.effective_from, time(16, 0)),
            True,
            f"{row.source_version}:classification-assumed",
        )
        for row in canonical.memberships
        if row.effective_to is None or row.effective_to >= warmup_start
    )
    evidence_by_key = {
        (row.security_id, row.effective_date, row.action_type): row
        for row in cash_action_evidence.rows
    }
    actions: list[R3Action] = []
    for row in canonical.actions:
        if row.action_date < warmup_start:
            continue
        effective = _timestamp(row.action_date, time(9, 30))
        available = _timestamp(row.action_date, time(16, 0))
        if row.action_type == "split":
            actions.append(R3Action(row.security_id, "split", effective, available, row.value))
        elif row.action_type == "dividend":
            evidence = evidence_by_key.get((row.security_id, row.action_date, "dividend"))
            if evidence is not None and not math.isclose(
                evidence.value_per_share, row.value, rel_tol=0, abs_tol=0.00001
            ):
                raise ValueError("cash-action evidence value contradicts canonical action")
            actions.append(
                R3Action(
                    row.security_id,
                    "dividend",
                    effective,
                    available if evidence is None else evidence.source_available_at,
                    row.value,
                    payment_at=(
                        None if evidence is None else _timestamp(evidence.payment_date, time(9, 30))
                    ),
                    withholding_fraction=(
                        None if evidence is None else evidence.withholding_fraction
                    ),
                )
            )
        elif row.action_type == "delisting":
            evidence = evidence_by_key.get((row.security_id, row.action_date, "delisting"))
            if (
                evidence is not None
                and row.value != 0
                and not math.isclose(
                    evidence.value_per_share, row.value, rel_tol=0, abs_tol=0.00001
                )
            ):
                raise ValueError("delisting evidence value contradicts canonical action")
            actions.append(
                R3Action(
                    row.security_id,
                    "delisting",
                    effective,
                    available if evidence is None else evidence.source_available_at,
                    row.value if evidence is None else evidence.value_per_share,
                    payment_at=(
                        None if evidence is None else _timestamp(evidence.payment_date, time(9, 30))
                    ),
                    withholding_fraction=0.0,
                )
            )
    return prices, memberships, tuple(actions), retained_sessions, benchmark_id


def build_r3_materialization(
    *,
    canonical: VerifiedCanonicalInputs,
    calendar: TradingCalendar,
    fx: FXHistory,
    fx_manifest: Mapping[str, object],
    cash_action_evidence: CashActionEvidenceSet,
    cash_action_manifest: Mapping[str, object],
    independent_calendar: TradingCalendar,
    independent_calendar_manifest: Mapping[str, object],
    dataset_evidence: Mapping[str, object],
    universe_policy: Mapping[str, object],
    config: R3Config,
    access_records: tuple[DataAccessRecord, ...],
    run_timestamp: datetime,
) -> R3Materialization:
    """Build development rows while retaining every unresolved causal outcome."""
    if run_timestamp.tzinfo is None:
        raise ValueError("run timestamp must be timezone-aware")
    if not fx.observations:
        raise ValueError("FX history must not be empty")
    prices, memberships, actions, retained_sessions, benchmark_id = _source_rows(
        canonical,
        calendar,
        fx,
        first_fx_date=fx.observations[0].available_at.date(),
        cash_action_evidence=cash_action_evidence,
    )
    feature_rows = build_r3_feature_rows(
        prices,
        memberships,
        retained_sessions,
        benchmark_id=benchmark_id,
        feature_version=config.feature_version,
    )
    labels = build_r3_labels(
        feature_rows,
        prices,
        actions,
        fx,
        retained_sessions,
        benchmark_id=benchmark_id,
        label_version=config.label_version,
        max_fx_age_days=config.max_fx_age_days,
    )
    usable_feature_dates = [row.decision_date for row in feature_rows if not row.exclusion_reasons]
    if not usable_feature_dates:
        raise ValueError("R3 materialization contains no usable feature decision")
    split_start = min(usable_feature_dates)
    split_sessions = tuple(session for session in retained_sessions if session >= split_start)
    splits = build_r3_split_assignments(
        labels,
        split_sessions,
        verified_complete_through=split_sessions[-1],
        as_of=run_timestamp,
        purge_sessions=config.purge_sessions,
    )
    base_register = preregister_r3(config, run_timestamp)
    register = R3ExperimentRegister(
        base_register.registration_version,
        base_register.config_sha256,
        base_register.legacy_controls,
        access_records,
        base_register.trials,
    )
    benchmark_sessions = tuple(
        sorted({row.date for row in canonical.bars if row.security_id == benchmark_id})
    )
    policy_hash = _policy_hash(universe_policy)
    calendar_independent = (
        independent_calendar.sessions == calendar.sessions
        and independent_calendar_manifest.get("independent_of_price_rows") is True
        and independent_calendar_manifest.get("sha256") == independent_calendar.source_sha256
    )
    retained_dividends = tuple(row for row in actions if row.action_type == "dividend")
    retained_delistings = tuple(row for row in actions if row.action_type == "delisting")
    evidenced_dividends = tuple(
        row
        for row in retained_dividends
        if row.payment_at is not None and row.withholding_fraction is not None
    )
    evidenced_delistings = tuple(row for row in retained_delistings if row.payment_at is not None)
    dividend_complete = len(evidenced_dividends) == len(retained_dividends)
    delisting_complete = len(evidenced_delistings) == len(retained_delistings)
    audit = R3SourceAudit(
        dataset_evidence.get("dataset_manifest_sha256") == canonical.manifest_sha256,
        dataset_evidence.get("producer_version") == canonical.transformation_version,
        universe_policy.get("sha256") == policy_hash
        and dataset_evidence.get("universe_policy_sha256") == policy_hash,
        benchmark_sessions == calendar.sessions,
        calendar_independent,
        fx_manifest.get("vintage_certified") is True,
        False,
        dividend_complete,
        dividend_complete and cash_action_manifest.get("withholding_assumption") is False,
        delisting_complete,
        False,
    )
    exclusions = _count([reason for row in feature_rows for reason in row.exclusion_reasons])
    unresolved = _count(
        [row.unresolved_reason for row in labels if row.unresolved_reason is not None]
    )
    split_counts: defaultdict[int, Counter[str]] = defaultdict(Counter)
    for row in splits:
        split_counts[row.fold_id][row.split] += 1
    nonempty_folds = tuple(
        fold
        for fold, counts in sorted(split_counts.items())
        if all(counts[name] > 0 for name in ("train", "validation", "test"))
    )
    feature_dates = [row.decision_date for row in feature_rows]
    matured = [row for row in labels if row.matured]
    matured_dates = [row.decision_date for row in matured]
    required_years = config.initial_train_years + config.validation_years + config.test_years
    matured_span_days = (max(matured_dates) - min(matured_dates)).days if matured_dates else 0
    history_sufficient = matured_span_days >= required_years * 365
    dates_by_fold_split: defaultdict[tuple[int, str], set[date]] = defaultdict(set)
    for row in splits:
        dates_by_fold_split[(row.fold_id, row.split)].add(row.decision_date)

    decisions = monthly_decision_dates(split_sessions)
    session_position = {session: index for index, session in enumerate(split_sessions)}
    windows = build_expanding_windows(
        split_sessions,
        verified_complete_through=split_sessions[-1],
        initial_train_years=config.initial_train_years,
        validation_years=config.validation_years,
        test_years=config.test_years,
        step_months=config.step_years * 12,
    )
    expected_dates: defaultdict[tuple[int, str], set[date]] = defaultdict(set)
    for window in windows:
        validation_index = session_position[window.validation[0]]
        test_index = session_position[window.test[0]]
        train_cutoff = split_sessions[validation_index - config.purge_sessions - 1]
        validation_cutoff = split_sessions[test_index - config.purge_sessions - 1]
        for index, decision in enumerate(decisions[:-1]):
            next_decision = decisions[index + 1]
            exit_index = session_position[next_decision] + 1
            if exit_index >= len(split_sessions):
                continue
            exit_day = split_sessions[exit_index]
            if decision in window.train and exit_day <= train_cutoff:
                expected_dates[(window.index, "train")].add(decision)
            elif decision in window.validation and exit_day <= validation_cutoff:
                expected_dates[(window.index, "validation")].add(decision)
            elif decision in window.test:
                expected_dates[(window.index, "test")].add(decision)
    protocol_ready_folds = tuple(
        fold
        for fold in nonempty_folds
        if all(
            dates_by_fold_split[(fold, split)] == expected_dates[(fold, split)]
            and bool(expected_dates[(fold, split)])
            for split in ("train", "validation", "test")
        )
    )
    evidence_blockers = [
        "dated_primary_common_classification_assumed",
        "membership_availability_not_vintage_certified",
        "fx_not_vintage_certified",
    ]
    if not dividend_complete:
        evidence_blockers.append("dividend_payment_dates_incomplete")
    if cash_action_manifest.get("withholding_assumption") is not False:
        evidence_blockers.append("dividend_withholding_development_assumption")
    if not delisting_complete:
        evidence_blockers.append("delisting_payment_recovery_incomplete")
    if not calendar_independent:
        evidence_blockers.append("independent_calendar_mismatch_or_unavailable")
    if not history_sufficient:
        evidence_blockers.append("matured_label_history_under_11_years")
    if not protocol_ready_folds:
        evidence_blockers.append("no_protocol_ready_8y_2y_1y_fold")
    if any(reason.startswith("cash_action_") for reason in unresolved):
        evidence_blockers.append("cash_action_labels_unresolved")
    outcome_conditioned_cash_action_rows_dropped = 0
    scope_override = config.r3_2_scope_decision == "proceed_with_open_label_evidence"
    development_blockers = _development_training_blockers(
        evidence_blockers,
        protocol_ready_folds=protocol_ready_folds,
        outcome_conditioned_cash_action_rows_dropped=(outcome_conditioned_cash_action_rows_dropped),
        scope_override=scope_override,
    )
    report: dict[str, Any] = {
        "contract": "r3.2-development-dataset-v1",
        "development_only": True,
        "qualification_permitted": False,
        "r3_3_development_training_permitted": not development_blockers,
        "development_training_blockers": sorted(set(development_blockers)),
        "evidence_limitations": sorted(set(evidence_blockers)),
        "r3_2_phase_closed": not development_blockers,
        "r3_2_closure_basis": (
            "explicit_scope_decision_with_open_label_evidence"
            if scope_override
            else "evidence_complete"
        ),
        "scope_decision": {
            "decision": config.r3_2_scope_decision,
            "recorded_at": config.r3_2_scope_decision_recorded_at,
            "note": config.r3_2_scope_decision_note,
            "resolves_evidence_limitations": False,
            "waives_evidence_limitations_for_development_training": True,
            "r3_3_started": False,
        },
        "run_timestamp": run_timestamp.isoformat(),
        "config_sha256": config.sha256,
        "canonical_manifest_sha256": canonical.manifest_sha256,
        "calendar_sha256": calendar.source_sha256,
        "fx_identity_sha256": fx.sha256,
        "cash_action_evidence_sha256": cash_action_evidence.sha256,
        "independent_calendar_sha256": independent_calendar.source_sha256,
        "register_sha256": register.sha256,
        "source_audit": asdict(audit),
        "source_provenance": [asdict(row) for row in canonical.source_provenance],
        "fx_source": {
            "source": fx.source,
            "licence": fx.licence,
            "synthetic": fx.synthetic,
        },
        "redistribution": "local development only; do not redistribute provider/source data",
        "timing_assumptions": {
            "raw_open": "09:30 America/New_York",
            "daily_close_available": "16:00 America/New_York",
            "membership_available": (
                "effective-from session close; retrospective, not vintage-certified"
            ),
            "fx_max_age_days": config.max_fx_age_days,
            "fx_manifest_availability": fx_manifest.get("availability_assumption"),
            "dividend_withholding": cash_action_manifest.get("withholding_treatment"),
        },
        "coverage": {
            "canonical_start": benchmark_sessions[0].isoformat(),
            "canonical_end": benchmark_sessions[-1].isoformat(),
            "materialization_start": retained_sessions[0].isoformat(),
            "materialization_end": retained_sessions[-1].isoformat(),
            "fx_start": fx.observations[0].available_at.isoformat(),
            "fx_end": fx.observations[-1].available_at.isoformat(),
            "feature_decision_start": min(feature_dates).isoformat() if feature_dates else None,
            "feature_decision_end": max(feature_dates).isoformat() if feature_dates else None,
        },
        "counts": {
            "canonical_bars": len(canonical.bars),
            "stable_security_ids": len({row.security_id for row in canonical.identities}),
            "membership_intervals": len(canonical.memberships),
            "assumed_primary_common_membership_intervals": len(memberships),
            "feature_rows_under_primary_common_assumption": len(feature_rows),
            "labels_under_primary_common_assumption": len(labels),
            "calendar_sessions": len(calendar.sessions),
            "materialization_sessions": len(retained_sessions),
            "price_rows": len(prices),
            "corporate_actions": len(actions),
            "dividends_with_payment_and_withholding": len(evidenced_dividends),
            "dividends_without_payment_or_withholding": (
                len(retained_dividends) - len(evidenced_dividends)
            ),
            "delistings_with_payment_recovery": len(evidenced_delistings),
            "delistings_without_payment_date": len(retained_delistings) - len(evidenced_delistings),
            "feature_rows": len(feature_rows),
            "usable_feature_rows": sum(not row.exclusion_reasons for row in feature_rows),
            "excluded_feature_rows": sum(bool(row.exclusion_reasons) for row in feature_rows),
            "labels": len(labels),
            "matured_labels": len(matured),
            "unresolved_labels": len(labels) - len(matured),
            "unresolved_cash_action_labels_retained": sum(
                reason.startswith("cash_action_")
                for reason in (row.unresolved_reason or "" for row in labels)
            ),
            "outcome_conditioned_cash_action_rows_dropped_from_label_artifact": (
                outcome_conditioned_cash_action_rows_dropped
            ),
            "split_assignments": len(splits),
            "nonempty_split_folds": len(nonempty_folds),
            "protocol_ready_folds": len(protocol_ready_folds),
            "matured_label_span_days": matured_span_days,
        },
        "feature_exclusions": exclusions,
        "label_unresolved_reasons": unresolved,
        "split_counts": {
            str(fold): dict(sorted(counts.items())) for fold, counts in sorted(split_counts.items())
        },
        "nonempty_split_fold_ids": list(nonempty_folds),
        "protocol_ready_fold_ids": list(protocol_ready_folds),
        "fold_date_coverage": {
            str(fold): {
                split: {
                    "expected_decision_dates": len(expected_dates[(fold, split)]),
                    "observed_matured_decision_dates": len(dates_by_fold_split[(fold, split)]),
                    "missing_decision_dates": len(
                        expected_dates[(fold, split)] - dates_by_fold_split[(fold, split)]
                    ),
                }
                for split in ("train", "validation", "test")
            }
            for fold in sorted({window.index for window in windows})
        },
        "protocol_ready_definition": {
            "split_origin": split_start.isoformat(),
            "all_expected_monthly_decisions_present_after_actual_interval_purge": True,
            "cash_action_completeness_evaluated_separately": True,
        },
        "feature_names": list(R3_FEATURE_NAMES),
        "notes": [
            "All V1/V2-inspected history remains development data.",
            "Unresolved cash-action outcomes are retained and never assigned to a split.",
            "No model fitting, optimization, return simulation or objective claim was performed.",
            (
                "Removing the versioned primary/common-stock assumption would exclude all "
                f"{len(feature_rows)} feature rows and all {len(labels)} attempted labels."
            ),
        ],
    }
    return R3Materialization(feature_rows, labels, splits, register, report)


def write_r3_materialization(result: R3Materialization, output_directory: Path) -> dict[str, str]:
    """Write deterministic Parquet/JSON artifacts and return their physical hashes."""
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as error:
        raise ValueError("pyarrow is required for R3 dataset materialization") from error
    output_directory.mkdir(parents=True, exist_ok=True)
    feature_records = []
    for row in result.feature_rows:
        record = {
            "security_id": row.security_id,
            "decision_date": row.decision_date,
            "feature_cutoff": row.feature_cutoff,
            "source_available_at": row.source_available_at,
            "membership_from": row.membership_from,
            "membership_until_exclusive": row.membership_until_exclusive,
            "raw_series_id": row.raw_series_id,
            "adjusted_series_id": row.adjusted_series_id,
            "exclusion_reasons": list(row.exclusion_reasons),
            "feature_version": row.feature_version,
        }
        record.update(dict(zip(R3_FEATURE_NAMES, row.values, strict=False)))
        feature_records.append(record)
    label_records = [asdict(row) for row in result.labels]
    split_records = [asdict(row) for row in result.splits]
    paths = {
        "features": output_directory / "features.parquet",
        "labels": output_directory / "labels.parquet",
        "splits": output_directory / "splits.parquet",
        "register": output_directory / "experiment_register.json",
        "report": output_directory / "materialization_report.json",
    }
    for key, records in (
        ("features", feature_records),
        ("labels", label_records),
        ("splits", split_records),
    ):
        table = pa.Table.from_pylist(records)
        pq.write_table(table, paths[key], compression="zstd", version="2.6")
    paths["register"].write_text(
        json.dumps(asdict(result.register), sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    artifact_hashes = {key: _sha256(path) for key, path in paths.items() if key != "report"}
    report = dict(result.report)
    report["artifact_sha256"] = artifact_hashes
    report["dataset_sha256"] = hashlib.sha256(
        json.dumps(artifact_hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    paths["report"].write_text(
        json.dumps(report, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    artifact_hashes["report"] = _sha256(paths["report"])
    return artifact_hashes
