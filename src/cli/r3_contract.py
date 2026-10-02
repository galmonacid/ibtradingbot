"""Inspect the immutable R3.2 registration and fail-closed readiness result."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.config.r3 import load_r3_config
from src.validation.r3_register import assess_r3_readiness, preregister_r3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.r3.yaml"))
    parser.add_argument(
        "--run-timestamp",
        help="timezone-aware ISO timestamp; omit for the current UTC time",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    timestamp = (
        datetime.now(UTC)
        if args.run_timestamp is None
        else datetime.fromisoformat(args.run_timestamp)
    )
    if timestamp.tzinfo is None:
        raise ValueError("--run-timestamp must include a timezone")
    config = load_r3_config(args.config)
    register = preregister_r3(config, timestamp)
    readiness = assess_r3_readiness(config, register)
    payload = {
        "contract": "r3.2",
        "config_sha256": config.sha256,
        "candidate_ids": [row.candidate_id for row in config.candidates],
        "sensitivity_ids": [row.sensitivity_id for row in config.sensitivities],
        "register": asdict(register),
        "register_sha256": register.sha256,
        "readiness": asdict(readiness),
        "disclaimer": "offline research registration; not qualification or trading authorization",
    }
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
