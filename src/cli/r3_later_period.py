"""Materialize an immutable later-period calendar and coverage design (no model fits)."""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import io
import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.research.r3_later_period import plan_period
from src.research.r3_source_feasibility import canonical_bytes, sha256_bytes


class _UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate configuration keys."""


def _mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
    if not isinstance(node, yaml.MappingNode):
        raise ValueError("mapping required")
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate config key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def materialize(config_path: Path, output: Path, timestamp: datetime) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    if timestamp.utcoffset() is None:
        raise ValueError("timezone-aware run timestamp required")
    config_bytes = config_path.read_bytes()
    config = yaml.load(config_bytes, Loader=_UniqueLoader)
    fixed = {
        "contract": "r3-later-period-design-v1", "initial_train_years": 8,
        "validation_years": 2, "test_years": 1, "step_months": 12, "purge_sessions": 31,
        "requested_start": "2010-01-01", "calendar_complete_through": "2026-09-15",
    }
    if set(config) != set(fixed) | {"calendar", "features", "sample_coverage"}:
        raise ValueError("unexpected or missing design fields")
    if any(type(config[key]) is not type(value) or config[key] != value
           for key, value in fixed.items()):
        raise ValueError("design change requires a separate contract")
    sources = {}
    for name in ("calendar", "features", "sample_coverage"):
        source = config[name]
        payload = Path(source["path"]).read_bytes()
        if sha256_bytes(payload) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {name}")
        sources[name] = payload
    start = date.fromisoformat(config["requested_start"])
    through = date.fromisoformat(config["calendar_complete_through"])
    if through > timestamp.date():
        raise ValueError("calendar coverage extends beyond run timestamp")
    calendar_rows = list(csv.DictReader(io.StringIO(sources["calendar"].decode())))
    if {row["exchange"] for row in calendar_rows} != {"XNYS"}:
        raise ValueError("expected XNYS calendar")
    import exchange_calendars as xcals  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    independent = tuple(
        stamp.date() for stamp in xcals.get_calendar(
            "XNYS", start=start.isoformat(), end=f"{through.year + 1}-01-10"
        ).sessions
    )
    rows = pq.read_table(io.BytesIO(sources["features"]), columns=[
        "security_id", "decision_date", "exclusion_reasons"
    ]).to_pylist()
    report = plan_period(
        tuple(date.fromisoformat(row["date"]) for row in calendar_rows), independent,
        requested_start=start, complete_through=through,
        feature_keys=((row["security_id"], row["decision_date"],
                       not row["exclusion_reasons"]) for row in rows),
    )
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True
    ).splitlines()
    implementation = {
        name: sha256_bytes(Path(name).read_bytes())
        for name in sorted(set(paths)) if Path(name).is_file()
    }
    report.update({
        "contract": fixed["contract"], "run_timestamp": timestamp.isoformat(),
        "config_sha256": sha256_bytes(config_bytes), "configuration": config,
        "independent_calendar_sha256": sha256_bytes(canonical_bytes(independent)),
        "sample_coverage_evidence": json.loads(sources["sample_coverage"]),
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "implementation_files": implementation,
        "implementation_tree_sha256": sha256_bytes(canonical_bytes(implementation)),
        "dependencies": {item: importlib.metadata.version(item) for item in (
            "exchange-calendars", "pyarrow", "PyYAML"
        )},
        "randomness_used": False, "returns_inspected": False,
        "date_rule": "First complete calendar year after sampled SEC availability in 2009",
    })
    payload = canonical_bytes(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    return {"report_sha256": sha256_bytes(payload),
            "complete_calendar_folds": report["complete_calendar_folds"],
            "model_fitting_permitted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-timestamp", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    print(json.dumps(materialize(args.config, args.output, args.run_timestamp), sort_keys=True))


if __name__ == "__main__":
    main()
