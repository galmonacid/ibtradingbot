"""Deterministic post-Step-3 remediation and governance records.

This module only verifies preserved evidence and writes decision records. It has
no imports from learning, scoring, portfolio, simulation, or backtest modules.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from src.config.r3_post_step3 import R3PostStep3Config


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_new(path: Path, value: object) -> str:
    if path.exists():
        raise FileExistsError(f"immutable artifact already exists: {path}")
    payload = canonical_bytes(value)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def directory_manifest(directory: Path) -> list[dict[str, object]]:
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    return [
        {
            "relative_path": path.relative_to(directory).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(item for item in directory.rglob("*") if item.is_file())
    ]


def directory_identity(manifest: list[dict[str, object]]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def _verify_hash(path: Path, expected: str) -> dict[str, object]:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"preserved evidence hash mismatch: {path}")
    return {
        "path": path.as_posix(),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "verified": True,
    }


def _verify_model_manifest(directory: Path) -> dict[str, object]:
    path = directory / "model_manifest.json"
    rows: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"invalid model manifest: {path}")
    checked = 0
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError(f"invalid model manifest row: {path}")
        model_path = directory / "models" / str(raw["path"])
        if sha256_file(model_path) != raw["file_sha256"]:
            raise ValueError(f"preserved model hash mismatch: {model_path}")
        checked += 1
    return {"path": path.as_posix(), "entries": checked, "all_referenced_models_verified": True}


def verify_preserved_evidence(config: R3PostStep3Config) -> dict[str, object]:
    step3 = Path(config.step3_directory)
    step3_manifest_path = step3 / "artifact_hash_manifest.json"
    step3_manifest: object = json.loads(step3_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(step3_manifest, dict) or not isinstance(
        step3_manifest.get("artifacts"), dict
    ):
        raise ValueError("invalid Step 3 artifact manifest")
    step3_artifacts = step3_manifest["artifacts"]
    verified_step3: list[dict[str, object]] = []
    for name, expected in sorted(step3_artifacts.items()):
        verified_step3.append(_verify_hash(step3 / str(name), str(expected)))
    calculated_identity = sha256_bytes(canonical_bytes(step3_artifacts))
    if calculated_identity != config.step3_package_identity:
        raise ValueError("Step 3 package identity mismatch")
    if step3_manifest.get("package_identity") != config.step3_package_identity:
        raise ValueError("Step 3 recorded package identity mismatch")

    dataset = Path(config.corrected_dataset_directory)
    dataset_report_path = dataset / "materialization_report.json"
    dataset_report: object = json.loads(dataset_report_path.read_text(encoding="utf-8"))
    if not isinstance(dataset_report, dict):
        raise ValueError("invalid corrected dataset report")
    artifact_hashes = dataset_report.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ValueError("corrected dataset lacks artifact hashes")
    calculated_dataset_identity = sha256_bytes(
        json.dumps(artifact_hashes, sort_keys=True, separators=(",", ":")).encode()
    )
    if calculated_dataset_identity != config.corrected_dataset_identity:
        raise ValueError("corrected dataset identity mismatch")
    corrected_dataset_files = [
        _verify_hash(dataset / f"{name}.parquet", str(expected))
        if name in {"features", "labels", "splits", "scoring"}
        else _verify_hash(dataset / "experiment_register.json", str(expected))
        for name, expected in sorted(artifact_hashes.items())
    ]
    if sha256_file(dataset / "scoring.parquet") != config.corrected_scoring_sha256:
        raise ValueError("corrected scoring hash mismatch")

    corrected_run = Path(config.corrected_run_directory)
    original_run = Path(config.preserved_r3_3_directory)
    direct_checks = [
        _verify_hash(step3 / "failure_register.json", config.step3_failure_register_sha256),
        _verify_hash(corrected_run / "development_report.json", config.corrected_report_sha256),
        _verify_hash(original_run / "development_report.json", config.preserved_r3_3_report_sha256),
        _verify_hash(
            original_run / "experiment_register.json", config.preserved_r3_3_register_sha256
        ),
        _verify_hash(
            original_run / "model_manifest.json", config.preserved_r3_3_model_manifest_sha256
        ),
    ]
    original_models = _verify_model_manifest(original_run)
    corrected_models = _verify_model_manifest(corrected_run)
    return {
        "verification_version": "r3-post-step3-preservation-v1",
        "all_verified": True,
        "step3_package_identity": calculated_identity,
        "step3_artifacts": verified_step3,
        "corrected_dataset_identity": calculated_dataset_identity,
        "corrected_dataset_artifacts": corrected_dataset_files,
        "direct_checks": direct_checks,
        "model_manifests": [original_models, corrected_models],
        "preservation_rule": "inputs were read and hashed only; no input artifact is rewritten or re-signed",
    }


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def prospective_date_support(config: R3PostStep3Config) -> dict[str, object]:
    price_start = date.fromisoformat(config.price_only_start)
    sec_start = date.fromisoformat(config.sec_sample_start)
    nominal_train_end = _add_years(sec_start, config.initial_train_years)
    nominal_validation_end = _add_years(nominal_train_end, config.validation_years)
    nominal_test_end = _add_years(nominal_validation_end, config.test_years)
    return {
        "calculation_version": "r3-post-step3-date-support-v1",
        "frozen_protocol": {
            "price_only_start": price_start.isoformat(),
            "required_folds": config.required_protocol_folds,
            "initial_train_years": config.initial_train_years,
            "validation_years": config.validation_years,
            "test_years": config.test_years,
            "step_years": config.step_years,
            "purge_sessions": config.purge_sessions,
            "supported_complete_enriched_folds": 0,
        },
        "sec_sample": {
            "first_causal_fact_date": sec_start.isoformat(),
            "precoverage_gap_days": (sec_start - price_start).days,
            "precoverage_gap_years_approx": round((sec_start - price_start).days / 365.2425, 6),
        },
        "prospective_lower_bound_only": {
            "earliest_possible_enriched_training_start": sec_start.isoformat(),
            "nominal_eight_year_training_end": nominal_train_end.isoformat(),
            "nominal_two_year_validation_end": nominal_validation_end.isoformat(),
            "nominal_one_year_test_end": nominal_test_end.isoformat(),
            "qualification": "sample-only calendar arithmetic; exact monthly XNYS boundaries, issuer-wide complete-case coverage, latency, staleness, identity, labels and purging are not established",
            "approval": "not a proposed or executed protocol change",
        },
        "missingness_distinction": {
            "training_only_imputation": "may replace sporadic nulls using statistics fitted only on observed training rows, while preserving indicators",
            "not_genuine_enriched_evaluation": "pre-2009 rows have no sampled causal SEC observation; imputing an entirely absent era creates no historical fundamental evidence and cannot make a frozen fold enriched",
            "rule": "an all-missing pre-coverage feature family cannot be counted as causal enriched support",
        },
    }


def identity_requirements() -> dict[str, object]:
    return {
        "decision": "current local master cannot be repaired from existing evidence alone",
        "reason": "it has stable local IDs and symbol intervals, but no authoritative dated CIK-to-security/share-class mapping; Step 3 manual joins are non-qualification-grade",
        "required_mapping_fields": [
            "issuer identifier and CIK",
            "stable security-level identifier independent of ticker",
            "share-class identifier and rights/class label",
            "ticker and exchange with effective_from and effective_to_exclusive",
            "issuer/name change with announcement and effective timestamps",
            "predecessor/successor identity for mergers, spinoffs and reorganizations",
            "delisting/acquisition effective date, consideration and recovery provenance",
            "source publication/availability timestamp and immutable source hash",
        ],
        "minimum_causal_source_evidence": [
            "dated primary filings or official issuer/exchange notices identifying the affected class",
            "dated corporate-action records linking predecessor and successor securities",
            "a historical security identifier source covering multiple classes and ticker changes",
            "explicit permission/licence record for local research use and any retained raw evidence",
        ],
        "known_cases": {
            "multiple_classes": [
                "Alphabet GOOG/GOOGL must remain distinct securities sharing one issuer",
                "Berkshire class and vendor-symbol variants must distinguish class identity from notation",
            ],
            "ticker_and_name_changes": [
                "Meta FB-to-META must preserve one security only when dated evidence proves continuity; the duplicate local META interval must be resolved"
            ],
            "mergers_and_delistings": [
                "Activision and Twitter require dated terminal action, consideration/recovery and successor treatment",
                "reorganizations must not infer continuity from matching issuer names",
            ],
        },
        "validation_tests": [
            "one issuer may map to multiple simultaneously active security classes without collapsing them",
            "a ticker change preserves a security ID only across a source-evidenced effective boundary",
            "symbol punctuation aliases do not create duplicate securities or merge distinct classes",
            "merger and delisting intervals are half-open, non-overlapping and source-dated",
            "as-of joins are prefix invariant when later metadata is appended",
            "unknown or conflicting mappings fail closed and never fall back to name/ticker matching",
            "current metadata cannot populate an earlier historical mapping",
        ],
        "present_day_metadata_substitution": {
            "allowed": False,
            "disposition": "explicitly rejected as historical mapping evidence",
        },
        "permission_status": "unknown until candidate source terms are captured; no source was selected or accessed in this step",
    }


def sector_macro_decisions() -> dict[str, object]:
    return {
        "sector": {
            "status": "feature family remains rejected under the current protocol",
            "required_properties": [
                "security- or issuer-linked classification with stable identifiers",
                "classification system and version",
                "effective_from and effective_to_exclusive",
                "publication/availability timestamp distinct from economic effective date",
                "historical revisions retained rather than overwritten",
                "coverage for inactive, acquired and delisted securities",
                "source hash, access terms and redistribution/local-use permission",
            ],
            "search_decision": "no executable source search is justified while the independent SEC-history blocker leaves 0/9 frozen folds; a later bounded official-source feasibility search requires explicit authority and cannot broaden into alternative data",
            "present_day_sector_backfill_allowed": False,
        },
        "macro": {
            "status": "feature family remains rejected under the current protocol",
            "access_blocker": "official FRED API documentation states every web-service request requires a 32-character registered API key; requesting/viewing a key requires account login; none was supplied or created",
            "official_documents": [
                {
                    "url": "https://fred.stlouisfed.org/docs/api/fred/alfred.html",
                    "step3_source_sha256": "63e00e2846a72af8d5bd8b2b224efe2bb69cf8f4def932dd0add7bcbb4c255ff",
                },
                {
                    "url": "https://fred.stlouisfed.org/docs/api/api_key.html",
                    "step3_source_sha256": "afa2f2365b87691063cce30c38eca118ba274253d19857abed361e606bca7540",
                },
            ],
            "no_account_bulk_route": "not established by the frozen official documentation; it documents keyed web-service access and supplies no verified public no-account vintage-observation bulk route",
            "credential_action": "none: no account, key or credential was created, requested or supplied",
            "revised_fred_substitution_allowed": False,
        },
    }


def source_permission_cost_decisions() -> list[dict[str, object]]:
    return [
        {
            "path": "SEC facts",
            "observed_cost_gbp": 0,
            "cost_basis": "observed bounded public read-only access with no charge",
            "assumed_cost_gbp": None,
            "unknown_costs": [
                "ongoing storage/maintenance labor",
                "full-universe refresh operations",
            ],
            "permission": "bounded public read-only research access observed; redistribution not established",
            "can_evaluate_remediation_without_paid_source": True,
            "limitation": "free access does not solve pre-2009 coverage",
        },
        {
            "path": "issuer-security identity",
            "observed_cost_gbp": None,
            "cost_basis": "no qualifying source acquired",
            "assumed_cost_gbp": None,
            "unknown_costs": ["historical identifier source", "licence", "maintenance"],
            "permission": "unknown",
            "can_evaluate_remediation_without_paid_source": "unknown; public primary evidence may support cases, but complete scalable coverage is unproven",
        },
        {
            "path": "dated sector metadata",
            "observed_cost_gbp": None,
            "cost_basis": "no source audited",
            "assumed_cost_gbp": None,
            "unknown_costs": [
                "subscription or licence",
                "historical revision access",
                "maintenance",
            ],
            "permission": "unknown",
            "can_evaluate_remediation_without_paid_source": "not established",
        },
        {
            "path": "ALFRED vintages",
            "observed_cost_gbp": None,
            "cost_basis": "documentation accessed but observations not accessed",
            "assumed_cost_gbp": None,
            "unknown_costs": ["access continuity", "operational maintenance"],
            "permission": "documentation public; keyed observation access not exercised",
            "can_evaluate_remediation_without_paid_source": "monetary charge not established; impossible here without a supplied credential or a separately verified official no-account route",
        },
        {
            "path": "local storage/CPU/no hosting",
            "observed_cost_gbp": None,
            "cost_basis": "existing resources",
            "assumed_cost_gbp": 0,
            "unknown_costs": ["incremental electricity", "future hosting", "labor"],
            "permission": "not applicable",
            "can_evaluate_remediation_without_paid_source": True,
        },
    ]


def blocker_traceability() -> list[dict[str, object]]:
    return [
        {
            "blocker": "SEC historical coverage",
            "step3_evidence": "first sampled causal fact 2009-07-23 versus frozen start 1999-01-29; 0/9 complete enriched folds",
            "disposition": "unresolved and not repairable by imputation; only a separately authorized future protocol decision could consider later windows",
            "current_protocol_solved": False,
        },
        {
            "blocker": "issuer-to-security identity",
            "step3_evidence": "Alphabet, Meta and Berkshire map one CIK to multiple/overlapping local IDs without dated authority",
            "disposition": "requirements defined; existing evidence insufficient; remediation not executed",
            "current_protocol_solved": False,
        },
        {
            "blocker": "sector metadata",
            "step3_evidence": "no dated causal classification source established",
            "disposition": "feature family remains rejected; source search deferred pending authority and cannot solve SEC history",
            "current_protocol_solved": False,
        },
        {
            "blocker": "macro vintages",
            "step3_evidence": "official API requires an unsupplied registered key",
            "disposition": "no-account bulk route not established from frozen official documentation; no credentials created; revised FRED forbidden",
            "current_protocol_solved": False,
        },
        {
            "blocker": "economics",
            "step3_evidence": "SEC bounded access observed at £0; other recurring source costs unknown",
            "disposition": "unknowns preserved; no affordability claim",
            "current_protocol_solved": False,
        },
    ]


def governance_options() -> list[dict[str, object]]:
    common_risks = ["future leakage", "survivorship selection", "present-day metadata substitution"]
    return [
        {
            "option": "A",
            "title": "stop the enriched-feature research direction",
            "evidence_prerequisites": [],
            "expected_causal_date_support": "none required; no enriched dataset is built",
            "source_access_permission": "no new source access or permission",
            "costs": {
                "known": "£0 incremental source spend",
                "assumed": "£0 local archival overhead",
                "unknown": [],
            },
            "implementation_work": [
                "retain packages and rejected feature status",
                "make no research or trading changes",
            ],
            "risks": common_risks,
            "can_proceed_without_new_authority": True,
            "stop_conditions": [
                "immediate and permanent for this direction unless the user explicitly reopens it"
            ],
        },
        {
            "option": "B",
            "title": "remediate identity, sector and macro evidence while retaining the existing protocol",
            "evidence_prerequisites": [
                "dated security/class mappings",
                "dated sector classification with revision history",
                "official vintage observations with lawful access",
                "permission and cost records",
            ],
            "expected_causal_date_support": "identity/sector/macro support unknown; SEC remains no earlier than sampled 2009-07-23",
            "source_access_permission": "new source access/terms or a supplied credential may be required; no purchase/account/credential action is implicit",
            "costs": {
                "known": "bounded SEC access observed at £0",
                "assumed": "existing local compute/storage at £0",
                "unknown": ["identity", "sector", "ALFRED operations", "maintenance"],
            },
            "implementation_work": [
                "source feasibility only",
                "build and test causal as-of mappings",
                "record permissions and complete recurring budget",
            ],
            "risks": common_risks + ["effort cannot repair the SEC pre-2009 absence"],
            "can_proceed_without_new_authority": False,
            "solves_sec_history_blocker": False,
            "stop_conditions": [
                "any use requires account creation, purchase, subscription or terms acceptance without exact authority",
                "no dated source or permission",
                "cost remains materially unknown",
                "mapping or prefix-invariance tests fail",
                "attempt to claim 9/9 enriched folds",
            ],
        },
        {
            "option": "C",
            "title": "propose a future protocol-amendment decision package",
            "evidence_prerequisites": [
                "complete remediation evidence and measured causal coverage",
                "explicit rationale for later start/window geometry",
                "freshness and qualification implications",
                "new user authorization before any amendment",
            ],
            "expected_causal_date_support": "prospective lower bound starts 2009-07-23; exact support is unestablished and sample-only",
            "source_access_permission": "all selected sources must have recorded lawful access and continuity",
            "costs": {
                "known": "bounded SEC access observed at £0",
                "assumed": "none for missing sources",
                "unknown": ["full recurring data and operations budget"],
            },
            "implementation_work": [
                "decision analysis only",
                "separate versioned amendment proposal",
                "no data fitting, experiment registration or outcome inspection",
            ],
            "risks": common_risks
            + [
                "shorter or later evidence window",
                "reusing inspected development dates",
                "silent weakening of gates",
            ],
            "can_proceed_without_new_authority": False,
            "stop_conditions": [
                "user does not explicitly authorize a separate amendment decision",
                "coverage cannot support a predeclared design",
                "fresh-evidence boundary is not defensible",
                "any proposal weakens risk, label, cost or qualification rules by implication",
            ],
        },
    ]


def build_decision_artifacts(
    config: R3PostStep3Config,
    *,
    provenance: dict[str, object],
) -> dict[str, object]:
    preservation = verify_preserved_evidence(config)
    step3_manifest = directory_manifest(Path(config.step3_directory))
    input_manifest = {
        "manifest_version": "r3-post-step3-inputs-v1",
        "step3": {
            "path": config.step3_directory,
            "identity": directory_identity(step3_manifest),
            "files": step3_manifest,
        },
        "corrected_dataset": {
            "path": config.corrected_dataset_directory,
            "identity": directory_identity(
                directory_manifest(Path(config.corrected_dataset_directory))
            ),
        },
        "corrected_run": {
            "path": config.corrected_run_directory,
            "identity": directory_identity(
                directory_manifest(Path(config.corrected_run_directory))
            ),
        },
        "preserved_r3_3": {
            "path": config.preserved_r3_3_directory,
            "identity": directory_identity(
                directory_manifest(Path(config.preserved_r3_3_directory))
            ),
        },
    }
    return {
        "verified_input_artifact_manifest.json": input_manifest,
        "preserved_evidence_verification.json": preservation,
        "step3_blocker_traceability.json": blocker_traceability(),
        "identity_remediation_requirements.json": identity_requirements(),
        "sector_macro_decision_records.json": sector_macro_decisions(),
        "source_permission_cost_decision_table.json": source_permission_cost_decisions(),
        "prospective_date_support.json": prospective_date_support(config),
        "governance_options_register.json": {
            "selected_disposition": "define prerequisites before any separately authorized future amendment can be considered",
            "options_are_not_ranked_by_performance_or_investment_merit": True,
            "options": governance_options(),
        },
        "no_protocol_amendment_executed.json": {
            "protocol_amendment_executed": False,
            "unchanged": [
                "8/2/1 split geometry",
                "31-session purge",
                "folds and dates",
                "labels",
                "portfolio policy",
                "risk controls",
                "source contract",
                "candidate budget",
            ],
            "future_amendment_requires_explicit_user_decision": True,
        },
        "no_step4_registration_created.json": {
            "step4_authorized": False,
            "step4_registration_created": False,
            "experiment_registration_created": False,
            "prohibited_actions_performed": {
                "model_fitting": False,
                "score_generation": False,
                "portfolio_simulation": False,
                "backtest": False,
                "performance_comparison": False,
                "candidate_selection": False,
                "fresh_holdout_access": False,
                "broker_or_account_change": False,
            },
        },
        "dependency_environment_provenance.json": provenance,
    }


def validate_decision_artifacts(artifacts: dict[str, object]) -> None:
    required = {
        "verified_input_artifact_manifest.json",
        "preserved_evidence_verification.json",
        "step3_blocker_traceability.json",
        "identity_remediation_requirements.json",
        "sector_macro_decision_records.json",
        "source_permission_cost_decision_table.json",
        "prospective_date_support.json",
        "governance_options_register.json",
        "no_protocol_amendment_executed.json",
        "no_step4_registration_created.json",
        "dependency_environment_provenance.json",
    }
    if set(artifacts) != required:
        raise ValueError("decision artifact set changed")
    register = artifacts["governance_options_register.json"]
    if not isinstance(register, dict) or not isinstance(register.get("options"), list):
        raise ValueError("invalid governance options register")
    if [row.get("option") for row in register["options"]] != ["A", "B", "C"]:
        raise ValueError("exactly governance options A, B and C are required")
    no_amendment = artifacts["no_protocol_amendment_executed.json"]
    no_step4 = artifacts["no_step4_registration_created.json"]
    if (
        not isinstance(no_amendment, dict)
        or no_amendment.get("protocol_amendment_executed") is not False
    ):
        raise ValueError("protocol changes are prohibited")
    if not isinstance(no_step4, dict) or any(
        no_step4.get(key) is not False
        for key in (
            "step4_authorized",
            "step4_registration_created",
            "experiment_registration_created",
        )
    ):
        raise ValueError("Step 4 registration is prohibited")
