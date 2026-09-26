"""Acquire and build trusted Phase 3 historical-data inputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from src.data.tiingo import (
    TiingoAcquisitionError,
    TiingoRequest,
    UrlLibTiingoTransport,
    acquire_tiingo_extracts,
)


def _requests(path: Path) -> tuple[TiingoRequest, ...]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TiingoAcquisitionError("request plan must be readable JSON") from error
    if not isinstance(payload, list) or not payload:
        raise TiingoAcquisitionError("request plan must be a non-empty list")
    result: list[TiingoRequest] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or set(row) != {
            "security_id",
            "provider_symbol",
            "start",
            "end",
        }:
            raise TiingoAcquisitionError(f"request plan row {index} has invalid fields")
        try:
            result.append(
                TiingoRequest(
                    str(row["security_id"]),
                    str(row["provider_symbol"]),
                    date.fromisoformat(str(row["start"])),
                    date.fromisoformat(str(row["end"])),
                )
            )
        except ValueError as error:
            raise TiingoAcquisitionError(f"request plan row {index} has invalid dates") from error
    return tuple(result)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire immutable Tiingo extracts for the Phase 3 producer."
    )
    parser.add_argument("--request-plan", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--token-environment", default="TIINGO_API_TOKEN")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--api-version", default="v1")
    parser.add_argument("--licence", required=True, help="Reviewed Tiingo licence/terms label")
    parser.add_argument("--minimum-interval-seconds", type=float, default=1.0)
    parser.add_argument("--maximum-attempts", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retrieved-at", help="Aware ISO timestamp; defaults to current UTC")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        when = datetime.fromisoformat(args.retrieved_at) if args.retrieved_at else None
        token = os.environ.get(args.token_environment, "")
        result = acquire_tiingo_extracts(
            _requests(args.request_plan),
            args.output_directory,
            token=token,
            transport=UrlLibTiingoTransport(timeout_seconds=args.timeout_seconds),
            plan=args.plan,
            api_version=args.api_version,
            licence=args.licence,
            retrieved_at=when,
            minimum_interval_seconds=args.minimum_interval_seconds,
            maximum_attempts=args.maximum_attempts,
        )
    except (OSError, ValueError, TiingoAcquisitionError) as error:
        print(f"historical producer acquisition failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "manifest": str(result.manifest_path),
                "successful": result.successful,
                "failed": result.failed,
                "resumed": result.resumed,
                "deployment_admissible": False,
                "paper_execution_permitted": False,
            },
            sort_keys=True,
        )
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
