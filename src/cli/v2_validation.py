"""Run fixed V2 development scenarios on certified native historical inputs."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from src.config.v2 import load_v2_config
from src.data.calendar import load_trading_calendar
from src.data.fx import load_fx_history
from src.validation.native_inputs import create_native_validation_inputs
from src.validation.v2_workflow import run_v2_development, write_v2_development


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "canonical-manifest",
        "config",
        "v2-config",
        "validation-spec",
        "strategy-spec",
        "dataset-evidence",
        "universe-policy",
        "calendar",
        "fx-csv",
        "fx-manifest",
        "output-directory",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--v1-anchor", type=Path)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--run-timestamp", type=datetime.fromisoformat, required=True)
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="explicit incomplete diagnostic: omit stresses and sensitivities",
    )
    args = parser.parse_args()
    try:
        root = args.repository_root.resolve()
        output = args.output_directory.resolve()
        if not any(
            output.is_relative_to(root / prefix)
            for prefix in ("data/local", "reports", "artifacts")
        ):
            raise ValueError(
                "output directory must be inside ignored data/local, reports or artifacts"
            )
        inputs = create_native_validation_inputs(
            canonical_manifest_path=args.canonical_manifest,
            config_path=args.config,
            validation_spec_path=args.validation_spec,
            repository_root=root,
            strategy_version="monthly-momentum-v2",
            dataset_evidence_path=args.dataset_evidence,
            universe_policy_path=args.universe_policy,
        )
        report, ledgers = run_v2_development(
            inputs,
            load_trading_calendar(args.calendar),
            load_fx_history(args.fx_csv, args.fx_manifest),
            load_v2_config(args.v2_config),
            start=args.start,
            end=args.end,
            run_timestamp=args.run_timestamp,
            strategy_spec_path=args.strategy_spec,
            baseline_only=args.baseline_only,
            v1_anchor_path=args.v1_anchor,
        )
        write_v2_development(report, ledgers, output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"V2 development failed: {error}", file=sys.stderr)
        return 1
    print(f"Development report: {output / 'research_report.md'}; paper trading blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
