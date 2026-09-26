"""Build a trusted canonical Phase 3 dataset from immutable local source snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from src.data.fmp_transform import transform_fmp_manifest
from src.data.git_source import verify_git_source_snapshot
from src.data.membership_audit import derive_constituent_changes
from src.data.semantic_certification import CoverageExclusion, TerminalTreatment
from src.data.source_adapters import (
    transform_identity_source,
    transform_membership_source,
    transform_riazarbi_audit_source,
)
from src.data.source_native_qa import ISHARES_IVV_ROLE, WIKIPEDIA_ROLE
from src.data.tiingo_transform import transform_tiingo_source
from src.data.trusted_historical import DatedSecurityIdentity
from src.data.trusted_producer import build_trusted_historical_dataset


class HistoricalBuildInputError(ValueError):
    """Raised when an offline producer input file is not canonical."""


def _json_list(path: Path, name: str) -> list[dict[str, Any]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoricalBuildInputError(f"{name} must be readable JSON") from error
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise HistoricalBuildInputError(f"{name} must be a JSON list of objects")
    return payload


def _sessions(path: Path) -> tuple[date, ...]:
    try:
        rows = tuple(
            date.fromisoformat(line.strip())
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except (OSError, ValueError) as error:
        raise HistoricalBuildInputError("sessions must contain one ISO date per line") from error
    if not rows or tuple(sorted(set(rows))) != rows:
        raise HistoricalBuildInputError("sessions must be non-empty, sorted, and unique")
    return rows


def _exclusions(path: Path | None) -> tuple[CoverageExclusion, ...]:
    if path is None:
        return ()
    rows = _json_list(path, "exclusions")
    if any(set(row) != {"security_id", "session", "reason"} for row in rows):
        raise HistoricalBuildInputError("exclusions contain invalid fields")
    try:
        return tuple(
            CoverageExclusion(
                str(row["security_id"]), date.fromisoformat(str(row["session"])), str(row["reason"])
            )
            for row in rows
        )
    except (KeyError, ValueError) as error:
        raise HistoricalBuildInputError("exclusions contain invalid records") from error


def _terminal(path: Path | None) -> tuple[TerminalTreatment, ...]:
    if path is None:
        return ()
    rows = _json_list(path, "terminal treatments")
    fields = {
        "security_id",
        "last_tradable_session",
        "disposition",
        "economic_value",
        "source",
    }
    if any(set(row) != fields for row in rows):
        raise HistoricalBuildInputError("terminal treatments contain invalid fields")
    try:
        return tuple(
            TerminalTreatment(
                str(row["security_id"]),
                date.fromisoformat(str(row["last_tradable_session"])),
                str(row["disposition"]),
                float(row["economic_value"]),
                str(row["source"]),
            )
            for row in rows
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HistoricalBuildInputError("terminal treatments contain invalid records") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build canonical Phase 3 Parquet and dataset evidence from local snapshots."
    )
    for role in ("membership", "identity", "scraper-qa", "holdings-qa"):
        parser.add_argument(f"--{role}-manifest", type=Path, required=True)
        parser.add_argument(f"--{role}-root", type=Path, required=True)
        parser.add_argument(f"--{role}-file", required=True)
    parser.add_argument(
        "--scraper-qa-kind", choices=("riazarbi-wikipedia",), default="riazarbi-wikipedia"
    )
    parser.add_argument("--holdings-qa-kind", choices=("riazarbi-ivv",), default="riazarbi-ivv")
    parser.add_argument("--tiingo-manifest", type=Path, required=True)
    parser.add_argument("--tiingo-root", type=Path, required=True)
    parser.add_argument("--tiingo-request-plan", type=Path, required=True)
    parser.add_argument("--fmp-manifest", type=Path)
    parser.add_argument("--fmp-root", type=Path)
    parser.add_argument(
        "--sessions",
        type=Path,
        help="Optional expected session list; otherwise derived from verified benchmark bars.",
    )
    parser.add_argument("--exclusions", type=Path)
    parser.add_argument("--terminal-treatments", type=Path)
    parser.add_argument("--coverage-start", type=date.fromisoformat, required=True)
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--audit-sample-size", type=int, default=75)
    parser.add_argument("--audit-seed", type=int, default=20260913)
    parser.add_argument("--minimum-investable-constituents", type=int, default=400)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        membership_snapshot = verify_git_source_snapshot(
            args.membership_manifest, args.membership_root
        )
        membership = transform_membership_source(
            membership_snapshot, args.membership_root, args.membership_file
        )
        known_symbols = tuple(
            sorted(
                {symbol for snapshot in membership.memberships for symbol in snapshot.symbols}
                | {args.benchmark_symbol}
            )
        )
        identity_snapshot = verify_git_source_snapshot(args.identity_manifest, args.identity_root)
        identity = transform_identity_source(
            identity_snapshot,
            args.identity_root,
            args.identity_file,
            coverage_start=args.coverage_start,
            known_symbols=known_symbols,
            preserve_symbol_reuse=True,
        )
        scraper_snapshot = verify_git_source_snapshot(
            args.scraper_qa_manifest, args.scraper_qa_root
        )
        scraper = transform_riazarbi_audit_source(
            scraper_snapshot,
            args.scraper_qa_root,
            args.scraper_qa_file,
            source_role=WIKIPEDIA_ROLE,
        )
        holdings_snapshot = verify_git_source_snapshot(
            args.holdings_qa_manifest, args.holdings_qa_root
        )
        holdings = transform_riazarbi_audit_source(
            holdings_snapshot,
            args.holdings_qa_root,
            args.holdings_qa_file,
            source_role=ISHARES_IVV_ROLE,
        )
        qa_sources = (scraper, holdings)
        tiingo = transform_tiingo_source(
            args.tiingo_manifest, args.tiingo_root, args.tiingo_request_plan
        )
        if (args.fmp_manifest is None) != (args.fmp_root is None):
            raise HistoricalBuildInputError(
                "optional FMP manifest and root must be supplied together"
            )
        fmp = (
            transform_fmp_manifest(
                args.fmp_manifest, args.fmp_root, identities=identity.parsed.identity_intervals
            )
            if args.fmp_manifest is not None and args.fmp_root is not None
            else None
        )
        identities = DatedSecurityIdentity(identity.parsed.identity_intervals)
        benchmark_id = identities.resolve(args.benchmark_symbol, args.coverage_start)
        benchmark_sessions = tuple(
            sorted({row.date for row in tiingo.bars if row.security_id == benchmark_id})
        )
        if not benchmark_sessions:
            raise HistoricalBuildInputError("verified Tiingo input has no benchmark sessions")
        sessions = _sessions(args.sessions) if args.sessions is not None else benchmark_sessions
        if sessions != benchmark_sessions:
            raise HistoricalBuildInputError(
                "supplied sessions do not exactly match verified Tiingo benchmark bars"
            )
        changes = derive_constituent_changes(
            membership.memberships, identities
        )
        result = build_trusted_historical_dataset(
            args.output_directory,
            membership_source=membership,
            identity_source=identity,
            qa_evidence_sources=qa_sources,
            tiingo_source=tiingo,
            fmp_source=fmp,
            sessions=sessions,
            benchmark_security_id=benchmark_id,
            primary_changes=changes,
            audit_sample_size=args.audit_sample_size,
            audit_seed=args.audit_seed,
            exclusions=_exclusions(args.exclusions),
            terminal_treatments=_terminal(args.terminal_treatments),
            fmp_quarantines=(),
            minimum_investable_constituents=args.minimum_investable_constituents,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"historical build failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "canonical_manifest": str(result.canonical.manifest_path),
                "dataset_evidence": str(result.dataset_evidence_manifest_path),
                "universe_policy": str(result.universe_policy_path),
                "deployment_admissible": False,
                "paper_execution_permitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
