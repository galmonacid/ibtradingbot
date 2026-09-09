"""Command-line entry point for the local Phase 1 research baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.config.settings import ConfigurationError
from src.logging import configure_logging
from src.research import ResearchError, run_research


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the synthetic, engineering-only Phase 1 research baseline."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument(
        "--run-timestamp",
        type=datetime.fromisoformat,
        help="Optional timezone-aware ISO timestamp for deterministic regression output.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logger = configure_logging()
    try:
        report = run_research(
            args.config,
            args.data,
            args.universe,
            args.calendar,
            args.corporate_actions,
            initial_cash=args.initial_cash,
            run_timestamp=args.run_timestamp,
        )
    except (ConfigurationError, ResearchError, ValueError) as error:
        logger.error("research_pipeline_failed", extra={"reason": str(error)})
        return 1
    logger.info(
        "research_pipeline_completed",
        extra={"trades": len(report["trades"]), "sessions": report["input"]["sessions"]},
    )
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
