"""Single-change controls retain the original V1 default and safety contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_v2_backtest import market_fixture

from src.data.canonical_historical import CanonicalSourceProvenance, write_canonical_parquet
from src.data.trusted_historical import SecurityIdentityInterval, SecurityMembershipInterval
from src.validation.native_inputs import create_native_validation_inputs
from src.validation.native_strategy import (
    NativeStrategyError,
    NativeStrategyParameters,
    build_native_strategy_context,
    build_native_targets,
)
from src.validation.v2_diagnostics import (
    diagnostic_dual_scale,
    diagnostic_momentum_rank,
    diagnostic_spy_ceiling,
    run_v1_single_change_diagnostics,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    pytest.importorskip("pyarrow")
    market, _, start, end = market_fixture()
    first = market.calendar.sessions[0]
    dataset = write_canonical_parquet(
        tmp_path / "canonical",
        bars=tuple(bar for rows in market.bars.values() for bar in rows.values()),
        identities=tuple(
            SecurityIdentityInterval(symbol, symbol, first, None) for symbol in market.bars
        ),
        memberships=tuple(
            SecurityMembershipInterval("fixture", symbol, first, None) for symbol in market.bars
        ),
        actions=(),
        source_provenance=(
            CanonicalSourceProvenance(
                "test",
                "git",
                "a" * 64,
                "2026-09-16T00:00:00+00:00",
                "MIT",
                repository_url="https://example.test/source",
                commit_sha="b" * 40,
            ),
        ),
        transformation_version="synthetic-test",
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        (ROOT / "config.example.yaml")
        .read_text()
        .replace("source: fixed_seed", "source: trusted_canonical")
    )
    monkeypatch.setattr(
        "src.validation.native_inputs._git",
        lambda root, *arguments: "b" * 40 if arguments[0] == "rev-parse" else "",
    )
    inputs = create_native_validation_inputs(
        canonical_manifest_path=dataset.manifest_path,
        config_path=config,
        validation_spec_path=ROOT / "docs/BACKTEST_AND_VALIDATION.md",
        repository_root=ROOT,
        strategy_version="v1-test",
    )
    return inputs, start, end


def test_default_unchanged_and_single_changes_do_not_disable_safety(native) -> None:  # type: ignore[no-untyped-def]
    inputs, start, end = native
    context = build_native_strategy_context(inputs)
    default = build_native_targets(inputs, context=context)
    explicit = build_native_targets(
        inputs, NativeStrategyParameters(diagnostic_change=None), context=context
    )
    assert default.target_sha256 == explicit.target_sha256
    assert default.targets_by_signal_date == explicit.targets_by_signal_date
    with pytest.raises(NativeStrategyError, match="combine"):
        NativeStrategyParameters(diagnostic_change="score", disabled_component="risk_controls")
    market, _, _, _ = market_fixture()
    report = run_v1_single_change_diagnostics(inputs, start=start, end=end, v2_market=market)
    assert len(report["runs"]) == 7
    assert all(item["status"] == "executed" for item in report["runs"].values())
    assert report["currency"] == "USD" and report["evidence_class"] == "development"
    fixed = report["runs"]["fixed_v2"]
    assert fixed["execution_audit"]["passed"]
    assert fixed["first_point"] == report["runs"]["original_v1"]["first_point"]
    assert fixed["last_point"] == report["runs"]["original_v1"]["last_point"]
    assert fixed["costs"]["commission_per_share"] == 0
    assert fixed["costs"]["commission_min_usd"] == report["cost_model"]["commission"]
    assert fixed["costs"]["slippage_bps"] == report["cost_model"]["slippage_bps"]
    assert fixed["costs"]["fx_friction_bps"] == report["cost_model"]["fx_bps"]
    assert fixed["costs"]["conversion_bps"] == fixed["monthly_fee"] == 0
    assert not fixed["deployment_admissible"]
    monthly = build_native_targets(
        inputs, NativeStrategyParameters(diagnostic_change="monthly"), context=context
    )
    assert all(
        (day.year, day.month)
        != (
            context.sessions[context.session_indexes[day] + 1].year,
            context.sessions[context.session_indexes[day] + 1].month,
        )
        for day in monthly.signal_dates
    )
    assert len(monthly.signal_dates) < len(default.signal_dates)


def test_exact_score_endpoints_prefix_and_missing_session(native) -> None:  # type: ignore[no-untyped-def]
    inputs, start, _ = native
    context = build_native_strategy_context(inputs)
    ranked, exclusions = diagnostic_momentum_rank(context, start, {"A"})
    index = context.session_indexes[start]
    expected = (
        context.prices[(context.sessions[index - 21], "A")]
        / context.prices[(context.sessions[index - 252], "A")]
        - 1
    )
    assert ranked[0].score == pytest.approx(expected)
    assert not exclusions
    prefix = replace(
        context, prices={key: value for key, value in context.prices.items() if key[0] <= start}
    )
    assert diagnostic_momentum_rank(prefix, start, {"A"}) == (ranked, exclusions)
    missing = dict(context.prices)
    del missing[(context.sessions[index - 100], "A")]
    assert not diagnostic_momentum_rank(replace(context, prices=missing), start, {"A"})[0]


def test_long_covariance_only_scales_down_and_spy_rule(native) -> None:  # type: ignore[no-untyped-def]
    inputs, start, _ = native
    context = build_native_strategy_context(inputs)
    weights = {"A": 0.25, "B": 0.25}
    reduced = diagnostic_dual_scale(context, start, weights, 0.001)
    assert 0 < reduced["A"] < weights["A"]
    assert reduced["A"] / weights["A"] == reduced["B"] / weights["B"]
    assert diagnostic_spy_ceiling(context, start, 0.02) == 0.98
    prices = dict(context.prices)
    prices[(start, context.benchmark_security_id)] = 1
    assert diagnostic_spy_ceiling(replace(context, prices=prices), start, 0.02) == 0
