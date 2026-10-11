"""Bounded later-period ranking comparison; deliberately not an account backtest."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from src.learning.r3 import LearningObservation

FAMILIES = ("momentum", "ridge", "xgboost")


class RankingRow(Protocol):
    @property
    def security_id(self) -> str: ...

    @property
    def decision_date(self) -> date: ...

    @property
    def target(self) -> float | None: ...


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False, default=str)
        handle.write("\n")


def load_config(path: Path) -> dict[str, Any]:
    import yaml

    from src.config.r3 import _UniqueLoader

    config: Any = yaml.load(path.read_text(), Loader=_UniqueLoader)
    keys = {
        "contract",
        "dataset",
        "dataset_report_sha256",
        "calendar",
        "calendar_sha256",
        "start",
        "complete_through",
        "seed",
        "top_k",
        "ridge_alpha",
        "xgboost",
        "missing_excess_scenarios",
        "incremental_drag_bps",
    }
    if not isinstance(config, dict) or set(config) != keys:
        raise ValueError("unexpected or missing iteration configuration fields")
    if config["contract"] != "r3-iteration-ranking-v1":
        raise ValueError("unsupported iteration contract")
    if config["start"] != "2010-01-01" or config["complete_through"] != "2026-09-15":
        raise ValueError("period amendment requires a new contract")
    for name in ("seed", "top_k"):
        if type(config[name]) is not int or config[name] <= 0:
            raise ValueError(f"positive integer {name} required")
    if config["top_k"] > 5:
        raise ValueError("top_k exceeds registered diagnostic scope")
    for name in ("dataset_report_sha256", "calendar_sha256"):
        value = config[name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError(f"invalid {name}")
    params = config["xgboost"]
    expected = {
        "n_estimators",
        "max_depth",
        "learning_rate",
        "min_child_weight",
        "reg_lambda",
        "reg_alpha",
        "subsample",
        "colsample_bytree",
    }
    if not isinstance(params, dict) or set(params) != expected:
        raise ValueError("unexpected XGBoost parameters")
    numeric = [config["ridge_alpha"], *params.values()]
    for name in ("missing_excess_scenarios", "incremental_drag_bps"):
        if not isinstance(config[name], list) or not config[name]:
            raise ValueError("nonempty sensitivity scenarios required")
        numeric.extend(config[name])
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in numeric):
        raise ValueError("finite numeric parameters required")
    if config["ridge_alpha"] <= 0 or min(config["incremental_drag_bps"]) < 0:
        raise ValueError("positive regularization and nonnegative drag required")
    for name, maximum in (("n_estimators", 200), ("max_depth", 4)):
        if type(params[name]) is not int or not 1 <= params[name] <= maximum:
            raise ValueError("bounded shallow tree budget required")
    if any(params[name] < 0 for name in ("min_child_weight", "reg_lambda", "reg_alpha")):
        raise ValueError("nonnegative regularization required")
    if any(
        not 0 < params[name] <= 1 for name in ("learning_rate", "subsample", "colsample_bytree")
    ):
        raise ValueError("invalid learning or sampling fraction")
    return dict(config)


def purged_training(
    observations: Sequence[LearningObservation],
    label_exits: Mapping[tuple[str, date], datetime],
    sessions: Sequence[date],
    boundary: date,
    cutoff: datetime,
) -> tuple[LearningObservation, ...]:
    """Use all prior history, with a 31-session gap and actual label maturity/exit."""
    index = sessions.index(boundary)
    if index <= 31:
        raise ValueError("insufficient calendar for 31-session purge")
    last_exit = sessions[index - 32]
    return tuple(
        row
        for row in observations
        if sessions[0] <= row.decision_date < boundary
        and row.target is not None
        and row.label_available_at is not None
        and row.label_available_at < cutoff
        and label_exits[(row.security_id, row.decision_date)].date() <= last_exit
    )


def _ranks(values: Sequence[float]) -> list[float]:
    result = [0.0] * len(values)
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    left = 0
    while left < len(ordered):
        right = left + 1
        while right < len(ordered) and values[ordered[left]] == values[ordered[right]]:
            right += 1
        for index in ordered[left:right]:
            result[index] = (left + right - 1) / 2.0
        left = right
    return result


def rank_ic(scores: Sequence[float], targets: Sequence[float]) -> float | None:
    if len(scores) != len(targets):
        raise ValueError("score/target length mismatch")
    if len(scores) < 2 or len(set(scores)) < 2 or len(set(targets)) < 2:
        return None
    return statistics.correlation(_ranks(scores), _ranks(targets))


def monthly_diagnostic(
    observations: Sequence[RankingRow],
    scores: Sequence[float],
    *,
    top_k: int,
) -> dict[str, Any]:
    if not observations or len(scores) != len(observations):
        raise ValueError("nonempty complete scoring cross-section required")
    if len({row.decision_date for row in observations}) != 1:
        raise ValueError("diagnostic must contain exactly one decision date")
    if len({row.security_id for row in observations}) != len(observations):
        raise ValueError("duplicate scoring identity")
    if top_k <= 0 or any(not math.isfinite(score) for score in scores):
        raise ValueError("invalid top_k or score")
    # Select BEFORE inspecting label availability, never replace an unresolved pick.
    chosen = sorted(range(len(scores)), key=lambda i: (-scores[i], observations[i].security_id))[
        :top_k
    ]
    selected = [observations[index] for index in chosen]
    known = [float(row.target) for row in selected if row.target is not None]
    resolved = [index for index, row in enumerate(observations) if row.target is not None]
    return {
        "date": observations[0].decision_date.isoformat(),
        "scored": len(observations),
        "resolved_labels": len(resolved),
        "missing_labels": len(observations) - len(resolved),
        "rank_ic_resolved_only": rank_ic(
            [scores[index] for index in resolved],
            [float(observations[index].target) for index in resolved],  # type: ignore[arg-type]
        ),
        "selected_ids": [row.security_id for row in selected],
        "selected_targets": {row.security_id: row.target for row in selected},
        "selected_missing": len(selected) - len(known),
        "top_mean_excess_if_complete": (
            statistics.mean(known) if len(known) == len(selected) else None
        ),
    }


def paired_month(
    challenger: dict[str, Any],
    control: dict[str, Any],
    *,
    scenarios: Sequence[float],
    drags: Sequence[float],
) -> dict[str, Any]:
    """Cancel common picks, retaining unresolved differential exposure explicitly."""
    if challenger["date"] != control["date"]:
        raise ValueError("paired dates must match")
    left: dict[str, float | None] = challenger["selected_targets"]
    right: dict[str, float | None] = control["selected_targets"]
    known_difference = 0.0
    missing_coefficient = 0.0
    missing_absolute_weight = 0.0
    for security_id in sorted(left.keys() | right.keys()):
        coefficient = (1 / len(left) if security_id in left else 0.0) - (
            1 / len(right) if security_id in right else 0.0
        )
        if security_id in left and security_id in right and left[security_id] != right[security_id]:
            raise ValueError("paired target evidence differs")
        target = left[security_id] if security_id in left else right[security_id]
        if target is None:
            missing_coefficient += coefficient
            missing_absolute_weight += abs(coefficient)
        else:
            known_difference += coefficient * target
    return {
        "date": challenger["date"],
        "known_contribution": known_difference,
        "missing_net_weight": missing_coefficient,
        "missing_absolute_weight": missing_absolute_weight,
        "paired_excess_if_resolved": known_difference if missing_absolute_weight == 0 else None,
        "common_missing_value_break_even": (
            -known_difference / missing_coefficient if abs(missing_coefficient) > 1e-12 else None
        ),
        "scenarios_not_bounds": [
            {
                "missing_excess": value,
                "extra_drag_bps": drag,
                "paired_excess": known_difference + missing_coefficient * value - drag / 10000,
            }
            for value in scenarios
            for drag in drags
        ],
        "adversarial_scenarios_not_bounds": [
            {
                "absolute_missing_excess": bound,
                "lower": known_difference - missing_absolute_weight * bound,
                "upper": known_difference + missing_absolute_weight * bound,
            }
            for bound in sorted({abs(value) for value in scenarios})
        ],
    }


def summarize(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(record["segment"], record["fold"], record["family"])].append(record)
    result = []
    for (segment, fold, family), rows in sorted(grouped.items()):
        ic = [
            row["rank_ic_resolved_only"] for row in rows if row["rank_ic_resolved_only"] is not None
        ]
        complete = [
            row["top_mean_excess_if_complete"]
            for row in rows
            if row["top_mean_excess_if_complete"] is not None
        ]
        result.append(
            {
                "segment": segment,
                "fold": fold,
                "family": family,
                "months": len(rows),
                "scored": sum(row["scored"] for row in rows),
                "resolved_labels": sum(row["resolved_labels"] for row in rows),
                "selected_missing": sum(row["selected_missing"] for row in rows),
                "selected_total": sum(len(row["selected_ids"]) for row in rows),
                "mean_monthly_rank_ic_resolved_only": statistics.mean(ic) if ic else None,
                "complete_top_months": len(complete),
                "mean_top_excess_complete_months_only": statistics.mean(complete)
                if complete
                else None,
            }
        )
    return {"by_fold": result}
