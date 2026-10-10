"""Run the bounded R3.3 six-configuration development experiment."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from src.backtest.r3 import build_r3_market_data
from src.config.r3 import load_r3_config
from src.config.r3_development import load_r3_development_config
from src.data.calendar import load_trading_calendar
from src.data.canonical_historical import load_verified_canonical_inputs
from src.data.fx import load_fx_history
from src.data.r3_evidence import load_cash_action_evidence
from src.research.r3_development import (
    load_r3_development_dataset,
    run_r3_development,
    write_r3_development,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _provenance(root: Path) -> dict[str, object]:
    files = sorted(
        path for parent in (root / "src", root / "tests") for path in parent.rglob("*.py")
    ) + [
        root / "pyproject.toml",
        root / "config.r3.yaml",
        root / "config.r3-development.yaml",
    ]
    rows = [
        {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)} for path in files
    ]

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    dependencies: dict[str, str] = {}
    for name in ("momentum-ml-bot", "numpy", "scikit-learn", "PyYAML", "pyarrow"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "not-installed-as-distribution"
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
        "dependencies": dependencies,
        "seed": 20260926,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r3-dataset", type=Path, required=True)
    parser.add_argument("--canonical-manifest", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--fx-csv", type=Path, required=True)
    parser.add_argument("--fx-manifest", type=Path, required=True)
    parser.add_argument("--cash-action-evidence", type=Path, required=True)
    parser.add_argument("--cash-action-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config.r3.yaml"))
    parser.add_argument(
        "--development-config", type=Path, default=Path("config.r3-development.yaml")
    )
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
    allowed = ("data/local", "reports", "artifacts")
    if not any(output.is_relative_to(root / prefix) for prefix in allowed):
        raise ValueError("output must be inside an ignored local artifact directory")
    config = load_r3_config(args.config)
    development = load_r3_development_config(args.development_config)
    dataset = load_r3_development_dataset(args.r3_dataset)
    if dataset.config_sha256 != config.sha256:
        raise ValueError("R3.2 dataset configuration identity does not match config.r3.yaml")
    source_register = _json(args.r3_dataset / "experiment_register.json")
    canonical = load_verified_canonical_inputs(args.canonical_manifest)
    calendar = load_trading_calendar(args.calendar)
    fx = load_fx_history(args.fx_csv, args.fx_manifest)
    actions = load_cash_action_evidence(args.cash_action_evidence, args.cash_action_manifest)
    evaluated_dates = sorted(
        {
            decision
            for (fold, split), keys in dataset.scoring_keys.items()
            if fold in dataset.ready_folds and split in ("validation", "test")
            for _, decision in keys
        }
    )
    first_index = calendar.sessions.index(evaluated_dates[0])
    market_start = calendar.sessions[max(0, first_index - 253)]
    final_candidates = [
        session
        for session in calendar.sessions
        if session <= evaluated_dates[-1] + timedelta(days=366)
    ]
    market_end = final_candidates[-1]
    market = build_r3_market_data(
        canonical,
        calendar,
        fx,
        actions,
        start=market_start,
        end=market_end,
    )
    del canonical
    gc.collect()
    result = run_r3_development(
        dataset=dataset,
        market=market,
        config=config,
        development=development,
        source_register=source_register,
        run_timestamp=args.run_timestamp,
    )
    result.report["provenance"] = _provenance(root)
    result.report["input_sha256"] = {
        "canonical_manifest": _sha256(args.canonical_manifest),
        "calendar": _sha256(args.calendar),
        "fx_csv": _sha256(args.fx_csv),
        "fx_manifest": _sha256(args.fx_manifest),
        "cash_action_evidence": _sha256(args.cash_action_evidence),
        "cash_action_manifest": _sha256(args.cash_action_manifest),
        "r3_config": _sha256(args.config),
        "development_config": _sha256(args.development_config),
    }
    hashes = write_r3_development(result, output)
    print(
        json.dumps(
            {
                "output_directory": str(output),
                "artifact_sha256": hashes,
                "r3_3_implementation_complete": True,
                "r3_3_research_accepted": result.report["r3_3_research_accepted"],
                "qualification_permitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
