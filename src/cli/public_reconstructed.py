"""Create reproducible public-reconstructed PIT membership inputs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.data.public_reconstructed import PublicReconstructedError, export_pitindex_sp500


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a non-admissible public S&P 500 PIT reconstruction from pitindex."
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--start", type=_date, default=date(2007, 1, 1))
    parser.add_argument("--end", type=_date, required=True)
    args = parser.parse_args()
    try:
        result = export_pitindex_sp500(args.output_directory, start=args.start, end=args.end)
    except (OSError, PublicReconstructedError, ValueError) as error:
        print(f"public reconstruction failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "source_version": result.source_version,
                "membership": str(result.membership_path),
                "security_master": str(result.security_master_path),
                "manifest": str(result.manifest_path),
                "deployment_admissible": False,
                "paper_execution_permitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
