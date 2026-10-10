"""Audit issuer-level monthly SEC ratios without admitting historical security joins."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.features.r3_fundamentals import VERSION, fundamental_ratios
from src.research.r3_source_feasibility import (
    canonical_bytes,
    parse_company_facts,
    parse_submissions,
    sha256_bytes,
)


def materialize(
    manifests: tuple[Path, ...], roots: tuple[Path, ...], output: Path, timestamp: datetime,
    *, period_path: Path = Path("data/local/r3_later_period_20261007_design_v2/report.json"),
    period_sha256: str = "053fa6b6204fde76a94831fde54c9110ecf52027604839639f92f6bc832dfc08",
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    if len(manifests) != len(roots) or not manifests:
        raise ValueError("one raw directory per access manifest required")
    if timestamp.utcoffset() is None:
        raise ValueError("aware timestamp required")
    accessed: dict[str, str] = {}
    by_url: dict[str, tuple[Path, str]] = {}
    for manifest_path, root in zip(manifests, roots, strict=True):
        payload = manifest_path.read_bytes()
        accessed[str(manifest_path)] = sha256_bytes(payload)
        for row in json.loads(payload):
            if "sha256" not in row or "data.sec.gov/" not in row["url"]:
                continue
            path = (root / row["file"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("raw path escapes its directory")
            if row["url"] in by_url and by_url[row["url"]][1] != row["sha256"]:
                raise ValueError("multiple source vintages need separate audits")
            by_url[row["url"]] = (path, row["sha256"])

    def source(url: str) -> tuple[dict[str, Any], str]:
        path, expected = by_url[url]
        payload = path.read_bytes()
        if sha256_bytes(payload) != expected:
            raise ValueError(f"source hash mismatch: {path}")
        accessed[str(path)] = expected
        return json.loads(payload), expected

    period_bytes = period_path.read_bytes()
    if sha256_bytes(period_bytes) != period_sha256:
        raise ValueError("period report hash mismatch")
    accessed[str(period_path)] = sha256_bytes(period_bytes)
    dates = tuple(date.fromisoformat(row["date"])
                  for row in json.loads(period_bytes)["monthly_coverage"])
    import exchange_calendars as xcals  # type: ignore[import-untyped]

    if not dates or dates != tuple(sorted(set(dates))):
        raise ValueError("period decisions must be nonempty, unique and increasing")
    calendar = xcals.get_calendar(
        "XNYS", start=dates[0] - timedelta(days=1), end=dates[-1] + timedelta(days=1)
    )
    closes = {day: calendar.session_close(day.isoformat()).to_pydatetime() for day in dates}
    if any(close > timestamp for close in closes.values()):
        raise ValueError("decision close is later than audit timestamp")
    issuer_rows = []
    monthly = []
    missing: Counter[str] = Counter()
    available: Counter[str] = Counter()
    for url in sorted(by_url):
        match = re.fullmatch(r"https://data\.sec\.gov/submissions/CIK(\d{10})\.json", url)
        if match is None:
            continue
        cik = match[1]
        main, main_sha = source(url)
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        if facts_url not in by_url:
            raise ValueError(f"issuer {cik} has no fact response")
        payloads = [(main, main_sha)]
        missing_shards = []
        for shard in main.get("filings", {}).get("files", []):
            shard_url = "https://data.sec.gov/submissions/" + shard["name"]
            if shard_url in by_url:
                payloads.append(source(shard_url))
            else:
                missing_shards.append(shard)
        filings = parse_submissions(cik, tuple(payloads))
        facts_payload, facts_sha = source(facts_url)
        if int(facts_payload.get("cik", -1)) != int(cik):
            raise ValueError("companyfacts issuer mismatch")
        facts = parse_company_facts(cik, facts_payload, facts_sha, filings, 24)
        issuer_rows.append({
            "cik": cik, "current_name_discovery_only": main.get("name"),
            "filings": len(filings), "facts": len(facts),
            "first_available_at": min((row.available_at for row in facts), default=None),
            "unacquired_submissions_shards": missing_shards,
            "historical_security_join_admitted": False,
        })
        for day in dates:
            cutoff = closes[day]
            ratios = fundamental_ratios(facts, cik=cik, decision_at=cutoff)
            for ratio in ratios:
                if ratio.value is None:
                    missing[ratio.name + ":" + str(ratio.reason)] += 1
                else:
                    available[ratio.name] += 1
            monthly.append({"cik": cik, "decision_at": cutoff,
                            "ratios": [asdict(row) for row in ratios]})
    if not issuer_rows:
        raise ValueError("no issuer sources found")
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True
    ).splitlines()
    tree = {name: sha256_bytes(Path(name).read_bytes())
            for name in sorted(set(paths)) if Path(name).is_file()}
    report = {
        "contract": "r3-issuer-fundamental-coverage-v1", "feature_version": VERSION,
        "run_timestamp": timestamp.isoformat(), "processing_latency_hours": 24,
        "stale_fiscal_period_days": 550,
        "decision_time": "XNYS session close including early closes",
        "decision_closes": {day.isoformat(): close for day, close in closes.items()},
        "source_hashes": accessed, "issuers": issuer_rows, "monthly": monthly,
        "available_feature_counts": dict(available), "missing_reasons": dict(missing),
        "model_fitting_permitted": False, "full_universe_coverage_verified": False,
        "qualification_permitted": False, "security_joins_admitted": 0,
        "implementation_files": tree,
        "implementation_tree_sha256": sha256_bytes(canonical_bytes(tree)),
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name)
                         for name in ("PyYAML", "exchange-calendars")},
        "randomness_used": False, "returns_inspected": False,
        "limitations": [
            "Issuer sample coverage is not full historical-universe or security-class coverage.",
            "Quarterly and YTD flow contexts are never substituted for reported annual values.",
            "Missing submission shards and unmatched acceptance records remain coverage gaps.",
            "Exchange close schedule is a retrospective calendar source, not a vintage archive.",
            "API extraction still needs representative primary-filing reconciliation.",
        ],
    }
    payload = canonical_bytes(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    return {"report_sha256": sha256_bytes(payload), "issuers": len(issuer_rows),
            "issuer_months": len(monthly), "available_feature_counts": dict(available)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access-manifest", action="append", required=True, type=Path)
    parser.add_argument("--raw-directory", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-timestamp", required=True, type=datetime.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(materialize(tuple(args.access_manifest), tuple(args.raw_directory),
                                 args.output, args.run_timestamp), sort_keys=True))


if __name__ == "__main__":
    main()
