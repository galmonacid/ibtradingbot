"""Compare sparse SEC-enriched Ridge/XGBoost with frozen price-only controls."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from src.cli.r3_iteration import provenance
from src.data.calendar import load_trading_calendar
from src.learning.r3 import LearningObservation
from src.learning.r3_enriched import EnrichedObservation, fit_enriched
from src.research.r3_development import load_r3_development_dataset
from src.research.r3_fundamental_iteration import (
    admitted_sample_map,
    enrich,
    indexed_ratios,
    load_enriched_config,
    verified_sources,
)
from src.research.r3_iteration import (
    load_config,
    monthly_diagnostic,
    paired_month,
    purged_training,
    sha256,
    summarize,
    write_json,
)
from src.validation.walk_forward import build_expanding_windows


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("use a new output directory")
    config = load_enriched_config(config_path)
    price_config = load_config(Path(config["price_config"]))
    fundamental_report, audit, _ = verified_sources(config)
    indexed = indexed_ratios(fundamental_report)
    mapping = admitted_sample_map(
        audit,
        config["joined_security_ids"],
        {row["cik"] for row in fundamental_report["issuers"]},
    )
    dataset = load_r3_development_dataset(Path(config["price_dataset"]))
    calendar = load_trading_calendar(Path(price_config["calendar"]))
    if calendar.source_sha256 != price_config["calendar_sha256"]:
        raise ValueError("calendar hash differs from baseline registration")
    sessions = tuple(
        day
        for day in calendar.sessions
        if date.fromisoformat(price_config["start"])
        <= day
        <= date.fromisoformat(price_config["complete_through"])
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
        raise ValueError("expected the six frozen later-period folds")
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    raw_features = pq.read_table(
        Path(config["price_dataset"]) / "features.parquet",
        columns=["security_id", "decision_date", "feature_cutoff", "exclusion_reasons"],
    ).to_pylist()
    cutoffs = {
        (row["security_id"], row["decision_date"]): row["feature_cutoff"]
        for row in raw_features
        if not row["exclusion_reasons"]
    }
    if len(cutoffs) != sum(not row["exclusion_reasons"] for row in raw_features):
        raise ValueError("duplicate eligible feature identity/date")
    month_ends = {
        a
        for a, b in zip(sessions, sessions[1:], strict=False)
        if (a.year, a.month) != (b.year, b.month)
    }
    price_rows = tuple(row for row in dataset.observations if row.decision_date in month_ends)
    enriched, coverage = enrich(price_rows, cutoffs, mapping, indexed)
    registration = {
        "contract": config["contract"],
        "registered_at": datetime.now(UTC).isoformat(),
        "config_sha256": sha256(config_path),
        "configuration": config,
        "provenance": provenance(),
        "price_config_sha256": sha256(Path(config["price_config"])),
        "source_dataset_report_sha256": sha256(
            Path(config["price_dataset"]) / "materialization_report.json"
        ),
        "fundamental_source_hashes": fundamental_report["source_hashes"],
        "calendar_sha256": calendar.source_sha256,
        "manual_sample_mapping": mapping,
        "candidate_count": 2,
        "candidate_families": ["ridge", "xgboost"],
        "controls": ["momentum", "ridge", "xgboost"],
        "trial_budget": "one frozen enriched fit per family and segment; no selection",
        "split_policy": "baseline six later-period folds; 31-session and actual-exit purge",
        "feature_policy": "12 original price features plus four SEC ratios and four missing flags",
        "missing_policy": "zero value with explicit indicator; no change to scoring eligibility",
        "selection_policy": "compare price-only and enriched on identical scoring rows",
        "cost_policy": "ranking diagnostic only; no account simulation",
        "development_only": True,
        "qualification_permitted": False,
    }
    output.mkdir(parents=True)
    write_json(output / "registration.json", registration)
    try:
        return _execute(
            config, price_config, output, price_rows, enriched, coverage, sessions, windows
        )
    except Exception as error:
        write_json(
            output / "failure.json",
            {
                "error_type": type(error).__name__,
                "error": str(error),
                "registration_sha256": sha256(output / "registration.json"),
                "failed_at": datetime.now(UTC).isoformat(),
            },
        )
        raise


def _execute(
    config: dict[str, Any],
    price_config: dict[str, Any],
    output: Path,
    price_rows: tuple[LearningObservation, ...],
    enriched: tuple[EnrichedObservation, ...],
    coverage: dict[str, object],
    sessions: tuple[date, ...],
    windows: Any,
) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    source = Path(config["price_dataset"])
    exits = {
        (row["security_id"], row["decision_date"]): row["exit_at"]
        for row in pq.read_table(source / "labels.parquet").to_pylist()
    }
    by_date: dict[date, list[EnrichedObservation]] = defaultdict(list)
    for row in enriched:
        by_date[row.decision_date].append(row)
    by_key = {(row.security_id, row.decision_date): row for row in enriched}
    if len(by_key) != len(enriched):
        raise ValueError("duplicate enriched security/decision row")
    records: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for window in windows:
        for segment, days in (("validation", window.validation), ("test", window.test)):
            decisions = sorted(day for day in by_date if day in days)
            if len(decisions) != (24 if segment == "validation" else 12):
                raise ValueError("missing complete monthly scoring dates")
            cutoff = datetime.combine(days[0], time.min, UTC)
            training_keys = {
                (row.security_id, row.decision_date)
                for row in purged_training(price_rows, exits, sessions, days[0], cutoff)
            }
            training = tuple(
                by_key[key] for key in sorted(training_keys, key=lambda x: (x[1], x[0]))
            )
            monthly: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
            for family in ("momentum", "ridge", "xgboost"):
                path = (
                    Path(config["baseline_run"])
                    / f"fold{window.index}_{segment}_{family}_scores.parquet"
                )
                baseline_scores = pq.read_table(path).to_pylist()
                score_index = {
                    (row["security_id"], row["decision_date"]): float(row["score"])
                    for row in baseline_scores
                }
                expected = {
                    (row.security_id, row.decision_date)
                    for day in decisions
                    for row in by_date[day]
                }
                if len(score_index) != len(baseline_scores) or set(score_index) != expected:
                    raise ValueError("baseline scoring universe differs from enriched universe")
                for day in decisions:
                    rows = by_date[day]
                    scores = [score_index[(row.security_id, day)] for row in rows]
                    diagnostic = monthly_diagnostic(rows, scores, top_k=price_config["top_k"])
                    diagnostic.update(fold=window.index, segment=segment, family=family + "_price")
                    monthly[family + "_price"][day] = diagnostic
                    records.append(diagnostic)
            for family in ("ridge", "xgboost"):
                prefix = f"fold{window.index}_{segment}_{family}_fundamental"
                print(f"Fitting {prefix}: {len(training)} rows", flush=True)
                model = fit_enriched(
                    family,
                    training,
                    cutoff=cutoff,
                    ridge_alpha=config["ridge_alpha"],
                    xgboost_parameters=config["xgboost"],
                    seed=config["seed"],
                )
                manifest = {"fold": window.index, "segment": segment, **model.manifest()}
                manifests.append(manifest)
                (output / f"{prefix}.pkl").write_bytes(model.payload())
                write_json(output / f"{prefix}_manifest.json", manifest)
                predictions: list[dict[str, object]] = []
                for day in decisions:
                    rows = by_date[day]
                    scores = model.score(rows)
                    diagnostic = monthly_diagnostic(rows, scores, top_k=price_config["top_k"])
                    diagnostic.update(
                        fold=window.index, segment=segment, family=family + "_fundamental"
                    )
                    monthly[family + "_fundamental"][day] = diagnostic
                    records.append(diagnostic)
                    predictions.extend(
                        {"security_id": row.security_id, "decision_date": day, "score": score}
                        for row, score in zip(rows, scores, strict=True)
                    )
                pq.write_table(
                    pa.Table.from_pylist(predictions), output / f"{prefix}_scores.parquet"
                )
            for challenger, control in (
                ("ridge_fundamental", "ridge_price"),
                ("xgboost_fundamental", "xgboost_price"),
                ("ridge_fundamental", "momentum_price"),
                ("xgboost_fundamental", "momentum_price"),
            ):
                for day in decisions:
                    pair = paired_month(
                        monthly[challenger][day],
                        monthly[control][day],
                        scenarios=price_config["missing_excess_scenarios"],
                        drags=price_config["incremental_drag_bps"],
                    )
                    pair.update(
                        fold=window.index, segment=segment, challenger=challenger, control=control
                    )
                    pairs.append(pair)
    report = {
        "contract": config["contract"],
        "completed_at": datetime.now(UTC).isoformat(),
        "registration_sha256": sha256(output / "registration.json"),
        "coverage": coverage,
        "summary": summarize(records),
        "monthly_diagnostics": records,
        "paired_diagnostics": pairs,
        "model_manifests": manifests,
        "account_target_assessed": False,
        "qualification_permitted": False,
        "limitations": [
            "Only eight manually matched issuer/security pairs receive SEC values; "
            "the other sampled issuers and all other securities remain missing.",
            "Sample joins are development-only and lack dated issuer/class admission.",
            "Original provider coverage and unresolved-label biases remain unbounded.",
            "Missing indicators may encode source selection as well as economics.",
            "Diagnostic top-five rankings are not funded account returns.",
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
    parser.add_argument("--config", type=Path, default=Path("config.r3-fundamental-iteration.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.config, args.output)
    print(json.dumps({"output": str(args.output), "coverage": report["coverage"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
