"""Generate a content-bound native canonical execution diagnostic."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.validation.native_inputs import create_native_validation_inputs
from src.validation.native_report import (
    build_native_validation_report,
    write_native_validation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--validation-spec", type=Path, required=True)
    parser.add_argument("--dataset-evidence", type=Path)
    parser.add_argument("--universe-policy", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--strategy-version", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        inputs = create_native_validation_inputs(
            canonical_manifest_path=args.canonical_manifest,
            config_path=args.config,
            validation_spec_path=args.validation_spec,
            repository_root=args.repository_root,
            strategy_version=args.strategy_version,
            dataset_evidence_path=args.dataset_evidence,
            universe_policy_path=args.universe_policy,
        )
        result = build_native_validation_report(inputs)
        write_native_validation_report(
            result, json_path=args.json_output, markdown_path=args.markdown_output
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"native validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
