"""Offline, source-bound SEC cover audit; no identity-master mutation or model fitting."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.data.r3_identity import audit_sec_cover
from src.research.r3_source_feasibility import canonical_bytes, sha256_bytes


def _verified(path: str, expected: str) -> bytes:
    payload = Path(path).read_bytes()
    if sha256_bytes(payload) != expected:
        raise ValueError(f"source hash mismatch: {path}")
    return payload


def materialize(manifest_path: Path, output: Path, timestamp: datetime) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"immutable output already exists: {output}")
    if timestamp.utcoffset() is None:
        raise ValueError("run timestamp must be timezone-aware")
    manifest_payload = manifest_path.read_bytes()
    manifest = json.loads(manifest_payload)
    if manifest.get("contract_version") != "r3-sec-cover-audit-input-v1":
        raise ValueError("unsupported manifest contract")
    latency = manifest["processing_latency_hours"]
    if type(latency) is not int or latency < 0:
        raise ValueError("nonnegative integer processing latency required")
    rows = manifest["filings"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("filings must be a nonempty list")
    audits = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        identity = (row["cik"], row["accession"])
        if identity in seen:
            raise ValueError("duplicate issuer/accession")
        seen.add(identity)
        payload = _verified(row["document_path"], row["document_sha256"])
        metadata = json.loads(_verified(row["acceptance_path"], row["acceptance_sha256"]))
        recent = metadata.get("filings", {}).get("recent", metadata)
        matches = [
            i for i, value in enumerate(recent["accessionNumber"]) if value == row["accession"]
        ]
        if len(matches) != 1:
            raise ValueError("acceptance record must match exactly one accession")
        accepted = datetime.fromisoformat(recent["acceptanceDateTime"][matches[0]])
        if accepted.utcoffset() is None or accepted > timestamp:
            raise ValueError("acceptance must be aware and no later than audit time")
        audit = audit_sec_cover(
            payload,
            expected_sha256=row["document_sha256"],
            cik=row["cik"],
            accession=row["accession"],
            accepted_at=accepted,
            processing_latency_hours=latency,
        )
        audits.append({"input": row, **asdict(audit)})
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True
    ).splitlines()
    implementation = {
        name: sha256_bytes(Path(name).read_bytes())
        for name in sorted(set(paths))
        if Path(name).is_file()
    }
    report: dict[str, Any] = {
        "contract_version": "r3-sec-cover-audit-v1",
        "run_timestamp": timestamp.isoformat(),
        "input_manifest_sha256": sha256_bytes(manifest_payload),
        "processing_latency_hours": latency,
        "audits": audits,
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_committed_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        "implementation_files": implementation,
        "implementation_tree_sha256": sha256_bytes(canonical_bytes(implementation)),
        "python": platform.python_version(),
        "randomness_used": False,
        "security_master_modified": False,
        "complete_identity_intervals_established": False,
        "step4_ready": False,
        "limitations": [
            "cover observations only; no automatic common-equity classification",
            "context strings retained; context entities/dimensions not independently validated",
            "no interval, vendor alias, merger, delisting or price-history reconciliation",
            "acceptance plus latency is a retrospective availability assumption",
            "unsupported/incomplete contexts remain explicit; no cross-context borrowing",
        ],
    }
    payload = canonical_bytes(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    return {
        "report_sha256": sha256_bytes(payload),
        "filings": len(audits),
        "observations": sum(len(row["observations"]) for row in audits),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-timestamp", required=True, type=datetime.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(materialize(args.manifest, args.output, args.run_timestamp), sort_keys=True))


if __name__ == "__main__":
    main()
