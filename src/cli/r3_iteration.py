"""Run one preregistered Momentum/Ridge/XGBoost ranking diagnostic on local data."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from src.data.calendar import load_trading_calendar
from src.learning.r3 import LearningObservation
from src.learning.r3_iteration import fit_iteration_model
from src.research.r3_development import load_r3_development_dataset
from src.research.r3_iteration import (
    FAMILIES,
    load_config,
    monthly_diagnostic,
    paired_month,
    purged_training,
    sha256,
    summarize,
    write_json,
)
from src.validation.walk_forward import WalkForwardWindow, build_expanding_windows


def provenance() -> dict[str, Any]:
    def git(*arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], text=True).strip()

    paths = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    return {
        "git_revision": git("rev-parse", "HEAD"),
        "git_committed_tree": git("rev-parse", "HEAD^{tree}"),
        "git_status": git("status", "--short"),
        "working_files_sha256": {
            name: sha256(Path(name)) for name in sorted(set(paths)) if Path(name).is_file()
        },
        "python": platform.python_version(),
        "dependencies": dict(
            sorted(
                (str(dist.metadata["Name"]), dist.version)
                for dist in importlib.metadata.distributions()
            )
        ),
    }


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("use a new output directory; failed runs are retained")
    config = load_config(config_path)
    dataset_path = Path(config["dataset"])
    source_report = dataset_path / "materialization_report.json"
    if sha256(source_report) != config["dataset_report_sha256"]:
        raise ValueError("source dataset report hash mismatch")
    calendar = load_trading_calendar(Path(config["calendar"]))
    if calendar.source_sha256 != config["calendar_sha256"]:
        raise ValueError("calendar hash mismatch")
    sessions = tuple(
        day
        for day in calendar.sessions
        if date.fromisoformat(config["start"])
        <= day
        <= date.fromisoformat(config["complete_through"])
    )
    windows = build_expanding_windows(
        sessions,
        verified_complete_through=sessions[-1],
        initial_train_years=8,
        validation_years=2,
        test_years=1,
        step_months=12,
    )
    if len(windows) != 6:
        raise ValueError("expected six registered later-period windows")
    dataset = load_r3_development_dataset(dataset_path)
    timestamp = datetime.now(UTC)
    if sessions[-1] > timestamp.date():
        raise ValueError("cannot evaluate future coverage")
    lineage = json.loads(source_report.read_text())
    registration = {
        "contract": config["contract"],
        "registered_at": timestamp.isoformat(),
        "configuration": config,
        "config_sha256": sha256(config_path),
        "provenance": provenance(),
        "source_materialization_report": lineage,
        "candidate_count": 3,
        "families": FAMILIES,
        "feature_family": "existing 12 causal price/volume/market features only",
        "fit_policy": "one fixed fit at each segment start; no within-segment refit",
        "training_policy": "expanding past only, actual exit/maturity and 31-session purge",
        "selection_policy": "fixed candidates; descriptive comparison without tuning or selection",
        "weights": "equal date totals normalized to mean row weight 1",
        "account_cost_model": "not applicable: ranking diagnostic, not account simulation",
        "cost_sensitivity": "illustrative extra monthly diagnostic drag; not tariff evidence",
        "folds": [
            {
                "fold": window.index,
                "train_start": window.train[0],
                "validation_start": window.validation[0],
                "test_start": window.test[0],
                "test_end": window.test[-1],
            }
            for window in windows
        ],
        "development_only": True,
        "qualification_permitted": False,
    }
    output.mkdir(parents=True)
    write_json(output / "registration.json", registration)
    try:
        return _execute(
            config,
            output,
            dataset.observations,
            sessions,
            windows,
            dataset_path,
            dataset.evidence_limitations,
            timestamp,
        )
    except Exception as error:
        write_json(
            output / "failure.json",
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "registration_sha256": sha256(output / "registration.json"),
                "failed_at": datetime.now(UTC).isoformat(),
            },
        )
        raise


def _execute(
    config: dict[str, Any],
    output: Path,
    observations: tuple[LearningObservation, ...],
    sessions: tuple[date, ...],
    windows: tuple[WalkForwardWindow, ...],
    dataset_path: Path,
    limitations: tuple[str, ...],
    timestamp: datetime,
) -> dict[str, Any]:
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    label_rows = pq.read_table(dataset_path / "labels.parquet").to_pylist()
    exits = {(row["security_id"], row["decision_date"]): row["exit_at"] for row in label_rows}
    # The artifact's partial final month is excluded; no outcome-conditioned eligibility.
    month_ends = {
        left
        for left, right in zip(sessions, sessions[1:], strict=False)
        if (left.year, left.month) != (right.year, right.month)
    }
    rows = tuple(row for row in observations if row.decision_date in month_ends)
    if any(
        row.label_available_at is not None and row.label_available_at > timestamp for row in rows
    ):
        raise ValueError("source artifact contains not-yet-matured diagnostic labels")
    by_date: dict[date, list[LearningObservation]] = defaultdict(list)
    for row in rows:
        by_date[row.decision_date].append(row)
    feature_rows = pq.read_table(
        dataset_path / "features.parquet",
        columns=["decision_date", "security_id", "exclusion_reasons"],
    ).to_pylist()
    coverage: dict[date, dict[str, int]] = defaultdict(lambda: {"retained": 0, "excluded": 0})
    for row in feature_rows:
        if row["decision_date"] in month_ends:
            item = coverage[row["decision_date"]]
            item["retained"] += 1
            item["excluded"] += bool(row["exclusion_reasons"])
    records: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for window in windows:
        for segment, segment_days in (("validation", window.validation), ("test", window.test)):
            boundary = segment_days[0]
            cutoff = datetime.combine(boundary, time.min, UTC)
            training = purged_training(rows, exits, sessions, boundary, cutoff)
            decisions = sorted(month_ends.intersection(segment_days))
            if not decisions or any(day not in by_date for day in decisions):
                raise ValueError("missing scoring month; cannot silently skip dates")
            monthly: dict[str, dict[date, dict[str, Any]]] = {}
            for family in FAMILIES:
                prefix = f"fold{window.index}_{segment}_{family}"
                print(f"Fitting {prefix}: {len(training)} purged rows", flush=True)
                model = fit_iteration_model(
                    family,
                    training,
                    cutoff,
                    ridge_alpha=config["ridge_alpha"],
                    xgboost_parameters=config["xgboost"],
                    seed=config["seed"],
                )
                manifest = {"fold": window.index, "segment": segment, **model.manifest()}
                manifests.append(manifest)
                (output / f"{prefix}.pkl").write_bytes(model.payload())
                write_json(output / f"{prefix}_manifest.json", manifest)
                predictions: list[dict[str, object]] = []
                monthly[family] = {}
                for decision in decisions:
                    score_rows = by_date[decision]
                    scores = model.score(score_rows)
                    diagnostic = monthly_diagnostic(score_rows, scores, top_k=config["top_k"])
                    diagnostic.update(fold=window.index, segment=segment, family=family)
                    monthly[family][decision] = diagnostic
                    records.append(diagnostic)
                    predictions.extend(
                        {
                            "security_id": row.security_id,
                            "decision_date": row.decision_date,
                            "score": score,
                        }
                        for row, score in zip(score_rows, scores, strict=True)
                    )
                pq.write_table(
                    pa.Table.from_pylist(predictions), output / f"{prefix}_scores.parquet"
                )
            for challenger, control in (
                ("ridge", "momentum"),
                ("xgboost", "momentum"),
                ("xgboost", "ridge"),
            ):
                for decision in decisions:
                    pair = paired_month(
                        monthly[challenger][decision],
                        monthly[control][decision],
                        scenarios=config["missing_excess_scenarios"],
                        drags=config["incremental_drag_bps"],
                    )
                    pair.update(
                        fold=window.index, segment=segment, challenger=challenger, control=control
                    )
                    pairs.append(pair)
    report = {
        "contract": config["contract"],
        "completed_at": datetime.now(UTC).isoformat(),
        "registration_sha256": sha256(output / "registration.json"),
        "summary": summarize(records),
        "monthly_diagnostics": records,
        "paired_diagnostics": pairs,
        "model_manifests": manifests,
        "coverage": [
            {"date": day.isoformat(), **counts} for day, counts in sorted(coverage.items())
        ],
        "coverage_denominator": "retained source rows, NOT full historical membership",
        "original_historical_identity_audit_denominator": 793,
        "qualification_permitted": False,
        "account_target_assessed": False,
        "conclusion": "conditional ranking diagnostics only; no candidate promoted",
        "limitations": [
            *limitations,
            "Source histories unchanged; selection and identity biases remain unbounded.",
            "Unresolved labels affect supervised training and IC; scores retain all eligible rows.",
            "Top-five is a diagnostic basket, not a funded portfolio or execution policy.",
            "Illustrative missing-outcome scenarios are not evidenced uncertainty bounds.",
            "No net account return, target attainment or cost-adjusted promotion is established.",
            "Validation windows overlap: do not pool them as independent evidence.",
            "Six annual test blocks are inspected development data, not fresh holdouts.",
            "Fundamentals deferred; this isolates estimator effects on existing features.",
        ],
    }
    write_json(output / "report.json", report)
    write_json(
        output / "artifact_manifest.json",
        {path.name: sha256(path) for path in sorted(output.iterdir()) if path.is_file()},
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.r3-iteration.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.config, args.output)
    print(json.dumps({"output": str(args.output), "conclusion": report["conclusion"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
