"""Inventory later-period source gaps without reducing the historical universe."""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import io
import json
import platform
import subprocess
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config.r3_step3 import load_r3_step3_config
from src.data.source_adapters import transform_identity_source, transform_membership_source
from src.data.trusted_historical import (
    DatedSecurityIdentity,
    SecurityMembershipInterval,
    build_security_membership_intervals,
    verify_source_snapshot,
)
from src.research.r3_source_feasibility import canonical_bytes, sha256_bytes
from src.research.r3_universe_coverage import audit_universe, discover_symbol_candidates


def materialize(output: Path, timestamp: datetime) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    if timestamp.utcoffset() is None:
        raise ValueError("aware timestamp required")
    hashes: dict[str, str] = {}

    def read(path: Path, expected: str | None = None) -> bytes:
        payload = path.read_bytes()
        digest = sha256_bytes(payload)
        if expected is not None and digest != expected:
            raise ValueError(f"hash mismatch: {path}")
        hashes[str(path)] = digest
        return payload

    membership_manifest = Path("data/local/phase3_manifests/membership.json")
    identity_manifest = Path("data/local/phase3_manifests/identity.json")
    membership_root = Path("data/local/phase3_sources/historical_sp500_constituents")
    identity_root = Path("data/local/phase3_sources/index-constitution")
    for manifest in (membership_manifest, identity_manifest):
        read(manifest)
    membership = transform_membership_source(
        verify_source_snapshot(membership_manifest, membership_root), membership_root,
        "sp_500_historical_components.csv",
    )
    identity = transform_identity_source(
        verify_source_snapshot(identity_manifest, identity_root), identity_root, "event/us.csv",
        coverage_start=date(1996, 1, 1),
        known_symbols=tuple(sorted({symbol for snapshot in membership.memberships
                                    for symbol in snapshot.symbols} | {"SPY"})),
        preserve_symbol_reuse=True,
    )
    native = build_security_membership_intervals(
        membership.memberships, DatedSecurityIdentity(identity.parsed.identity_intervals),
        source_version=membership.snapshot.manifest_sha256,
    )
    period = json.loads(read(
        Path("data/local/r3_later_period_20261007_design_v2/report.json"),
        "053fa6b6204fde76a94831fde54c9110ecf52027604839639f92f6bc832dfc08",
    ))
    canonical_root = Path("data/local/phase3_build_v3/canonical")
    canonical = json.loads(read(
        canonical_root / "canonical_manifest.json",
        "a669110a7f575f8c3883dbcf7f9ab9203a21031f8f27d0789405ba80692d5dc3",
    ))
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    member_source = next(row for row in canonical["files"] if row["path"] == "membership.parquet")
    member_rows = pq.read_table(io.BytesIO(read(
        canonical_root / member_source["path"], member_source["sha256"]
    ))).to_pylist()
    retained = tuple(SecurityMembershipInterval(**row) for row in member_rows)
    feature_source = period["configuration"]["features"]
    features = pq.read_table(io.BytesIO(read(
        Path(feature_source["path"]), feature_source["sha256"]
    )), columns=["security_id", "decision_date", "exclusion_reasons"]).to_pylist()
    sample_path = Path("config.r3-step3-feasibility.yaml")
    read(sample_path)
    sample = load_r3_step3_config(sample_path)
    candidates = {security_id: row.cik for row in sample.sample for security_id in row.security_ids}
    report = audit_universe(
        tuple(date.fromisoformat(row["date"]) for row in period["monthly_coverage"]),
        native, retained,
        ((row["security_id"], row["decision_date"], not row["exclusion_reasons"])
         for row in features), candidates,
    )
    symbols: dict[str, set[str]] = {}
    for interval in identity.parsed.identity_intervals:
        symbols.setdefault(interval.security_id, set()).add(interval.symbol)
    for row in report["remediation_queue"]:
        row["source_symbols"] = sorted(symbols.get(row["security_id"], set()))
    provider = json.loads(read(
        Path("data/local/phase3_tiingo_v2/tiingo_manifest.json"),
        "343d182a2d7d9388c2a5936be723d33f0ca500aa0bd333b0047481067f68d3f1",
    ))
    for row in report["remediation_queue"]:
        row["provider_requests"] = [
            {"provider_symbol": request["provider_symbol"], "status": request["status"],
             "request_id": request["request_id"]}
            for request in provider["requests"] if request["security_id"] == row["security_id"]
        ]
    discovery_root = Path("data/local/r3_source_discovery_20261007_v1")
    access = json.loads(read(discovery_root / "access_manifest.json"))
    discovery_payloads = {
        row["file"]: read(discovery_root / row["file"], row["sha256"])
        for row in access if row.get("status") == 200
    }
    with zipfile.ZipFile(io.BytesIO(discovery_payloads["tiingo_supported.zip"])) as archive:
        provider_rows = list(csv.DictReader(io.StringIO(
            archive.read("supported_tickers.csv").decode("utf-8")
        )))
    sec_rows = list(json.loads(discovery_payloads["sec_company_tickers.json"]).values())
    for row in report["remediation_queue"]:
        row["discovery"] = discover_symbol_candidates(
            row["source_symbols"], provider_rows, sec_rows
        )
    report["discovery_sources"] = access
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True
    ).splitlines()
    tree = {name: sha256_bytes(Path(name).read_bytes())
            for name in sorted(set(paths)) if Path(name).is_file()}
    report.update({
        "run_timestamp": timestamp.isoformat(), "source_hashes": hashes,
        "implementation_files": tree,
        "implementation_tree_sha256": sha256_bytes(canonical_bytes(tree)),
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("pyarrow", "PyYAML")},
        "randomness_used": False, "returns_inspected": False,
    })
    payload = canonical_bytes(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    return {key: report[key] for key in (
        "unique_native_security_ids", "native_security_months",
        "missing_retained_membership_security_months", "missing_usable_feature_security_months"
    )} | {"report_sha256": sha256_bytes(payload)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-timestamp", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    print(json.dumps(materialize(args.output, args.run_timestamp), sort_keys=True))


if __name__ == "__main__":
    main()
