"""Acquire clearly non-admissible public daily-price research inputs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.data.public_prices import PublicPriceError, acquire_yahoo_daily_prices


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Acquire public Yahoo daily bars with an explicit incomplete-coverage manifest."
    )
    parser.add_argument("--membership", type=Path, required=True)
    parser.add_argument("--membership-manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--start", type=_date, required=True)
    parser.add_argument("--end", type=_date, required=True)
    parser.add_argument("--benchmark", default="SPY")
    args = parser.parse_args()
    try:
        result = acquire_yahoo_daily_prices(
            args.membership,
            args.membership_manifest,
            args.output_directory,
            start=args.start,
            end=args.end,
            benchmark=args.benchmark,
        )
    except (OSError, PublicPriceError, ValueError) as error:
        print(f"public price acquisition failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "bars": str(result.bars_path),
                "manifest": str(result.manifest_path),
                "fetched_symbols": result.fetched_symbols,
                "failed_symbols": result.failed_symbols,
                "deployment_admissible": False,
                "paper_execution_permitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
