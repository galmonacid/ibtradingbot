"""Causal sample-only joins for a sparse fundamental ablation."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.config.r3 import _UniqueLoader
from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import LearningObservation
from src.learning.r3_enriched import ENRICHED_FEATURE_NAMES, RATIO_NAMES, EnrichedObservation
from src.research.r3_iteration import load_config, sha256


def load_enriched_config(path: Path) -> dict[str, Any]:
    value: Any = yaml.load(path.read_text(), Loader=_UniqueLoader)
    expected = {
        "contract",
        "price_config",
        "price_dataset",
        "baseline_run",
        "baseline_manifest_sha256",
        "fundamental_report",
        "fundamental_report_sha256",
        "join_audit",
        "join_audit_sha256",
        "joined_security_ids",
        "feature_names",
        "missing_policy",
        "seed",
        "ridge_alpha",
        "xgboost",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("unexpected enriched configuration fields")
    if value["contract"] != "r3-fundamental-iteration-v1":
        raise ValueError("unsupported enriched experiment contract")
    if value["missing_policy"] != "zero_plus_indicator":
        raise ValueError("unregistered missingness policy")
    if value["feature_names"] != list(RATIO_NAMES):
        raise ValueError("fundamental order differs from registered schema")
    security_ids = value["joined_security_ids"]
    if not isinstance(security_ids, list) or len(security_ids) != 8 or len(set(security_ids)) != 8:
        raise ValueError("exactly eight distinct audited security IDs required")
    for name in ("baseline_manifest_sha256", "fundamental_report_sha256", "join_audit_sha256"):
        digest = value[name]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("invalid source hash")
    price = load_config(Path(value["price_config"]))
    if (
        value["price_dataset"] != price["dataset"]
        or value["seed"] != price["seed"]
        or value["ridge_alpha"] != price["ridge_alpha"]
        or value["xgboost"] != price["xgboost"]
    ):
        raise ValueError("ablation must share original data and model parameters")
    return dict(value)


def verified_sources(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    for name, digest in (
        ("fundamental_report", "fundamental_report_sha256"),
        ("join_audit", "join_audit_sha256"),
    ):
        if sha256(Path(config[name])) != config[digest]:
            raise ValueError(f"source hash mismatch: {name}")
    run = Path(config["baseline_run"])
    manifest_path = run / "artifact_manifest.json"
    if sha256(manifest_path) != config["baseline_manifest_sha256"]:
        raise ValueError("baseline manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("invalid baseline manifest")
    for name, digest in manifest.items():
        if sha256(run / name) != digest:
            raise ValueError(f"baseline artifact changed: {name}")
    report = json.loads(Path(config["fundamental_report"]).read_text())
    audit = json.loads(Path(config["join_audit"]).read_text())
    if (
        report.get("contract") != "r3-issuer-fundamental-coverage-v1"
        or report.get("feature_version") != "r3-sec-period-aligned-ratios-v1"
        or report.get("processing_latency_hours") != 24
        or not isinstance(audit, list)
    ):
        raise ValueError("unexpected fundamental/identity evidence contract")
    return report, audit, manifest


def admitted_sample_map(
    audit: Sequence[dict[str, Any]], selected_ids: Sequence[str], available_ciks: set[str]
) -> dict[str, str]:
    """Admit only the exact eight one-to-one, manually reviewed sample rows."""
    selected = set(selected_ids)
    mapping: dict[str, str] = {}
    for row in audit:
        ids = row.get("security_ids")
        if not isinstance(ids, list) or not selected.intersection(ids):
            continue
        if row.get("join_status") != "manually_matched_sample_only" or len(ids) != 1:
            raise ValueError("ambiguous or unaudited issuer/security join")
        security_id = ids[0]
        cik = row.get("cik")
        if security_id in mapping or not isinstance(cik, str) or cik not in available_ciks:
            raise ValueError("duplicate or unavailable issuer mapping")
        mapping[security_id] = cik
    if set(mapping) != selected or len(set(mapping.values())) != len(mapping):
        raise ValueError("configured sample join is missing or nonunique")
    return mapping


def indexed_ratios(report: Mapping[str, Any]) -> dict[tuple[str, date], dict[str, Any]]:
    index: dict[tuple[str, date], dict[str, Any]] = {}
    for row in report["monthly"]:
        cutoff = datetime.fromisoformat(row["decision_at"])
        if cutoff.utcoffset() is None:
            raise ValueError("fundamental cutoff must be timezone-aware")
        key = row["cik"], cutoff.date()
        if key in index:
            raise ValueError("duplicate issuer decision")
        if [item["name"] for item in row["ratios"]] != list(RATIO_NAMES):
            raise ValueError("fundamental ratio schema mismatch")
        index[key] = row
    return index


def enrich(
    rows: Sequence[LearningObservation],
    feature_cutoffs: Mapping[tuple[str, date], datetime],
    mapping: Mapping[str, str],
    ratios: Mapping[tuple[str, date], dict[str, Any]],
) -> tuple[tuple[EnrichedObservation, ...], dict[str, object]]:
    output = []
    availability: Counter[str] = Counter()
    joined_security_months = 0
    for row in rows:
        key = row.security_id, row.decision_date
        cutoff = feature_cutoffs[key]
        if cutoff.utcoffset() is None:
            raise ValueError("feature cutoff must be timezone-aware")
        cik = mapping.get(row.security_id)
        source = ratios.get((cik, row.decision_date)) if cik else None
        if cik is not None:
            joined_security_months += 1
        if source is not None:
            source_close = datetime.fromisoformat(source["decision_at"])
            if source_close.date() != row.decision_date or source_close > cutoff:
                raise ValueError("SEC decision close follows price feature cutoff")
        extra: list[float] = []
        for name, position in zip(RATIO_NAMES, range(len(RATIO_NAMES)), strict=True):
            item = source["ratios"][position] if source is not None else None
            value = None if item is None else item["value"]
            if value is not None:
                assert item is not None
                available_at = datetime.fromisoformat(item["available_at"])
                if available_at.utcoffset() is None or available_at > cutoff:
                    raise ValueError("future or naive SEC fact availability")
                if item["name"] != name or not math.isfinite(value):
                    raise ValueError("invalid fundamental ratio")
                availability[name] += 1
                extra.extend((float(value), 0.0))
            else:
                extra.extend((0.0, 1.0))
        observation = EnrichedObservation(
            row.security_id,
            row.decision_date,
            row.label_available_at,
            row.features + tuple(extra),
            row.target,
        )
        output.append(observation)
    if any(len(row.features) != len(ENRICHED_FEATURE_NAMES) for row in output):
        raise ValueError("enriched feature count mismatch")
    return tuple(output), {
        "scoring_rows": len(output),
        "joined_security_months": joined_security_months,
        "unjoined_security_months": len(output) - joined_security_months,
        "observed_ratio_counts": dict(availability),
        "feature_names": ENRICHED_FEATURE_NAMES,
        "base_feature_count": len(R3_FEATURE_NAMES),
    }
