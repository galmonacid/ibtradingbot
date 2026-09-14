"""Deterministic parameter-grid enumeration and stable-plateau selection."""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ParameterValue = int | float | str


class SensitivityError(ValueError):
    """Raised when a parameter study is incomplete or unsafe."""


@dataclass(frozen=True, order=True)
class ParameterSet:
    values: tuple[tuple[str, ParameterValue], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, ParameterValue]) -> ParameterSet:
        if not values or any(not key for key in values):
            raise SensitivityError("parameter sets must have named values")
        return cls(tuple(sorted(values.items())))

    def as_dict(self) -> dict[str, ParameterValue]:
        return dict(self.values)


@dataclass(frozen=True)
class SensitivityScore:
    parameters: ParameterSet
    validation_score: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.validation_score):
            raise SensitivityError("validation scores must be finite")


@dataclass(frozen=True)
class PlateauSelection:
    selected: SensitivityScore
    viable: tuple[SensitivityScore, ...]
    neighbouring_viable: int
    neighbouring_viable_scores: tuple[float, ...]
    relative_tolerance: float


def parameter_grid(
    values: Mapping[str, Sequence[ParameterValue]],
) -> tuple[ParameterSet, ...]:
    """Enumerate a non-empty broad grid in stable lexical/product order."""
    if not values or any(not key or not choices for key, choices in values.items()):
        raise SensitivityError("every grid dimension must be named and non-empty")
    keys = sorted(values)
    result = [
        ParameterSet.from_mapping(dict(zip(keys, combination, strict=True)))
        for combination in itertools.product(*(values[key] for key in keys))
    ]
    if len(set(result)) != len(result):
        raise SensitivityError("grid dimensions may not contain duplicate values")
    return tuple(result)


def _validated_axes(
    grid_axes: Mapping[str, Sequence[ParameterValue]],
) -> dict[str, tuple[ParameterValue, ...]]:
    if not grid_axes or any(not key or not choices for key, choices in grid_axes.items()):
        raise SensitivityError("every grid axis must be named and non-empty")
    axes = {key: tuple(choices) for key, choices in grid_axes.items()}
    if any(len(set(choices)) != len(choices) for choices in axes.values()):
        raise SensitivityError("grid axes may not contain duplicate values")
    return axes


def _neighbours(
    left: ParameterSet,
    right: ParameterSet,
    axes: Mapping[str, tuple[ParameterValue, ...]],
) -> bool:
    if tuple(key for key, _value in left.values) != tuple(key for key, _value in right.values):
        return False
    differing: list[tuple[str, ParameterValue, ParameterValue]] = []
    for (key, left_value), (_other, right_value) in zip(left.values, right.values, strict=True):
        if left_value != right_value:
            differing.append((key, left_value, right_value))
    if len(differing) != 1:
        return False
    key, left_value, right_value = differing[0]
    choices = axes[key]
    return abs(choices.index(left_value) - choices.index(right_value)) == 1


def select_stable_plateau(
    scores: Sequence[SensitivityScore],
    *,
    grid_axes: Mapping[str, Sequence[ParameterValue]],
    relative_tolerance: float = 0.20,
    minimum_viable_neighbours: int = 1,
) -> PlateauSelection:
    """Select a strong candidate supported by nearby economically similar parameters."""
    if not scores or not 0 <= relative_tolerance < 1 or minimum_viable_neighbours < 1:
        raise SensitivityError("invalid plateau selection inputs")
    if len({item.parameters for item in scores}) != len(scores):
        raise SensitivityError("each parameter set must be scored exactly once")
    axes = _validated_axes(grid_axes)
    expected_keys = tuple(sorted(axes))
    for item in scores:
        if tuple(key for key, _value in item.parameters.values) != expected_keys:
            raise SensitivityError("each score must contain exactly the configured grid axes")
        if any(value not in axes[key] for key, value in item.parameters.values):
            raise SensitivityError("score contains a value absent from its configured grid axis")
    best = max(item.validation_score for item in scores)
    floor = best - max(abs(best), 1e-12) * relative_tolerance
    viable = tuple(
        sorted(
            (item for item in scores if item.validation_score >= floor),
            key=lambda item: item.parameters,
        )
    )
    supported: list[tuple[int, SensitivityScore]] = []
    for item in viable:
        count = sum(
            _neighbours(item.parameters, other.parameters, axes)
            for other in viable
            if other is not item
        )
        if count >= minimum_viable_neighbours:
            supported.append((count, item))
    if not supported:
        raise SensitivityError("validation optimum is an unsupported isolated peak")
    count, selected = min(
        supported,
        key=lambda pair: (-pair[0], -pair[1].validation_score, pair[1].parameters),
    )
    neighbour_scores = tuple(
        item.validation_score
        for item in viable
        if item is not selected and _neighbours(selected.parameters, item.parameters, axes)
    )
    return PlateauSelection(selected, viable, count, neighbour_scores, relative_tolerance)
