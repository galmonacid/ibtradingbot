from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from src.validation.ablation import (
    DETERMINISTIC_ABLATIONS,
    DETERMINISTIC_COMPONENTS,
    AblationContext,
    AblationError,
    AblationEvaluation,
    AblationMetrics,
    AblationScenario,
    run_ablation_analysis,
    validate_ablation_results,
)


def _dates() -> tuple[date, ...]:
    return tuple(date(2020, 1, 1) + timedelta(days=offset) for offset in range(3))


def test_scenarios_are_full_minus_one_then_full_and_exclude_ml() -> None:
    assert tuple(item.name for item in DETERMINISTIC_ABLATIONS) == (
        "without_momentum",
        "without_trend",
        "without_regime",
        "without_inverse_volatility",
        "without_risk_controls",
        "full_deterministic",
    )
    for scenario, removed in zip(
        DETERMINISTIC_ABLATIONS[:-1], DETERMINISTIC_COMPONENTS, strict=True
    ):
        assert set(scenario.enabled_components) == set(DETERMINISTIC_COMPONENTS) - {removed}
        assert "ml" not in scenario.enabled_components
    assert DETERMINISTIC_ABLATIONS[-1].enabled_components == DETERMINISTIC_COMPONENTS


def test_runner_uses_common_context_and_calculates_deltas() -> None:
    calls: list[tuple[str, AblationContext]] = []

    def evaluator(scenario: AblationScenario, context: AblationContext) -> AblationEvaluation:
        name = scenario.name
        calls.append((name, context))
        value = 10.0 if name == "full_deterministic" else float(len(calls))
        return AblationEvaluation(context, AblationMetrics.from_mapping({"score": value}))

    analysis = run_ablation_analysis(
        oos_dates=_dates(), data_id="bars-v1", cost_id="cost-v1", evaluator=evaluator
    )
    assert [name for name, _context in calls] == [item.name for item in DETERMINISTIC_ABLATIONS]
    assert all(context is calls[0][1] for _name, context in calls)
    assert analysis.results[0].deltas_vs_full.as_dict() == {"score": -9.0}
    assert analysis.results[-1].deltas_vs_full.as_dict() == {"score": 0.0}


def test_runner_rejects_changed_context_or_metric_schema() -> None:
    def changed_context(scenario: AblationScenario, context: AblationContext) -> AblationEvaluation:
        if scenario.name == "without_trend":
            context = replace(context, cost_id="different")
        return AblationEvaluation(context, AblationMetrics.from_mapping({"score": 1.0}))

    with pytest.raises(AblationError, match="different context"):
        run_ablation_analysis(
            oos_dates=_dates(), data_id="bars", cost_id="costs", evaluator=changed_context
        )

    def changed_metrics(scenario: AblationScenario, context: AblationContext) -> AblationEvaluation:
        name = "other" if scenario.name == "without_trend" else "score"
        return AblationEvaluation(context, AblationMetrics.from_mapping({name: 1.0}))

    with pytest.raises(AblationError, match="same metric names"):
        run_ablation_analysis(
            oos_dates=_dates(), data_id="bars", cost_id="costs", evaluator=changed_metrics
        )


def test_invalid_inputs_fail_closed() -> None:
    with pytest.raises(AblationError, match="strictly increasing"):
        AblationContext((_dates()[1], _dates()[0]), "bars", "costs")
    with pytest.raises(AblationError, match="finite"):
        AblationMetrics.from_mapping({"sharpe": float("nan")})
    with pytest.raises(AblationError, match="declared order"):
        validate_ablation_results(("full_deterministic",))
