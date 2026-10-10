"""Bounded R3.3 training, causal scoring and common-policy development evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src.backtest.r3 import R3MarketData, R3SimulationResult, simulate_r3_account
from src.config.r3 import CandidateConfig, R3Config
from src.config.r3_development import R3DevelopmentConfig
from src.features.r3 import R3_FEATURE_NAMES
from src.learning.r3 import FittedR3Model, LearningObservation, fit_r3_model


@dataclass(frozen=True)
class R3DevelopmentDataset:
    observations: tuple[LearningObservation, ...]
    split_keys: dict[tuple[int, str], frozenset[tuple[str, date]]]
    scoring_keys: dict[tuple[int, str], frozenset[tuple[str, date]]]
    ready_folds: tuple[int, ...]
    dataset_sha256: str
    split_sha256: str
    scoring_sha256: str
    evidence_limitations: tuple[str, ...]
    config_sha256: str


@dataclass(frozen=True)
class R3DevelopmentRun:
    report: dict[str, object]
    trial_register: dict[str, object]
    models: tuple[FittedR3Model, ...]
    simulations: tuple[R3SimulationResult, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_r3_development_dataset(directory: Path) -> R3DevelopmentDataset:
    """Load and re-bind the immutable R3.2 artifact before any model fitting."""
    try:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as error:  # pragma: no cover - dependency guard
        raise RuntimeError("install historical-data to read the R3.2 artifact") from error
    report_path = directory / "materialization_report.json"
    report: object = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("R3.2 materialization report must be an object")
    if report.get("contract") != "r3.2-development-dataset-v2-label-independent-scoring":
        raise ValueError(
            "R3 evaluation repair requires a new v2 label-independent scoring artifact"
        )
    required = {
        "features": directory / "features.parquet",
        "labels": directory / "labels.parquet",
        "splits": directory / "splits.parquet",
        "scoring": directory / "scoring.parquet",
        "register": directory / "experiment_register.json",
    }
    artifact_hashes = report.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ValueError("R3.2 report lacks artifact identities")
    for name, path in required.items():
        if not path.is_file():
            raise ValueError(f"R3.2 {name} artifact is missing")
        if artifact_hashes.get(name) != _sha256(path):
            raise ValueError(f"R3.2 {name} artifact hash mismatch")
    if (
        report.get("r3_3_development_training_permitted") is not True
        or report.get("r3_2_phase_closed") is not True
        or report.get("qualification_permitted") is not False
    ):
        raise ValueError("R3.2 artifact does not permit development-only R3.3 training")
    feature_rows = pq.read_table(required["features"]).to_pylist()
    labels = {
        (row["security_id"], row["decision_date"]): row
        for row in pq.read_table(required["labels"]).to_pylist()
    }
    observations: list[LearningObservation] = []
    for row in feature_rows:
        if row["exclusion_reasons"]:
            continue
        label = labels.get((row["security_id"], row["decision_date"]))
        if label is None:
            raise ValueError("usable feature row lacks its retained label row")
        observations.append(
            LearningObservation(
                row["security_id"],
                row["decision_date"],
                label["available_at"],
                tuple(float(row[name]) for name in R3_FEATURE_NAMES),
                None if label["excess_return_gbp"] is None else float(label["excess_return_gbp"]),
            )
        )
    split_keys: defaultdict[tuple[int, str], set[tuple[str, date]]] = defaultdict(set)
    for row in pq.read_table(required["splits"]).to_pylist():
        split_keys[(int(row["fold_id"]), str(row["split"]))].add(
            (str(row["security_id"]), row["decision_date"])
        )
    scoring_keys: defaultdict[tuple[int, str], set[tuple[str, date]]] = defaultdict(set)
    for row in pq.read_table(required["scoring"]).to_pylist():
        scoring_keys[(int(row["fold_id"]), str(row["split"]))].add(
            (str(row["security_id"]), row["decision_date"])
        )
    observation_keys = {(row.security_id, row.decision_date) for row in observations}
    if any(not keys <= observation_keys for keys in scoring_keys.values()):
        raise ValueError("scoring contract contains a key without a usable feature row")
    labelled_keys = {
        (row.security_id, row.decision_date)
        for row in observations
        if row.target is not None and row.label_available_at is not None
    }
    if any(not keys <= labelled_keys for keys in split_keys.values()):
        raise ValueError("supervised split contains an unresolved or unavailable label")
    counts = report.get("counts")
    dropped_key = "outcome_conditioned_cash_action_rows_dropped_from_label_artifact"
    if not isinstance(counts, dict) or counts.get(dropped_key) != 0:
        raise ValueError("outcome-conditioned cash-action deletion blocks R3.3")
    ready = report.get("protocol_ready_fold_ids")
    limitations = report.get("evidence_limitations")
    if not isinstance(ready, list) or not ready or not isinstance(limitations, list):
        raise ValueError("R3.2 protocol-ready folds or limitations are unavailable")
    return R3DevelopmentDataset(
        tuple(sorted(observations, key=lambda row: (row.decision_date, row.security_id))),
        {key: frozenset(value) for key, value in split_keys.items()},
        {key: frozenset(value) for key, value in scoring_keys.items()},
        tuple(int(value) for value in ready),
        str(report["dataset_sha256"]),
        str(artifact_hashes["splits"]),
        str(artifact_hashes["scoring"]),
        tuple(str(value) for value in limitations),
        str(report["config_sha256"]),
    )


def _months_between(left: date, right: date) -> int:
    return (right.year - left.year) * 12 + right.month - left.month


def _eligible_by_date(
    keys: frozenset[tuple[str, date]],
) -> dict[date, frozenset[str]]:
    by_date: defaultdict[date, set[str]] = defaultdict(set)
    for security_id, decision_date in keys:
        by_date[decision_date].add(security_id)
    return {decision: frozenset(security_ids) for decision, security_ids in by_date.items()}


def _score_segment(
    candidate: CandidateConfig,
    dataset: R3DevelopmentDataset,
    *,
    training_keys: frozenset[tuple[str, date]],
    score_keys: frozenset[tuple[str, date]],
    config: R3Config,
) -> tuple[dict[date, dict[str, float]], tuple[FittedR3Model, ...]]:
    by_date: defaultdict[date, list[LearningObservation]] = defaultdict(list)
    for row in dataset.observations:
        if (row.security_id, row.decision_date) in score_keys:
            by_date[row.decision_date].append(row)
    training = tuple(
        row
        for row in dataset.observations
        if (row.security_id, row.decision_date) in training_keys
    )
    score_dates = tuple(sorted(by_date))
    if not score_dates:
        raise ValueError("score segment contains no observations")
    result: dict[date, dict[str, float]] = {}
    models: list[FittedR3Model] = []
    model: FittedR3Model | None = None
    last_refit: date | None = None
    for decision in score_dates:
        refit_due = (
            model is None
            or last_refit is None
            or _months_between(last_refit, decision) >= config.refit_months
        )
        if refit_due:
            cutoff = datetime.combine(decision, time(16), ZoneInfo("America/New_York"))
            expanding = training + tuple(
                row
                for row in dataset.observations
                if (row.security_id, row.decision_date) in score_keys
                and row.decision_date < decision
            )
            model = fit_r3_model(
                candidate,
                expanding,
                training_cutoff=cutoff,
                fitted_at=cutoff,
                seed=config.seed,
            )
            models.append(model)
            last_refit = decision
        assert model is not None
        result[decision] = model.score(by_date[decision])
    return result, tuple(models)


def _aggregate(results: Sequence[R3SimulationResult]) -> dict[str, object]:
    valid = [row for row in results if row.return_12m is not None and row.failure is None]
    values = sorted(row.return_12m for row in valid if row.return_12m is not None)
    failure_counts = Counter(row.failure for row in results if row.failure is not None)
    skip_counts: Counter[str] = Counter()
    for row in results:
        skip_counts.update(row.skip_reasons)
    attempted = len(results)
    common = {
        "accounts": attempted,
        "valid_accounts": len(valid),
        "invalid_accounts": attempted - len(valid),
        "failure_counts": dict(sorted(failure_counts.items())),
        "failures": sorted(failure_counts),
        "skip_reason_counts": dict(sorted(skip_counts.items())),
        "account_results": [row.summary() for row in results],
        "development_pass": len(valid) == attempted,
    }
    if not values:
        return common
    def percentile(fraction: float) -> float:
        return values[round((len(values) - 1) * fraction)]
    traded_notional = math.fsum(
        fill.reference_notional_gbp for row in results for fill in row.fills
    )
    return {
        **common,
        # Invalid attempts remain in all overall frequency denominators. Separate
        # survivor-only values are retained only as explicitly labelled diagnostics.
        "target_attainment_frequency": sum(row.target_attained for row in results) / attempted,
        "valid_only_target_attainment_frequency": (
            sum(row.target_attained for row in valid) / len(valid)
        ),
        "loss_frequency": sum(
            row.return_12m is not None and row.return_12m < 0 for row in valid
        )
        / attempted,
        "valid_only_loss_frequency": sum(
            row.return_12m is not None and row.return_12m < 0 for row in valid
        )
        / len(valid),
        "below_minus_15pct_frequency": (
            sum(row.return_12m is not None and row.return_12m < -0.15 for row in valid)
            / attempted
        ),
        "valid_only_below_minus_15pct_frequency": (
            sum(row.return_12m is not None and row.return_12m < -0.15 for row in valid)
            / len(valid)
        ),
        "median_return_12m": statistics.median(values),
        "p05_return_12m": percentile(0.05),
        "p95_return_12m": percentile(0.95),
        "worst_maximum_drawdown": min(
            float(row.maximum_drawdown) for row in valid if row.maximum_drawdown is not None
        ),
        "mean_exposure": statistics.fmean(
            float(row.mean_exposure) for row in valid if row.mean_exposure is not None
        ),
        "mean_cash_weight": statistics.fmean(
            1.0 - float(row.mean_exposure)
            for row in valid
            if row.mean_exposure is not None
        ),
        "fills": sum(len(row.fills) for row in results),
        "mandatory_fills": sum(
            fill.mandatory for row in results for fill in row.fills
        ),
        "traded_notional_gbp": traded_notional,
        "turnover_on_initial_capital": (
            traded_notional / (attempted * results[0].initial_capital_gbp)
        ),
        "halted_sessions": sum(row.halted_sessions for row in results),
        "halted_session_fraction": (
            sum(row.halted_sessions for row in results)
            / sum(len(row.nav) for row in results)
            if any(row.nav for row in results)
            else None
        ),
        "gross_terminal_wealth_gbp": math.fsum(
            float(row.gross_terminal_wealth_gbp) for row in valid
            if row.gross_terminal_wealth_gbp is not None
        ),
        "trading_net_terminal_wealth_gbp": math.fsum(
            float(row.trading_net_terminal_wealth_gbp) for row in valid
            if row.trading_net_terminal_wealth_gbp is not None
        ),
        "all_in_terminal_wealth_gbp": math.fsum(
            float(row.terminal_wealth_gbp) for row in valid if row.terminal_wealth_gbp is not None
        ),
        "commissions_gbp": math.fsum(row.commission_gbp for row in valid),
        "slippage_gbp": math.fsum(row.slippage_gbp for row in valid),
        "fx_friction_gbp": math.fsum(row.fx_friction_gbp for row in valid),
        "conversion_gbp": math.fsum(row.conversion_gbp for row in valid),
        "account_fees_gbp": math.fsum(row.account_fees_gbp for row in valid),
        "liquidation_reserve_gbp": math.fsum(row.liquidation_reserve_gbp for row in valid),
        "unresolved_accrual_gbp": math.fsum(row.unresolved_accrual_gbp for row in valid),
    }


def _paired(
    left: Sequence[R3SimulationResult],
    right: Sequence[R3SimulationResult],
    *,
    paths: int,
    seed: int,
) -> dict[str, object]:
    left_by_start = {row.start_session: row for row in left}
    pairs = [
        (row, left_by_start[row.start_session])
        for row in right
        if row.start_session in left_by_start
        and row.return_12m is not None
        and left_by_start[row.start_session].return_12m is not None
    ]
    differences: list[float] = []
    for challenger, control in pairs:
        assert challenger.return_12m is not None
        assert control.return_12m is not None
        differences.append(challenger.return_12m - control.return_12m)
    if not differences:
        return {"paired_accounts": 0, "promotion_pass": False, "reason": "no_valid_pairs"}
    generator = random.Random(seed)
    means = sorted(
        statistics.fmean(generator.choice(differences) for _ in differences)
        for _ in range(paths)
    )
    lower = means[math.floor(0.025 * (paths - 1))]
    median_uplift = statistics.median(differences)
    right_target = sum(row.target_attained for row, _ in pairs) / len(pairs)
    left_target = sum(row.target_attained for _, row in pairs) / len(pairs)
    right_drawdown = min(
        float(row.maximum_drawdown)
        for row, _ in pairs
        if row.maximum_drawdown is not None
    )
    left_drawdown = min(
        float(row.maximum_drawdown)
        for _, row in pairs
        if row.maximum_drawdown is not None
    )
    return {
        "paired_accounts": len(pairs),
        "median_return_uplift": median_uplift,
        "mean_return_uplift": statistics.fmean(differences),
        "bootstrap_95pct_lower_mean_uplift": lower,
        "challenger_target_attainment": right_target,
        "control_target_attainment": left_target,
        "challenger_worst_drawdown": right_drawdown,
        "control_worst_drawdown": left_drawdown,
        "independent_annual_blocks": len(pairs),
        "uncertainty_note": (
            "limited_independent_annual_blocks; development evidence only"
            if len(pairs) < 10
            else "development bootstrap; not fresh evidence"
        ),
        "promotion_pass": (
            median_uplift >= 0.02
            and right_target >= left_target
            and right_drawdown >= left_drawdown
            and lower > 0
        ),
    }


def _selection_key(
    summary: Mapping[str, object], complexity: int
) -> tuple[float, float, float, int]:
    def number(name: str, default: float) -> float:
        value = summary.get(name, default)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return default

    return (
        number("target_attainment_frequency", -1.0),
        number("median_return_12m", -math.inf),
        -number("fills", math.inf),
        -complexity,
    )


def run_r3_development(
    *,
    dataset: R3DevelopmentDataset,
    market: R3MarketData,
    config: R3Config,
    development: R3DevelopmentConfig,
    source_register: Mapping[str, object],
    run_timestamp: datetime,
) -> R3DevelopmentRun:
    if run_timestamp.tzinfo is None:
        raise ValueError("run timestamp must be timezone-aware")
    required_segments = {
        (fold, split)
        for fold in dataset.ready_folds
        for split in ("train", "validation", "test")
    }
    if not required_segments <= set(dataset.split_keys):
        raise ValueError("supervised split contract is incomplete for a protocol-ready fold")
    if not required_segments <= set(dataset.scoring_keys):
        raise ValueError("scoring-universe contract is incomplete for a protocol-ready fold")
    scoring_audit: dict[str, object] = {}
    for fold in dataset.ready_folds:
        for split in ("validation", "test"):
            keys = dataset.scoring_keys[(fold, split)]
            dates = sorted({decision for _, decision in keys})
            if not dates:
                raise ValueError("registered scoring segment contains no decision dates")
            payload = sorted((security_id, decision.isoformat()) for security_id, decision in keys)
            scoring_audit[f"{fold}:{split}"] = {
                "decision_dates": len(dates),
                "eligible_security_date_rows": len(keys),
                "first_decision_date": dates[0].isoformat(),
                "last_decision_date": dates[-1].isoformat(),
                "universe_sha256": hashlib.sha256(
                    json.dumps(payload, separators=(",", ":")).encode()
                ).hexdigest(),
            }
    all_models: list[FittedR3Model] = []
    simulations: list[R3SimulationResult] = []
    candidate_rows: dict[str, dict[str, object]] = {}
    test_results: dict[str, list[R3SimulationResult]] = {}
    test_scores: dict[str, dict[date, dict[str, float]]] = {}
    outcomes: dict[str, str] = {}
    for candidate in config.candidates:
        validation_runs: list[R3SimulationResult] = []
        candidate_tests: list[R3SimulationResult] = []
        combined_test_scores: dict[date, dict[str, float]] = {}
        candidate_models: list[FittedR3Model] = []
        for fold in dataset.ready_folds:
            train = dataset.split_keys[(fold, "train")]
            validation = dataset.split_keys[(fold, "validation")]
            validation_scoring = dataset.scoring_keys[(fold, "validation")]
            test_scoring = dataset.scoring_keys[(fold, "test")]
            validation_scores, fitted = _score_segment(
                candidate,
                dataset,
                training_keys=train,
                score_keys=validation_scoring,
                config=config,
            )
            candidate_models.extend(fitted)
            validation_dates = tuple(sorted(validation_scores))
            validation_runs.append(
                simulate_r3_account(
                    candidate_id=candidate.candidate_id,
                    scores_by_decision=validation_scores,
                    eligible_by_decision=_eligible_by_date(validation_scoring),
                    market=market,
                    config=config,
                    development=development,
                    first_decision=validation_dates[0],
                )
            )
            test_scores_fold, fitted = _score_segment(
                candidate,
                dataset,
                training_keys=train | validation,
                score_keys=test_scoring,
                config=config,
            )
            candidate_models.extend(fitted)
            overlap = set(combined_test_scores) & set(test_scores_fold)
            if overlap:
                raise ValueError("registered outer-test folds must not overlap")
            combined_test_scores.update(test_scores_fold)
            test_dates = tuple(sorted(test_scores_fold))
            candidate_tests.append(
                simulate_r3_account(
                    candidate_id=candidate.candidate_id,
                    scores_by_decision=test_scores_fold,
                    eligible_by_decision=_eligible_by_date(test_scoring),
                    market=market,
                    config=config,
                    development=development,
                    first_decision=test_dates[0],
                )
            )
        monthly_cohorts: list[R3SimulationResult] = []
        ordered_test_dates = tuple(sorted(combined_test_scores))
        for decision in ordered_test_dates:
            if _months_between(decision, ordered_test_dates[-1]) < 12:
                continue
            monthly_cohorts.append(
                simulate_r3_account(
                    candidate_id=candidate.candidate_id,
                    scores_by_decision=combined_test_scores,
                    eligible_by_decision=_eligible_by_date(
                        frozenset(
                            key
                            for fold in dataset.ready_folds
                            for key in dataset.scoring_keys[(fold, "test")]
                        )
                    ),
                    market=market,
                    config=config,
                    development=development,
                    first_decision=decision,
                )
            )
        continuous = simulate_r3_account(
            candidate_id=candidate.candidate_id,
            scores_by_decision=combined_test_scores,
            eligible_by_decision=_eligible_by_date(
                frozenset(
                    key
                    for fold in dataset.ready_folds
                    for key in dataset.scoring_keys[(fold, "test")]
                )
            ),
            market=market,
            config=config,
            development=development,
            first_decision=ordered_test_dates[0],
            final_session=ordered_test_dates[-1],
            continuous=True,
        )
        validation_summary = _aggregate(validation_runs)
        test_summary = _aggregate(candidate_tests)
        monthly_summary = _aggregate(monthly_cohorts)
        candidate_rows[candidate.candidate_id] = {
            "candidate": asdict(candidate),
            "validation": validation_summary,
            "nonoverlapping_test_cohorts": test_summary,
            "monthly_overlapping_test_cohorts": monthly_summary,
            "continuous_account": continuous.summary(),
            "model_refits": len(candidate_models),
            "model_artifact_sha256": sorted({row.estimator_sha256 for row in candidate_models}),
        }
        test_results[candidate.candidate_id] = candidate_tests
        test_scores[candidate.candidate_id] = combined_test_scores
        all_models.extend(candidate_models)
        simulations.extend(validation_runs + candidate_tests + monthly_cohorts + [continuous])
        outcomes[candidate.candidate_id] = hashlib.sha256(
            json.dumps(
                candidate_rows[candidate.candidate_id],
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()

    ridge_ids = [row.candidate_id for row in config.candidates if row.family == "ridge"]
    tree_ids = [
        row.candidate_id
        for row in config.candidates
        if row.family == "hist_gradient_boosting"
    ]
    best_ridge = max(
        ridge_ids,
        key=lambda value: _selection_key(candidate_rows[value]["validation"], 1),  # type: ignore[arg-type]
    )
    best_tree = max(
        tree_ids,
        key=lambda value: _selection_key(candidate_rows[value]["validation"], 2),  # type: ignore[arg-type]
    )
    comparisons = {
        candidate_id: _paired(
            test_results["R3-M"],
            test_results[candidate_id],
            paths=development.bootstrap_paths,
            seed=config.seed,
        )
        for candidate_id in ridge_ids + tree_ids
    }
    for tree_id in tree_ids:
        comparisons[f"{tree_id}_vs_{best_ridge}"] = _paired(
            test_results[best_ridge],
            test_results[tree_id],
            paths=development.bootstrap_paths,
            seed=config.seed,
        )
    development_decisions: dict[str, dict[str, object]] = {}
    for candidate_id, candidate_row in candidate_rows.items():
        summary = candidate_row["nonoverlapping_test_cohorts"]
        assert isinstance(summary, dict)
        objective_supported = (
            summary.get("development_pass") is True
            and isinstance(summary.get("median_return_12m"), (int, float))
            and float(summary["median_return_12m"]) > config.target_return
            and isinstance(summary.get("target_attainment_frequency"), (int, float))
            and float(summary["target_attainment_frequency"]) > 0.5
        )
        candidate = next(row for row in config.candidates if row.candidate_id == candidate_id)
        promotion_supported = True
        if candidate.family != "momentum":
            promotion_supported = comparisons[candidate_id]["promotion_pass"] is True
        ridge_comparison_supported: bool | None = None
        if candidate.family == "hist_gradient_boosting":
            ridge_comparison_supported = (
                comparisons[f"{candidate_id}_vs_{best_ridge}"]["promotion_pass"] is True
            )
        supports_advancement = (
            objective_supported
            and promotion_supported
            and ridge_comparison_supported is not False
        )
        development_decisions[candidate_id] = {
            "objective_supported": objective_supported,
            "promotion_vs_momentum_supported": promotion_supported,
            "promotion_vs_selected_ridge_supported": ridge_comparison_supported,
            "supports_advancement": supports_advancement,
        }
    completed_trials: list[dict[str, object]] = []
    raw_trials = source_register.get("trials")
    if not isinstance(raw_trials, list):
        raise ValueError("source experiment register lacks trials")
    for row in raw_trials:
        if not isinstance(row, dict) or str(row.get("candidate_id")) not in outcomes:
            raise ValueError("source experiment register trial is invalid")
        candidate_id = str(row["candidate_id"])
        completed_trials.append(
            {
                **row,
                "dataset_sha256": dataset.dataset_sha256,
                "split_sha256": dataset.split_sha256,
                "scoring_sha256": dataset.scoring_sha256,
                "status": "completed",
                "recorded_at": run_timestamp.isoformat(),
                "outcome_sha256": outcomes[candidate_id],
                "failure_reason": None,
            }
        )
    register = {**source_register, "trials": completed_trials}
    register["registration_version"] = "r3-register-v1"
    register["r3_3_recorded_at"] = run_timestamp.isoformat()
    research_accepted = any(
        row["supports_advancement"] is True for row in development_decisions.values()
    )
    report: dict[str, object] = {
        "contract": development.contract_version,
        "development_only": True,
        "qualification_permitted": False,
        "r3_3_implementation_complete": True,
        "r3_3_research_accepted": research_accepted,
        "objective": {
            "initial_capital_gbp": config.initial_capital_gbp,
            "strict_net_profit_gbp": config.target_profit_gbp,
            "strict_terminal_wealth_gbp": config.initial_capital_gbp + config.target_profit_gbp,
            "strict_return": config.target_return,
        },
        "dataset_sha256": dataset.dataset_sha256,
        "split_sha256": dataset.split_sha256,
        "scoring_sha256": dataset.scoring_sha256,
        "evidence_limitations": list(dataset.evidence_limitations),
        "protocol_ready_fold_ids": list(dataset.ready_folds),
        "matched_evaluation_policy": {
            "candidate_ids": [row.candidate_id for row in config.candidates],
            "same_scoring_dates_and_eligibility_universes": True,
            "same_portfolio_cost_and_risk_policy": True,
            "segments": scoring_audit,
        },
        "candidate_table": candidate_rows,
        "validation_selection": {"best_ridge": best_ridge, "best_tree": best_tree},
        "paired_uplift": comparisons,
        "development_decisions": development_decisions,
        "cost_policy": asdict(development),
        "risk_policy": {
            "long_only": True,
            "leverage": False,
            "max_holdings": config.max_holdings,
            "max_position_weight": config.max_position_weight,
            "cash_buffer": config.cash_buffer,
            "soft_drawdown": config.soft_drawdown,
            "hard_drawdown_latched": config.hard_drawdown,
        },
        "run_timestamp": run_timestamp.isoformat(),
        "notes": [
            "All dates are previously inspected development data.",
            "Overlapping monthly cohorts are descriptive, not independent probabilities.",
            "The explicit R3.2 scope decision permits development but does not cure evidence gaps.",
            "No paper/live execution, fresh holdout claim, or qualification is produced.",
            (
                "A corrected development result above 10% would not by itself "
                "demonstrate the objective."
            ),
        ],
    }
    return R3DevelopmentRun(report, register, tuple(all_models), tuple(simulations))


def write_r3_development(result: R3DevelopmentRun, output: Path) -> dict[str, str]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable development output: {output}")
    output.mkdir(parents=True)
    model_directory = output / "models"
    model_directory.mkdir(exist_ok=True)
    model_manifest: list[dict[str, object]] = []
    unique: dict[tuple[str, str], FittedR3Model] = {
        (row.candidate.candidate_id, row.estimator_sha256): row for row in result.models
    }
    for index, ((candidate_id, digest), model) in enumerate(sorted(unique.items())):
        path = model_directory / f"{index:03d}_{candidate_id}_{digest[:12]}.pkl"
        path.write_bytes(pickle.dumps(model, protocol=5))
        model_manifest.append({**model.manifest(), "path": path.name, "file_sha256": _sha256(path)})
    (output / "model_manifest.json").write_text(
        json.dumps(model_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "experiment_register.json").write_text(
        json.dumps(result.trial_register, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    report = dict(result.report)
    report["model_manifest_sha256"] = _sha256(output / "model_manifest.json")
    report["experiment_register_sha256"] = _sha256(output / "experiment_register.json")
    (output / "development_report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return {
        name: _sha256(output / name)
        for name in (
            "development_report.json",
            "experiment_register.json",
            "model_manifest.json",
        )
    }
