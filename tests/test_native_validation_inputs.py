from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from src.backtest.costs import CostModel
from src.data.canonical_historical import (
    CanonicalDailyBar,
    CanonicalSourceProvenance,
    write_canonical_parquet,
)
from src.data.execution_audit import audit_bound_native_backtest_executions
from src.data.trusted_historical import SecurityIdentityInterval, SecurityMembershipInterval
from src.validation.native_execution import (
    NativeBacktestRun,
    NativeExecutionError,
    run_native_backtest,
)
from src.validation.native_inputs import (
    NativeValidationInputError,
    NativeValidationInputs,
    create_native_validation_inputs,
)
from src.validation.native_report import (
    build_native_validation_report,
)
from src.validation.native_strategy import (
    NativeStrategyError,
    build_native_regimes,
    build_native_strategy_context,
    build_native_targets,
    compose_native_targets,
    select_native_targets,
)
from src.validation.native_workflow import (
    NativeWorkflowError,
    _validate_selected_execution_costs,
)

pytest.importorskip("pyarrow")

ROOT = Path(__file__).resolve().parents[1]


def test_path_factory_binds_verified_dataset_config_spec_and_source_tree(tmp_path: Path) -> None:
    canonical = write_canonical_parquet(
        tmp_path / "canonical",
        bars=(
            CanonicalDailyBar(
                "SEC-SPY", "SPY", date(2020, 1, 2), 100, 101, 99, 100, 100,
                1_000, 100, 101, 99, 1_000,
            ),
            CanonicalDailyBar(
                "SEC-SPY", "SPY", date(2020, 1, 3), 101, 102, 100, 101, 101,
                1_000, 101, 102, 100, 1_000,
            ),
            CanonicalDailyBar(
                "SEC-SPY", "SPY", date(2020, 1, 6), 102, 103, 101, 102, 102,
                1_000, 102, 103, 101, 1_000,
            ),
        ),
        identities=(SecurityIdentityInterval("SEC-SPY", "SPY", date(2020, 1, 1), None),),
        memberships=(
            SecurityMembershipInterval("pit-v1", "SEC-SPY", date(2020, 1, 1), None),
        ),
        actions=(),
        source_provenance=(
            CanonicalSourceProvenance(
                "test-source", "git", "a" * 64, "2026-09-16T00:00:00+00:00", "MIT",
                repository_url="https://example.test/source", commit_sha="b" * 40,
            ),
        ),
        transformation_version="test-v1",
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        (ROOT / "config.example.yaml")
        .read_text(encoding="utf-8")
        .replace("source: fixed_seed", "source: trusted_canonical"),
        encoding="utf-8",
    )
    specification = tmp_path / "validation.md"
    specification.write_text("# Exact validation specification\n", encoding="utf-8")

    result = create_native_validation_inputs(
        canonical_manifest_path=canonical.manifest_path,
        config_path=config,
        validation_spec_path=specification,
        repository_root=ROOT,
        strategy_version="phase3-native-v1",
    )

    assert result.identity.canonical_manifest_sha256 == result.canonical.manifest_sha256
    assert result.identity.config_sha256 == result.config.sha256
    assert result.identity.strategy_definition_sha256
    assert result.strategy_definition_files

    context = build_native_strategy_context(result)
    assert context.raw_closes[(date(2020, 1, 2), "SEC-SPY")] == 100
    targets = build_native_targets(result)
    cached_targets = build_native_targets(result, context=context)
    assert cached_targets.target_sha256 == targets.target_sha256
    assert build_native_regimes(result, context=context) == build_native_regimes(result)
    selected_targets = select_native_targets(result, targets, targets.signal_dates)
    assert selected_targets.target_sha256 == targets.target_sha256
    composed_targets = compose_native_targets(
        result, ((targets, targets.signal_dates),), parameters=targets.parameters
    )
    assert composed_targets.target_sha256 == targets.target_sha256
    with pytest.raises(NativeStrategyError, match="duplicate signal dates"):
        compose_native_targets(
            result,
            ((targets, targets.signal_dates), (targets, targets.signal_dates)),
        )
    with pytest.raises(NativeStrategyError, match="different validation run"):
        build_native_targets(
            result,
            context=replace(context, validation_run_id="not-this-run"),
        )
    baseline = run_native_backtest(result, scenario="baseline", targets=targets)
    stressed = run_native_backtest(result, scenario="stressed", targets=targets)
    assert baseline.validation_run_id == result.identity.validation_run_id
    assert baseline.market_input_sha256 == stressed.market_input_sha256
    assert baseline.target_sha256 == stressed.target_sha256
    assert baseline.result.execution_trace.sha256 == stressed.result.execution_trace.sha256
    bounded = run_native_backtest(
        result,
        scenario="baseline",
        targets=targets,
        window_start=date(2020, 1, 3),
        window_end=date(2020, 1, 6),
    )
    assert tuple(point.date for point in bounded.result.equity_curve) == (
        date(2020, 1, 2),
        date(2020, 1, 3),
        date(2020, 1, 6),
    )
    assert all(trade.date <= date(2020, 1, 6) for trade in bounded.result.trades)
    baseline_parameters = replace(
        targets.parameters,
        slippage_bps_each_side=result.config.transaction_costs[1],
    )
    _validate_selected_execution_costs({0: baseline_parameters}, result)
    with pytest.raises(NativeWorkflowError, match="fold-varying costs"):
        _validate_selected_execution_costs(
            {0: replace(baseline_parameters, commission_multiplier=2.0)}, result
        )
    audit = audit_bound_native_backtest_executions(
        result.identity,
        sessions=tuple(
            sorted(
                {bar.date for bar in result.canonical.bars if bar.symbol == result.config.benchmark}
            )
        ),
        baseline_run=baseline,
        stressed_run=stressed,
        baseline_costs=CostModel(*result.config.transaction_costs),
        stressed_costs=CostModel(*result.config.stress_transaction_costs),
    )
    assert audit.passed

    with pytest.raises(NativeWorkflowError, match="complete fold"):
        build_native_validation_report(result)

    targets.targets_by_signal_date[date(2020, 1, 3)] = {"SEC-SPY": 0.3}
    with pytest.raises(NativeExecutionError, match="attested hash"):
        run_native_backtest(result, scenario="baseline", targets=targets)

    with pytest.raises(NativeExecutionError, match="native executor"):
        NativeBacktestRun("a" * 64, "baseline", "b" * 64, "c" * 64, baseline.result)


def test_native_inputs_cannot_be_caller_constructed() -> None:
    with pytest.raises(NativeValidationInputError, match="path-derived factory"):
        NativeValidationInputs(
            object(), object(), Path("spec"), (), object(), False, None, None, None, None
        )  # type: ignore[arg-type]
