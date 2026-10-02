"""Build the offline R3.1 account-economics and exposure-attribution report."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.config.r3_feasibility import load_r3_feasibility_config
from src.data.calendar import load_trading_calendar
from src.data.canonical_historical import load_verified_canonical_inputs
from src.research.r3_feasibility import (
    build_r3_feasibility_report,
    write_r3_feasibility_report,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(root: Path) -> dict[str, object]:
    files = sorted(
        path
        for parent in (root / "src", root / "tests")
        for path in parent.rglob("*.py")
    ) + [root / "pyproject.toml", root / "config.r3-feasibility.yaml"]
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
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
    return {
        "git_revision": git("rev-parse", "HEAD"),
        "git_committed_tree": git("rev-parse", "HEAD^{tree}"),
        "git_dirty": bool(status),
        "git_status_sha256": hashlib.sha256(status.encode()).hexdigest(),
        "implementation_tree_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "python": platform.python_version(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("momentum-ml-bot", "PyYAML", "pyarrow")
        },
        "random_seed": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--legacy-report", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--canonical-manifest", type=Path)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-timestamp", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        if (args.canonical_manifest is None) != (args.calendar is None):
            raise ValueError("canonical-manifest and calendar must be supplied together")
        root = args.repository_root.resolve()
        output = args.output_directory.resolve()
        if not any(
            output.is_relative_to(root / prefix)
            for prefix in ("data/local", "reports", "artifacts")
        ):
            raise ValueError("output must be inside ignored data/local, reports or artifacts")
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        if not isinstance(ledger, dict):
            raise ValueError("ledger must contain a JSON object")
        legacy_report = json.loads(args.legacy_report.read_text(encoding="utf-8"))
        if not isinstance(legacy_report, dict):
            raise ValueError("legacy report must contain a JSON object")
        canonical = (
            load_verified_canonical_inputs(args.canonical_manifest)
            if args.canonical_manifest is not None
            else None
        )
        calendar = load_trading_calendar(args.calendar) if args.calendar is not None else None
        report = build_r3_feasibility_report(
            ledger,
            load_r3_feasibility_config(args.config),
            run_timestamp=args.run_timestamp,
            ledger_sha256=_sha256(args.ledger),
            config_file_sha256=_sha256(args.config),
            canonical=canonical,
            calendar=calendar,
            provenance=_provenance(root),
            legacy_report=legacy_report,
            legacy_report_sha256=_sha256(args.legacy_report),
        )
        write_r3_feasibility_report(report, output)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        importlib.metadata.PackageNotFoundError,
    ) as error:
        print(f"R3.1 feasibility failed: {error}", file=sys.stderr)
        return 1
    status = "passed" if report["research_acceptance_passed"] else "blocked"
    print(f"R3.1 report: {output / 'r3_1_feasibility.md'}; research acceptance {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
