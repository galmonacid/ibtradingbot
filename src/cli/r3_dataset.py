"""Materialize the development-only R3.2 feature/label dataset from local evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from src.config.r3 import load_r3_config
from src.data.calendar import load_trading_calendar
from src.data.canonical_historical import load_verified_canonical_inputs
from src.data.fx import load_fx_history
from src.data.r3_evidence import load_cash_action_evidence
from src.research.r3_dataset import build_r3_materialization, write_r3_materialization
from src.validation.r3_register import DataAccessRecord


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _provenance(root: Path) -> dict[str, object]:
    files = sorted(
        path for parent in (root / "src", root / "tests") for path in parent.rglob("*.py")
    ) + [root / "pyproject.toml", root / "config.r3.yaml"]
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
        }
        for path in files
    ]

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    status = git("status", "--short")
    dependencies: dict[str, str] = {}
    for name in ("momentum-ml-bot", "PyYAML", "pyarrow"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "not-installed-as-distribution"
    return {
        "git_revision": git("rev-parse", "HEAD"),
        "git_committed_tree": git("rev-parse", "HEAD^{tree}"),
        "git_dirty": bool(status),
        "git_status_sha256": hashlib.sha256(status.encode()).hexdigest(),
        "implementation_tree_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "python": platform.python_version(),
        "dependencies": dependencies,
        "random_seed": 20260926,
    }


def _access_records(
    *,
    canonical_manifest: Path,
    dataset_evidence: Path,
    universe_policy: Path,
    calendar: Path,
    fx_csv: Path,
    fx_manifest: Path,
    fx_source_archive: Path,
    cash_action_evidence: Path,
    cash_action_manifest: Path,
    independent_calendar: Path,
    independent_calendar_manifest: Path,
    curated_delisting_evidence: Path,
    spdr_distributions_evidence: Path,
    accessed_at: datetime,
) -> tuple[DataAccessRecord, ...]:
    manifest = _json_object(canonical_manifest)
    root = canonical_manifest.parent
    records = [
        DataAccessRecord(
            "canonical_manifest",
            _sha256(canonical_manifest),
            "1996-01-02",
            "2026-09-15",
            accessed_at,
            "R3.2 source binding and provenance",
            True,
        )
    ]
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("canonical manifest files must be a list")
    for row in files:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("canonical manifest file entry is invalid")
        path = root / str(row["path"])
        records.append(
            DataAccessRecord(
                f"canonical/{row['path']}",
                _sha256(path),
                str(row.get("minimum_date") or "unknown"),
                str(row.get("maximum_date") or "unknown"),
                accessed_at,
                "R3.2 feature, label, identity, membership or action materialization",
                True,
            )
        )
    records.extend(
        (
            DataAccessRecord(
                "dataset_evidence",
                _sha256(dataset_evidence),
                "1996-01-02",
                "2026-09-15",
                accessed_at,
                "R3.2 producer-evidence audit",
                True,
            ),
            DataAccessRecord(
                "universe_policy",
                _sha256(universe_policy),
                "2010-05-27",
                "2026-09-15",
                accessed_at,
                "R3.2 universe coverage audit",
                True,
            ),
            DataAccessRecord(
                "xnys_calendar",
                _sha256(calendar),
                "1996-01-02",
                "2026-09-15",
                accessed_at,
                "R3.2 decision, label and purge scheduling",
                True,
            ),
            DataAccessRecord(
                "gbp_usd_fx_csv",
                _sha256(fx_csv),
                str(_json_object(fx_manifest).get("start", "unknown")),
                str(_json_object(fx_manifest).get("end", "unknown")),
                accessed_at,
                "R3.2 causal GBP label conversion",
                False,
            ),
            DataAccessRecord(
                "gbp_usd_fx_manifest",
                _sha256(fx_manifest),
                str(_json_object(fx_manifest).get("start", "unknown")),
                str(_json_object(fx_manifest).get("end", "unknown")),
                accessed_at,
                "R3.2 FX provenance and vintage audit",
                False,
            ),
            DataAccessRecord(
                "ecb_fx_source_archive",
                _sha256(fx_source_archive),
                str(_json_object(fx_manifest).get("start", "unknown")),
                str(_json_object(fx_manifest).get("end", "unknown")),
                accessed_at,
                "R3.2 full-history GBP/USD reconstruction source",
                False,
            ),
            DataAccessRecord(
                "cash_action_evidence",
                _sha256(cash_action_evidence),
                str(_json_object(cash_action_manifest).get("period_start", "unknown")),
                str(_json_object(cash_action_manifest).get("period_end", "unknown")),
                accessed_at,
                "R3.2 dividend payment-date and withholding label evidence",
                False,
            ),
            DataAccessRecord(
                "cash_action_evidence_manifest",
                _sha256(cash_action_manifest),
                str(_json_object(cash_action_manifest).get("period_start", "unknown")),
                str(_json_object(cash_action_manifest).get("period_end", "unknown")),
                accessed_at,
                "R3.2 cash-action provenance, access terms and coverage audit",
                False,
            ),
            DataAccessRecord(
                "independent_xnys_calendar",
                _sha256(independent_calendar),
                str(_json_object(independent_calendar_manifest).get("start", "unknown")),
                str(_json_object(independent_calendar_manifest).get("end", "unknown")),
                accessed_at,
                "R3.2 independent exchange-session comparison",
                False,
            ),
            DataAccessRecord(
                "independent_xnys_calendar_manifest",
                _sha256(independent_calendar_manifest),
                str(_json_object(independent_calendar_manifest).get("start", "unknown")),
                str(_json_object(independent_calendar_manifest).get("end", "unknown")),
                accessed_at,
                "R3.2 independent-calendar provenance and licence audit",
                False,
            ),
            DataAccessRecord(
                "curated_delisting_evidence",
                _sha256(curated_delisting_evidence),
                "2021-01-07",
                "2023-12-14",
                accessed_at,
                "R3.2 explicit cash-recovery amount and completion/payment timing",
                False,
            ),
            DataAccessRecord(
                "state_street_spdr_distributions",
                _sha256(spdr_distributions_evidence),
                "1996-01-02",
                "2026-09-15",
                accessed_at,
                "R3.2 SPY dividend payment-date and amount evidence",
                False,
            ),
        )
    )
    return tuple(records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-manifest", type=Path, required=True)
    parser.add_argument("--dataset-evidence", type=Path, required=True)
    parser.add_argument("--universe-policy", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--fx-csv", type=Path, required=True)
    parser.add_argument("--fx-manifest", type=Path, required=True)
    parser.add_argument("--fx-source-archive", type=Path, required=True)
    parser.add_argument("--cash-action-evidence", type=Path, required=True)
    parser.add_argument("--cash-action-manifest", type=Path, required=True)
    parser.add_argument("--independent-calendar", type=Path, required=True)
    parser.add_argument("--independent-calendar-manifest", type=Path, required=True)
    parser.add_argument("--curated-delisting-evidence", type=Path, required=True)
    parser.add_argument("--spdr-distributions-evidence", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config.r3.yaml"))
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-timestamp", type=datetime.fromisoformat, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.run_timestamp.tzinfo is None:
        raise ValueError("run timestamp must be timezone-aware")
    root = args.repository_root.resolve()
    output = args.output_directory.resolve()
    if not any(
        output.is_relative_to(root / prefix) for prefix in ("data/local", "reports", "artifacts")
    ):
        raise ValueError("output must be inside ignored data/local, reports or artifacts")
    canonical = load_verified_canonical_inputs(args.canonical_manifest)
    calendar = load_trading_calendar(args.calendar)
    fx = load_fx_history(args.fx_csv, args.fx_manifest)
    fx_manifest = _json_object(args.fx_manifest)
    if fx_manifest.get("source_archive_sha256") != _sha256(args.fx_source_archive):
        raise ValueError("ECB source archive does not match the reconstructed FX manifest")
    cash_action_evidence = load_cash_action_evidence(
        args.cash_action_evidence, args.cash_action_manifest
    )
    cash_action_manifest = _json_object(args.cash_action_manifest)
    if cash_action_manifest.get("curated_delistings_sha256") != _sha256(
        args.curated_delisting_evidence
    ):
        raise ValueError("curated delisting evidence does not match its cash-action manifest")
    if cash_action_manifest.get("spdr_distributions_sha256") != _sha256(
        args.spdr_distributions_evidence
    ):
        raise ValueError("SPDR distribution evidence does not match its cash-action manifest")
    independent_calendar = load_trading_calendar(args.independent_calendar)
    independent_calendar_manifest = _json_object(args.independent_calendar_manifest)
    dataset_evidence = _json_object(args.dataset_evidence)
    universe_policy = _json_object(args.universe_policy)
    config = load_r3_config(args.config)
    records = _access_records(
        canonical_manifest=args.canonical_manifest,
        dataset_evidence=args.dataset_evidence,
        universe_policy=args.universe_policy,
        calendar=args.calendar,
        fx_csv=args.fx_csv,
        fx_manifest=args.fx_manifest,
        fx_source_archive=args.fx_source_archive,
        cash_action_evidence=args.cash_action_evidence,
        cash_action_manifest=args.cash_action_manifest,
        independent_calendar=args.independent_calendar,
        independent_calendar_manifest=args.independent_calendar_manifest,
        curated_delisting_evidence=args.curated_delisting_evidence,
        spdr_distributions_evidence=args.spdr_distributions_evidence,
        accessed_at=args.run_timestamp,
    )
    result = build_r3_materialization(
        canonical=canonical,
        calendar=calendar,
        fx=fx,
        fx_manifest=fx_manifest,
        cash_action_evidence=cash_action_evidence,
        cash_action_manifest=cash_action_manifest,
        independent_calendar=independent_calendar,
        independent_calendar_manifest=independent_calendar_manifest,
        dataset_evidence=dataset_evidence,
        universe_policy=universe_policy,
        config=config,
        access_records=records,
        run_timestamp=args.run_timestamp,
    )
    report = dict(result.report)
    report["provenance"] = _provenance(root)
    result = replace(result, report=report)
    hashes = write_r3_materialization(result, output)
    summary = {
        "output_directory": str(output),
        "artifact_sha256": hashes,
        "counts": result.report["counts"],
        "development_training_blockers": result.report["development_training_blockers"],
        "r3_3_development_training_permitted": result.report["r3_3_development_training_permitted"],
        "qualification_permitted": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
