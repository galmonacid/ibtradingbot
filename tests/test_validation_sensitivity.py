import pytest

from src.validation.sensitivity import (
    ParameterSet,
    SensitivityError,
    SensitivityScore,
    parameter_grid,
    select_stable_plateau,
)


def _score(value: float, **parameters: int | float | str) -> SensitivityScore:
    return SensitivityScore(ParameterSet.from_mapping(parameters), value)


def test_grid_is_complete_and_deterministic() -> None:
    grid = parameter_grid({"positions": [3, 4, 5], "vol_target": [0.10, 0.12]})
    assert len(grid) == 6
    assert grid[0].as_dict() == {"positions": 3, "vol_target": 0.10}
    assert grid[-1].as_dict() == {"positions": 5, "vol_target": 0.12}


def test_plateau_prefers_supported_region_over_isolated_maximum() -> None:
    result = select_stable_plateau(
        [
            _score(1.00, positions=3, skip=0),
            _score(0.91, positions=4, skip=5),
            _score(0.90, positions=4, skip=10),
            _score(0.89, positions=5, skip=5),
        ],
        grid_axes={"positions": [3, 4, 5], "skip": [0, 5, 10]},
        relative_tolerance=0.15,
    )
    assert result.selected.parameters.as_dict() == {"positions": 4, "skip": 5}
    assert result.neighbouring_viable == 2


def test_isolated_peak_fails_instead_of_overfitting() -> None:
    with pytest.raises(SensitivityError, match="isolated"):
        select_stable_plateau(
            [_score(1.0, positions=3), _score(0.1, positions=4)],
            grid_axes={"positions": [3, 4]},
            relative_tolerance=0.05,
        )


def test_duplicate_grid_values_and_scores_fail_closed() -> None:
    with pytest.raises(SensitivityError):
        parameter_grid({"positions": [3, 3]})
    item = _score(1.0, positions=3)
    with pytest.raises(SensitivityError):
        select_stable_plateau([item, item], grid_axes={"positions": [3]})


def test_distant_values_are_not_treated_as_adjacent() -> None:
    with pytest.raises(SensitivityError, match="isolated"):
        select_stable_plateau(
            [_score(1.0, positions=3), _score(0.99, positions=50)],
            grid_axes={"positions": [3, 4, 5, 50]},
        )


def test_scores_must_match_declared_grid_topology() -> None:
    with pytest.raises(SensitivityError, match="absent"):
        select_stable_plateau(
            [_score(1.0, positions=3)],
            grid_axes={"positions": [4, 5]},
        )
