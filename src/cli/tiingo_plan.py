"""Derive a complete Tiingo request plan from pinned membership and identity sources."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from src.data.git_source import verify_git_source_snapshot
from src.data.source_adapters import transform_identity_source, transform_membership_source
from src.data.trusted_historical import (
    DatedSecurityIdentity,
    build_security_membership_intervals,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a complete Tiingo request plan from pinned Phase 3 Git sources."
    )
    parser.add_argument("--membership-manifest", type=Path, required=True)
    parser.add_argument("--membership-root", type=Path, required=True)
    parser.add_argument("--membership-file", required=True)
    parser.add_argument("--identity-manifest", type=Path, required=True)
    parser.add_argument("--identity-root", type=Path, required=True)
    parser.add_argument("--identity-file", required=True)
    parser.add_argument("--coverage-start", type=date.fromisoformat, required=True)
    parser.add_argument("--coverage-end", type=date.fromisoformat, required=True)
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=400,
        help="Calendar-day history requested before first membership for feature warm-up.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.coverage_end < args.coverage_start:
            raise ValueError("coverage end precedes coverage start")
        if args.lookback_days < 0:
            raise ValueError("lookback days must be non-negative")
        membership = transform_membership_source(
            verify_git_source_snapshot(args.membership_manifest, args.membership_root),
            args.membership_root,
            args.membership_file,
        )
        symbols = tuple(
            sorted(
                {symbol for snapshot in membership.memberships for symbol in snapshot.symbols}
                | {args.benchmark_symbol}
            )
        )
        identity = transform_identity_source(
            verify_git_source_snapshot(args.identity_manifest, args.identity_root),
            args.identity_root,
            args.identity_file,
            coverage_start=args.coverage_start,
            known_symbols=symbols,
            preserve_symbol_reuse=True,
        )
        resolver = DatedSecurityIdentity(identity.parsed.identity_intervals)
        memberships = build_security_membership_intervals(
            membership.memberships,
            resolver,
            source_version=membership.snapshot.manifest_sha256,
        )
        raw_bounds: dict[str, list[tuple[date, date]]] = {}
        for row in memberships:
            start = max(
                args.coverage_start,
                row.effective_from - timedelta(days=args.lookback_days),
            )
            # Membership is half-open, but the removal session is still required to execute
            # the prior close's exit decision and value any terminal disposition.
            end = min(args.coverage_end, row.effective_to or args.coverage_end)
            raw_bounds.setdefault(row.security_id, []).append((start, end))
        bounds: dict[str, tuple[tuple[date, date], ...]] = {}
        for security_id, windows in raw_bounds.items():
            merged: list[tuple[date, date]] = []
            for start, end in sorted(windows):
                if merged and start <= merged[-1][1] + timedelta(days=1):
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            bounds[security_id] = tuple(merged)
        benchmark_id = resolver.resolve(args.benchmark_symbol, args.coverage_start)
        bounds[benchmark_id] = ((args.coverage_start, args.coverage_end),)

        requests: list[dict[str, str]] = []
        for interval in identity.parsed.identity_intervals:
            needed_windows = bounds.get(interval.security_id)
            if needed_windows is None:
                continue
            for needed_start, needed_end in needed_windows:
                start = max(interval.effective_from, needed_start)
                end = min(
                    needed_end,
                    (
                        interval.effective_to - timedelta(days=1)
                        if interval.effective_to is not None
                        else needed_end
                    ),
                )
                if start <= end:
                    requests.append(
                        {
                            "security_id": interval.security_id,
                            "provider_symbol": interval.symbol,
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                        }
                    )
        if not requests:
            raise ValueError("identity history produced no Tiingo requests")
        requests.sort(key=lambda row: (row["security_id"], row["start"], row["provider_symbol"]))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(requests, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError) as error:
        print(f"Tiingo plan generation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output), "requests": len(requests)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
