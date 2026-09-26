"""CLI for content- and origin-bound Git source manifests."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from src.data.git_source import (
    APPROVED_SOURCE_ORIGINS,
    GitSourceError,
    create_git_source_manifest,
    tracked_files_under,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a verified manifest for an approved Git source."
    )
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-name", choices=sorted(APPROVED_SOURCE_ORIGINS), required=True)
    parser.add_argument("--licence", required=True)
    parser.add_argument("--file", action="append", dest="files", default=[])
    parser.add_argument("--tree", action="append", dest="trees", default=[])
    parser.add_argument("--retrieved-at", type=datetime.fromisoformat)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        files = tuple(args.files) + tracked_files_under(args.checkout, tuple(args.trees))
        path = create_git_source_manifest(
            args.checkout,
            args.output,
            source_name=args.source_name,
            licence=args.licence,
            relative_files=files,
            retrieved_at=args.retrieved_at,
        )
    except (OSError, GitSourceError) as error:
        print(f"Git source snapshot failed: {error}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
