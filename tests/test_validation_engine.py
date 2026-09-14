from datetime import date

import pytest

from src.validation.engine import EvaluationContext, SegmentEvaluation, run_walk_forward_selection
from src.validation.sensitivity import ParameterSet, parameter_grid
from src.validation.walk_forward import WalkForwardWindow


def test_selection_uses_validation_and_calls_test_only_for_fixed_choice() -> None:
    window = WalkForwardWindow(
        0,
        (date(2010, 1, 1),),
        (date(2011, 1, 1),),
        (date(2012, 1, 1), date(2012, 1, 2)),
    )
    axes = {"positions": (3, 4, 5)}
    candidates = parameter_grid(axes)
    test_calls: list[dict[str, int | float | str]] = []

    def evaluator(
        fold: EvaluationContext, parameters: ParameterSet, segment: str
    ) -> SegmentEvaluation:
        positions = int(parameters.as_dict()["positions"])
        if segment == "validation":
            return SegmentEvaluation({3: 0.9, 4: 1.0, 5: 0.91}[positions])
        test_calls.append(parameters.as_dict())
        return SegmentEvaluation(999.0, tuple((day, 0.01) for day in fold.evaluation_dates))

    result = run_walk_forward_selection([window], candidates, axes, evaluator)
    assert test_calls == [{"positions": 4}]
    assert result.folds[0].selection.selected.parameters.as_dict() == {"positions": 4}
    assert result.stitched_test_observations == (
        (date(2012, 1, 1), 0.01),
        (date(2012, 1, 2), 0.01),
    )


def test_test_scores_cannot_change_parameter_selection() -> None:
    window = WalkForwardWindow(
        0,
        (date(2010, 1, 1),),
        (date(2011, 1, 1),),
        (date(2012, 1, 1),),
    )
    axes = {"positions": (3, 4)}
    candidates = parameter_grid(axes)

    def run(test_preference: int) -> dict[str, int | float | str]:
        def evaluator(
            fold: EvaluationContext, parameters: ParameterSet, segment: str
        ) -> SegmentEvaluation:
            position = int(parameters.as_dict()["positions"])
            if segment == "validation":
                return SegmentEvaluation(1.0 if position == 3 else 0.95)
            score = 10_000.0 if position == test_preference else -10_000.0
            return SegmentEvaluation(score, ((fold.evaluation_dates[0], 0.0),))

        result = run_walk_forward_selection([window], candidates, axes, evaluator)
        return result.folds[0].selection.selected.parameters.as_dict()

    assert run(3) == run(4) == {"positions": 3}


def test_validation_evaluator_cannot_return_observations() -> None:
    window = WalkForwardWindow(0, (date(2010, 1, 1),), (date(2011, 1, 1),), (date(2012, 1, 1),))
    candidate = ParameterSet.from_mapping({"positions": 3})

    def evaluator(
        context: EvaluationContext, parameters: ParameterSet, segment: str
    ) -> SegmentEvaluation:
        return SegmentEvaluation(1.0, ((context.evaluation_dates[0], 0.01),))

    with pytest.raises(ValueError, match="must not expose observations"):
        run_walk_forward_selection([window], [candidate], {"positions": (3,)}, evaluator)
