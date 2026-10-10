"""Materialize the immutable R3 Step 3 source-feasibility package."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Any

from src.config.r3_step3 import load_r3_step3_config
from src.research.r3_source_feasibility import (
    audit_payloads,
    canonical_bytes,
    feature_contract,
    seeded_sample_order,
    sha256_bytes,
    write_new,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(("git", *args), text=True).strip()


def _fetch(url: str, user_agent: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return bytes(response.read())


def _source_urls(config: Any, existing: dict[str, bytes]) -> list[str]:
    urls = [
        "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "https://www.sec.gov/about/developer-resources",
        "https://www.sec.gov/about/privacy-information",
        "https://fred.stlouisfed.org/docs/api/fred/alfred.html",
        "https://fred.stlouisfed.org/docs/api/api_key.html",
    ]
    for sample in config.sample:
        main = f"https://data.sec.gov/submissions/CIK{sample.cik}.json"
        urls.extend((main, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{sample.cik}.json"))
        payload = existing.get(main)
        if payload is not None:
            parsed = json.loads(payload)
            urls.extend(
                f"https://data.sec.gov/submissions/{row['name']}"
                for row in parsed.get("filings", {}).get("files", [])
            )
            if sample.cik in {"0000320193", "0001652044", "0000040545"}:
                recent = parsed.get("filings", {}).get("recent", {})
                for index, form in enumerate(recent.get("form", [])):
                    if form not in {"10-Q", "10-K"}:
                        continue
                    accession = str(recent["accessionNumber"][index]).replace("-", "")
                    document = str(recent["primaryDocument"][index])
                    urls.append(
                        "https://www.sec.gov/Archives/edgar/data/"
                        f"{int(sample.cik)}/{accession}/{document}"
                    )
                    break
    return list(dict.fromkeys(urls))


def fetch_sources(config_path: Path, raw_directory: Path, retrieved_at: str) -> None:
    config = load_r3_step3_config(config_path)
    if raw_directory.exists():
        raise FileExistsError(f"raw source directory already exists: {raw_directory}")
    raw_directory.mkdir(parents=True)
    existing: dict[str, bytes] = {}
    manifest: list[dict[str, object]] = []
    queue = _source_urls(config, existing)
    index = 0
    while index < len(queue):
        url = queue[index]
        index += 1
        if len(manifest) >= config.source_request_limit:
            raise ValueError("bounded SEC request limit exceeded")
        body = _fetch(url, config.sec_user_agent)
        existing[url] = body
        suffix = ".json" if url.endswith(".json") else ".html"
        name = f"response_{len(manifest):03d}{suffix}"
        (raw_directory / name).write_bytes(body)
        manifest.append(
            {
                "url": url,
                "retrieved_at": retrieved_at,
                "sha256": sha256_bytes(body),
                "bytes": len(body),
                "file": name,
                "read_only_public": True,
            }
        )
        if "/submissions/CIK" in url:
            queue = _source_urls(config, existing)
    write_new(raw_directory / "source_access_manifest.json", manifest)


def materialize(config_path: Path, raw_directory: Path, output: Path) -> dict[str, str]:
    config = load_r3_step3_config(config_path)
    if output.exists():
        raise FileExistsError(f"immutable package path already exists: {output}")
    output.mkdir(parents=True)
    manifest_path = raw_directory / "source_access_manifest.json"
    accesses: list[dict[str, object]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    for access in accesses:
        source_path = raw_directory / str(access["file"])
        if not source_path.is_file() or _sha(source_path) != access["sha256"]:
            raise ValueError(f"source response hash mismatch: {source_path}")
    audit = audit_payloads(config, raw_directory, accesses)
    try:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as error:  # pragma: no cover - dependency guard
        raise RuntimeError("historical-data dependencies are required") from error
    security_rows = pq.read_table(
        "data/local/phase3_build_v3/canonical/security_master.parquet"
    ).to_pylist()
    for row in audit["joins"]:
        ids = set(row["security_ids"])
        intervals = [
            {
                "security_id": value["security_id"],
                "symbol": value["symbol"],
                "effective_from": value["effective_from"],
                "effective_to": value["effective_to"],
            }
            for value in security_rows
            if value["security_id"] in ids
        ]
        row["local_symbol_intervals"] = intervals
        row["ticker_change_preserved_within_identity"] = any(
            len({value["symbol"] for value in intervals if value["security_id"] == identity}) > 1
            for identity in ids
        )
    by_url = {str(row["url"]): row for row in accesses}
    representative: list[dict[str, object]] = []
    for sample in config.sample:
        if sample.cik not in {"0000320193", "0001652044", "0000040545"}:
            continue
        main_url = f"https://data.sec.gov/submissions/CIK{sample.cik}.json"
        main = json.loads(
            (raw_directory / str(by_url[main_url]["file"])).read_text(encoding="utf-8")
        )
        recent = main["filings"]["recent"]
        for index, form in enumerate(recent["form"]):
            if form not in {"10-Q", "10-K"}:
                continue
            accession = str(recent["accessionNumber"][index])
            document = str(recent["primaryDocument"][index])
            url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(sample.cik)}/{accession.replace('-', '')}/{document}"
            )
            source = by_url[url]
            body = (raw_directory / str(source["file"])).read_text(
                encoding="utf-8", errors="replace"
            )
            representative.append(
                {
                    "cik": sample.cik,
                    "issuer": sample.issuer,
                    "accession": accession,
                    "form": form,
                    "accepted_at": recent["acceptanceDateTime"][index],
                    "primary_document": document,
                    "url": url,
                    "source_sha256": source["sha256"],
                    "issuer_name_present": sample.issuer.split()[0].lower() in body.lower(),
                    "xbrl_fact_markup_present": "ix:nonfraction" in body.lower(),
                    "reconciliation": "primary filing identity and inline-XBRL structure manually sampled",
                }
            )
            break
    preserved = {
        "dataset": config.corrected_dataset_identity,
        "scoring": _sha(Path("data/local/r3_2_20261002_corrected_v2/scoring.parquet")),
        "report": _sha(Path("data/local/r3_3_20261002_corrected_v2/development_report.json")),
    }
    if preserved != {
        "dataset": config.corrected_dataset_identity,
        "scoring": config.corrected_scoring_sha256,
        "report": config.corrected_report_sha256,
    }:
        raise ValueError("preserved corrected evidence hash mismatch")
    artifacts: dict[str, object] = {
        "source_access_manifest.json": accesses,
        "sample_manifest.json": {
            "contract": config.contract_version,
            "seed": config.sample_seed,
            "selection_basis": "predeclared structural complications only; no returns or scores",
            "seeded_processing_order": list(seeded_sample_order(config)),
            "sample": [
                {
                    "cik": row.cik,
                    "issuer": row.issuer,
                    "cases": list(row.cases),
                    "security_ids": list(row.security_ids),
                }
                for row in config.sample
            ],
        },
        "issuer_security_join_audit.json": audit["joins"],
        "filing_fact_audit.json": {
            "issuers": audit["issuers"],
            "fact_summary": audit["fact_summary"],
            "transform": "r3-step3-sec-facts-v1",
            "amendment_rule": "each /A accession becomes new information at its own acceptance plus latency",
            "restatement_rule": "later filings never replace earlier knowledge retroactively",
            "period_rule": "duration classifies quarterly, YTD, annual and instant facts",
            "representative_primary_reconciliation": representative,
        },
        "coverage.json": {
            "protocol": audit["protocol"],
            "sample_only": True,
            "annual_sample_coverage": audit["annual_coverage"],
            "complete_case_universe": 0,
            "partial_case_issuers": sum(int(row["facts"]) > 0 for row in audit["issuers"]),
            "expected_security_loss": "not estimated from a bounded sample",
            "expected_decision_date_loss": "all dates before first causal SEC fact; full-universe rate not estimated",
            "stale_limit_days": 550,
        },
        "missing_conflicts.json": {
            "duplicate_conflicts": audit["conflicts"],
            "causal_sector": "unavailable: no dated classification source with mapped historical identities",
            "macro": "infeasible in this run: official ALFRED API requires an API key; no credential was supplied or created",
            "identity": "sample shows duplicate/multiple security IDs without a dated issuer-security mapping authority",
        },
        "feature_contract.json": feature_contract(),
        "source_permissions.json": {
            "sec": {
                "authentication": "none required",
                "rate_limit": "no more than 10 requests/second; this audit used sequential bounded requests",
                "api_update": "submissions real-time; XBRL typically under one minute",
                "permission_status": "public read-only access compatible with bounded local research",
                "redistribution": "raw responses retained locally and ignored; dataset redistribution not authorized by this audit",
            },
            "alfred": {
                "permission_status": "documentation public; observation API access requires a key",
                "retrieval_status": "not attempted because no credential was supplied",
            },
            "sector": {"permission_status": "no candidate source audited; infeasible"},
        },
        "cost_budget.json": {
            "initial_capital_gbp": 3000,
            "items": [
                {"item": "SEC EDGAR APIs", "annual_gbp": 0, "status": "observed_public_access_no_charge", "from_account": False},
                {"item": "ALFRED API", "annual_gbp": None, "status": "unknown_not_accessed", "from_account": None},
                {"item": "causal sector metadata", "annual_gbp": None, "status": "unknown_no_source", "from_account": None},
                {"item": "storage", "annual_gbp": 0, "status": "assumed_existing_local_resources", "from_account": False},
                {"item": "compute", "annual_gbp": 0, "status": "assumed_existing_local_cpu", "from_account": False},
                {"item": "hosting", "annual_gbp": 0, "status": "assumed_no_hosting", "from_account": False},
            ],
            "known_annual_from_account_gbp": 0,
            "known_percent_starting_capital": 0,
            "full_recurring_cost_known": False,
            "refresh_workload": "11 issuer submissions + companyfacts resources; sequential and below SEC limits",
            "continuity_risks": ["API schema/policy changes", "issuer mapping maintenance", "unknown sector and ALFRED access continuity"],
            "economic_decision": "stop: unknown required-source costs and zero support for the frozen protocol",
        },
        "protocol_feasibility.json": audit["protocol"],
        "failure_register.json": {
            "register_version": "r3-step3-failure-register-v1",
            "decision": "stop_before_step4_registration",
            "step4_authorized": False,
            "experiment_register_created": False,
            "blockers": [
                "zero_of_nine_full_8_2_1_folds_support_SEC_features_without_backfill",
                "issuer_security_identity_mapping_materially_ambiguous",
                "causal_sector_metadata_unavailable",
                "ALFRED_vintage_observations_not_accessible_without_unsupplied_API_key",
                "required_source_costs_materially_unknown",
            ],
            "prohibitions": ["model_fit", "score_generation", "portfolio_simulation", "candidate_selection", "protocol_shortening"],
            "preserved_evidence": preserved,
        },
        "environment.json": {
            "run_timestamp": config.run_timestamp,
            "git_revision": _git("rev-parse", "HEAD"),
            "git_committed_tree": _git("rev-parse", "HEAD^{tree}"),
            "git_dirty": bool(_git("status", "--porcelain=v1")),
            "git_status_sha256": sha256_bytes((_git("status", "--porcelain=v1") + "\n").encode()),
            "implementation_tree_sha256": sha256_bytes(
                canonical_bytes(
                    {
                        str(path): _sha(path)
                        for path in sorted(Path("src").rglob("*.py"))
                    }
                )
            ),
            "config_sha256": _sha(config_path),
            "typed_config_sha256": config.sha256,
            "source_manifest_sha256": _sha(manifest_path),
            "source_identity": sha256_bytes(canonical_bytes(accesses)),
            "universe_identity": _sha(Path("data/local/phase3_build_v3/canonical/security_master.parquet")),
            "python": platform.python_version(),
            "dependencies": {
                name: metadata.version(name)
                for name in ("PyYAML", "pyarrow", "numpy", "scikit-learn")
            },
            "xgboost": "not_installed_and_not_required_for_step3",
            "seeds": [config.sample_seed, 20260926],
        },
    }
    hashes: dict[str, str] = {}
    for name, value in artifacts.items():
        hashes[name] = write_new(output / name, value)
    package_identity = sha256_bytes(canonical_bytes(hashes))
    hash_manifest = {"package_identity": package_identity, "artifacts": hashes}
    hashes["artifact_hash_manifest.json"] = write_new(
        output / "artifact_hash_manifest.json", hash_manifest
    )
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--config", type=Path, required=True)
    fetch.add_argument("--raw-directory", type=Path, required=True)
    fetch.add_argument("--retrieved-at", required=True)
    build = sub.add_parser("materialize")
    build.add_argument("--config", type=Path, required=True)
    build.add_argument("--raw-directory", type=Path, required=True)
    build.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "fetch":
        fetch_sources(args.config, args.raw_directory, args.retrieved_at)
    else:
        hashes = materialize(args.config, args.raw_directory, args.output_directory)
        print(json.dumps(hashes, sort_keys=True))


if __name__ == "__main__":
    main()
