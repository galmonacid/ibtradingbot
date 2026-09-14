"""Like-for-like deterministic-strategy ablation evaluation."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date


class AblationError(ValueError):
    """Raised when ablation evidence is incomplete or not like-for-like."""


DETERMINISTIC_COMPONENTS = (
    "momentum",
    "trend",
    "regime",
    "inverse_volatility",
    "risk_controls",
)


@dataclass(frozen=True)
class AblationScenario:
    name: str
    enabled_components: tuple[str, ...]
    description: str


DETERMINISTIC_ABLATIONS = tuple(
    AblationScenario(
        f"without_{removed}",
        tuple(component for component in DETERMINISTIC_COMPONENTS if component != removed),
        f"Full deterministic strategy without {removed.replace('_', ' ')}.",
    )
    for removed in DETERMINISTIC_COMPONENTS
) + (
    AblationScenario(
        "full_deterministic",
        DETERMINISTIC_COMPONENTS,
        "Full deterministic strategy.",
    ),
)


@dataclass(frozen=True)
class AblationContext:
    oos_dates: tuple[date, ...]
    data_id: str
    cost_id: str

    def __post_init__(self) -> None:
        if not self.oos_dates:
            raise AblationError("ablation OOS dates must not be empty")
        if any(
            later <= earlier
            for earlier, later in zip(self.oos_dates, self.oos_dates[1:], strict=False)
        ):
            raise AblationError("ablation OOS dates must be strictly increasing")
        if not self.data_id or not self.cost_id:
            raise AblationError("ablation data and cost identifiers must not be blank")


@dataclass(frozen=True)
class AblationMetrics:
    values: tuple[tuple[str, float | None], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, float | None]) -> AblationMetrics:
        if not values or any(not name for name in values):
            raise AblationError("ablation metrics must be named and non-empty")
        normalized = tuple(
            sorted(
                (name, None if value is None else float(value)) for name, value in values.items()
            )
        )
        if any(value is not None and not math.isfinite(value) for _name, value in normalized):
            raise AblationError("ablation metrics must be finite")
        return cls(normalized)

    def as_dict(self) -> dict[str, float | None]:
        return dict(self.values)


@dataclass(frozen=True)
class AblationEvaluation:
    context: AblationContext
    metrics: AblationMetrics


@dataclass(frozen=True)
class AblationResult:
    scenario: AblationScenario
    metrics: AblationMetrics
    deltas_vs_full: AblationMetrics


@dataclass(frozen=True)
class AblationAnalysis:
    context: AblationContext
    results: tuple[AblationResult, ...]


AblationEvaluator = Callable[[AblationScenario, AblationContext], AblationEvaluation]


def validate_ablation_results(result_names: tuple[str, ...]) -> None:
    """Require one like-for-like result for every declared deterministic scenario."""
    expected = tuple(item.name for item in DETERMINISTIC_ABLATIONS)
    if result_names != expected:
        raise AblationError(f"ablation results must match declared order: {expected}")


def run_ablation_analysis(
    *, oos_dates: tuple[date, ...], data_id: str, cost_id: str, evaluator: AblationEvaluator
) -> AblationAnalysis:
    """Evaluate deterministic removals and the full model on one immutable context."""
    context = AblationContext(oos_dates, data_id, cost_id)
    evaluations: list[tuple[AblationScenario, AblationEvaluation]] = []
    for scenario in DETERMINISTIC_ABLATIONS:
        evaluation = evaluator(scenario, context)
        if not isinstance(evaluation, AblationEvaluation):
            raise AblationError("ablation evaluator must return AblationEvaluation")
        if evaluation.context != context:
            raise AblationError(f"ablation scenario {scenario.name} returned a different context")
        evaluations.append((scenario, evaluation))

    full_metrics = evaluations[-1][1].metrics.as_dict()
    results: list[AblationResult] = []
    for scenario, evaluation in evaluations:
        metrics = evaluation.metrics.as_dict()
        if tuple(metrics) != tuple(full_metrics):
            raise AblationError("every ablation must return the same metric names")

        delta_values: dict[str, float | None] = {}
        for name, baseline in full_metrics.items():
            value = metrics[name]
            delta_values[name] = None if value is None or baseline is None else value - baseline
        deltas = AblationMetrics.from_mapping(delta_values)
        results.append(AblationResult(scenario, evaluation.metrics, deltas))
    validate_ablation_results(tuple(result.scenario.name for result in results))
    return AblationAnalysis(context, tuple(results))
