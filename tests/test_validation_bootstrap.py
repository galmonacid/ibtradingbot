from __future__ import annotations

import math

import pytest

from src.validation.bootstrap import (
    bootstrap_validation,
    circular_block_samples,
    regime_block_samples,
)


def test_circular_block_bootstrap_is_seeded_and_wraps() -> None:
    first = circular_block_samples([0.01, 0.02, 0.03], block_length=2, seed=7)
    second = circular_block_samples([0.01, 0.02, 0.03], block_length=2, seed=7)
    assert first == second
    assert len(first) == 2_000
    assert all(len(sample) == 3 for sample in first)
    assert any((0.03, 0.01) in tuple(zip(sample, sample[1:], strict=False)) for sample in first)


def test_regime_bootstrap_samples_contiguous_observed_runs() -> None:
    returns = [0.01, 0.02, -0.03, -0.04, 0.05]
    regimes = ["on", "on", "off", "off", "on"]
    samples = regime_block_samples(returns, regimes, seed=11)
    observed_runs = {
        ((0.01, "on"), (0.02, "on")),
        ((-0.03, "off"), (-0.04, "off")),
        ((0.05, "on"),),
    }
    assert len(samples) == 2_000
    assert all(len(sample) >= len(returns) for sample in samples)
    assert all(len(sample) <= len(returns) + max(map(len, observed_runs)) - 1 for sample in samples)
    # Every path is a concatenation of complete observed episodes, including its final run.
    for sample in samples:
        cursor = 0
        while cursor < len(sample):
            run = next(run for run in observed_runs if sample[cursor : cursor + len(run)] == run)
            cursor += len(run)
        assert cursor == len(sample)


def test_regime_bootstrap_rejects_degenerate_episode_history() -> None:
    with pytest.raises(ValueError, match="two distinct regimes"):
        regime_block_samples([0.01, 0.02, 0.03], ["on", "on", "on"])


def test_analysis_reports_distributions_quantiles_and_honest_horizons() -> None:
    returns = [0.001 if index % 3 else -0.0005 for index in range(300)]
    regimes = ["on" if index < 150 else "neutral" for index in range(300)]
    result = bootstrap_validation(returns, [0.10, -0.05, 0.03], regimes, seed=19)
    assert result == bootstrap_validation(returns, [0.10, -0.05, 0.03], regimes, seed=19)
    assert len(result.daily.cagr.samples) == 2_000
    assert result.daily.cagr.q05 <= result.daily.cagr.q50 <= result.daily.cagr.q95
    assert result.daily.one_year_return is not None
    assert result.daily.three_year_return is None
    assert result.regime_blocks.one_year_return is not None
    assert result.mean_trade_return is not None
    assert all(math.isfinite(value) for value in result.mean_trade_return.samples)


def test_three_year_distribution_requires_full_three_year_horizon() -> None:
    returns = [0.0001, -0.0001] * 378
    regimes = ["on" if index < 378 else "off" for index in range(len(returns))]
    result = bootstrap_validation(returns, [], regimes, seed=3)
    assert result.daily.three_year_return is not None
    assert result.regime_blocks.three_year_return is not None
    assert result.mean_trade_return is None


@pytest.mark.parametrize(
    ("call", "error"),
    [
        (lambda: circular_block_samples([], block_length=1), ValueError),
        (lambda: circular_block_samples([0.1], block_length=0), ValueError),
        (lambda: circular_block_samples([0.1], block_length=1, iterations=1_999), ValueError),
        (lambda: circular_block_samples([float("nan")], block_length=1), ValueError),
        (lambda: circular_block_samples([-1.0], block_length=1), ValueError),
        (lambda: regime_block_samples([0.1], []), ValueError),
        (lambda: regime_block_samples([0.1], [""]), ValueError),
        (
            lambda: bootstrap_validation([0.1], [float("inf")], ["on"]),
            ValueError,
        ),
    ],
)
def test_invalid_inputs_fail_closed(call: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        call()  # type: ignore[operator]
