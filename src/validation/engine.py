"""Validation-only parameter selection and untouched-test walk-forward execution."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from src.validation.sensitivity import (
    ParameterSet,
    PlateauSelection,
    SensitivityScore,
    select_stable_plateau,
)
from src.validation.walk_forward import WalkForwardWindow, stitch_test_observations


@dataclass(frozen=True)
class SegmentEvaluation:
    """One evaluator result; observations are only populated for test execution."""

    score: float
    observations: tuple[tuple[date, float], ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise ValueError("evaluation score must be finite")


@dataclass(frozen=True)
class FoldEvaluation:
    window: WalkForwardWindow
    validation_scores: tuple[SensitivityScore, ...]
    selection: PlateauSelection
    test: SegmentEvaluation


@dataclass(frozen=True)
class WalkForwardEvaluation:
    folds: tuple[FoldEvaluation, ...]
    stitched_test_observations: tuple[tuple[date, float], ...]


@dataclass(frozen=True)
class EvaluationContext:
    """Dates visible to an evaluator for one chronological segment."""

    fold_index: int
    training_dates: tuple[date, ...]
    evaluation_dates: tuple[date, ...]


Evaluator = Callable[[EvaluationContext, ParameterSet, str], SegmentEvaluation]


def run_walk_forward_selection(
    windows: Sequence[WalkForwardWindow],
    candidates: Sequence[ParameterSet],
    grid_axes: Mapping[str, Sequence[int | float | str]],
    evaluator: Evaluator,
    *,
    relative_tolerance: float = 0.20,
    minimum_viable_neighbours: int = 1,
) -> WalkForwardEvaluation:
    """Choose on validation only, then evaluate the fixed choice once on each test fold."""
    if not windows or not candidates:
        raise ValueError("walk-forward windows and candidates must be non-empty")
    fold_results: list[FoldEvaluation] = []
    stitched_inputs: list[tuple[int, Sequence[tuple[date, float]]]] = []
    for window in windows:
        validation_context = EvaluationContext(window.index, window.train, window.validation)
        scores_list: list[SensitivityScore] = []
        for candidate in candidates:
            validation = evaluator(validation_context, candidate, "validation")
            if validation.observations:
                raise ValueError("validation evaluation must not expose observations")
            scores_list.append(SensitivityScore(candidate, validation.score))
        scores = tuple(scores_list)
        selection = select_stable_plateau(
            scores,
            grid_axes=grid_axes,
            relative_tolerance=relative_tolerance,
            minimum_viable_neighbours=minimum_viable_neighbours,
        )
        test_context = EvaluationContext(
            window.index,
            window.train + window.validation,
            window.test,
        )
        test = evaluator(test_context, selection.selected.parameters, "test")
        fold_results.append(FoldEvaluation(window, scores, selection, test))
        stitched_inputs.append((window.index, test.observations))
    return WalkForwardEvaluation(
        tuple(fold_results),
        stitch_test_observations(stitched_inputs, windows=windows),
    )
