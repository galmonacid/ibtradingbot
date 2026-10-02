"""Build deterministic local evidence inputs for the R3.2 materializer."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from src.data.r3_evidence import (
    acquire_nasdaq_dividend_evidence,
    build_independent_xnys_calendar,
    rebuild_ecb_gbp_usd,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    fx = subparsers.add_parser("ecb-fx")
    fx.add_argument("--archive", type=Path, required=True)
    fx.add_argument("--output-csv", type=Path, required=True)
    fx.add_argument("--output-manifest", type=Path, required=True)
    fx.add_argument("--retrieved-at", type=datetime.fromisoformat, required=True)
    calendar = subparsers.add_parser("xnys-calendar")
    calendar.add_argument("--output-csv", type=Path, required=True)
    calendar.add_argument("--output-manifest", type=Path, required=True)
    calendar.add_argument("--start", type=date.fromisoformat, required=True)
    calendar.add_argument("--end", type=date.fromisoformat, required=True)
    calendar.add_argument("--retrieved-at", type=datetime.fromisoformat, required=True)
    dividends = subparsers.add_parser("nasdaq-dividends")
    dividends.add_argument("--canonical-actions", type=Path, required=True)
    dividends.add_argument("--output-directory", type=Path, required=True)
    dividends.add_argument("--start", type=date.fromisoformat, required=True)
    dividends.add_argument("--end", type=date.fromisoformat, required=True)
    dividends.add_argument("--retrieved-at", type=datetime.fromisoformat, required=True)
    dividends.add_argument("--maximum-workers", type=int, default=8)
    dividends.add_argument("--curated-delistings", type=Path)
    dividends.add_argument("--spdr-distributions-xlsx", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ecb-fx":
        result = rebuild_ecb_gbp_usd(
            args.archive,
            args.output_csv,
            args.output_manifest,
            retrieved_at=args.retrieved_at,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "nasdaq-dividends":
        try:
            import pyarrow.parquet as pq  # type: ignore[import-untyped]
        except ImportError as error:
            raise ValueError("pyarrow is required for canonical action evidence") from error
        rows = pq.read_table(args.canonical_actions).to_pylist()
        actions = tuple(
            (row["security_id"], row["symbol"], row["action_date"], float(row["value"]))
            for row in rows
            if row["action_type"] == "dividend"
        )
        result = acquire_nasdaq_dividend_evidence(
            actions,
            args.output_directory,
            start=args.start,
            end=args.end,
            retrieved_at=args.retrieved_at,
            maximum_workers=args.maximum_workers,
            curated_delistings_path=args.curated_delistings,
            spdr_distributions_path=args.spdr_distributions_xlsx,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "xnys-calendar":
        result = build_independent_xnys_calendar(
            args.output_csv,
            args.output_manifest,
            start=args.start,
            end=args.end,
            retrieved_at=args.retrieved_at,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
