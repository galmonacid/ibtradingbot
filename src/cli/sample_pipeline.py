"""Run the validation-only Phase 0 sample pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config.settings import ConfigurationError, load_config
from src.data.quality import DataQualityError, validate_daily_bars
from src.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the checked-in Phase 0 sample dataset."
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to the YAML configuration."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/sample/daily_bars.csv"),
        help="Path to daily-bar CSV.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logger = configure_logging()
    try:
        config = load_config(args.config)
        summary = validate_daily_bars(args.data)
    except (ConfigurationError, DataQualityError) as error:
        logger.error("sample_pipeline_failed", extra={"reason": str(error)})
        return 1
    output = {
        "config_sha256": config.sha256,
        "data": {
            "first_date": summary.first_date,
            "last_date": summary.last_date,
            "rows": summary.row_count,
            "symbols": summary.symbols,
        },
        "status": "validated",
    }
    logger.info(
        "sample_pipeline_validated",
        extra={"rows": summary.row_count, "symbols": len(summary.symbols)},
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
