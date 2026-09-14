from __future__ import annotations

import math

from src.validation.gates import (
    DeploymentGateInputs,
    GateStatus,
    assess_deployment_gates,
)


def _passing_inputs(**overrides: object) -> DeploymentGateInputs:
    values: dict[str, object] = {
        "admissible_point_in_time_evidence": True,
        "out_of_sample_cagr": 0.08,
        "out_of_sample_sharpe": 0.8,
        "out_of_sample_maximum_drawdown": 0.15,
        "stressed_cagr": 0.06,
        "stressed_sharpe": 0.6,
        "closed_trades": 150,
        "realized_profit_loss_by_year": {2020: 34.0, 2021: 33.0, 2022: 33.0},
        "realized_profit_loss_by_stock": {
            "A": 20.0,
            "B": 20.0,
            "C": 20.0,
            "D": 20.0,
            "E": 20.0,
        },
        "nearby_parameters_economically_viable": True,
        "bootstrap_cagr_q05": 0.01,
        "bootstrap_sharpe_q05": 0.10,
        "bootstrap_maximum_drawdown_q95": 0.20,
    }
    values.update(overrides)
    return DeploymentGateInputs(**values)  # type: ignore[arg-type]


def test_all_gates_pass_at_inclusive_thresholds() -> None:
    assessment = assess_deployment_gates(_passing_inputs())

    assert assessment.ready_for_paper_trading
    assert len(assessment.gates) == 13
    assert all(gate.status is GateStatus.PASS for gate in assessment.gates)


def test_each_numeric_gate_fails_outside_threshold() -> None:
    cases = {
        "out_of_sample_cagr": 0.079,
        "out_of_sample_sharpe": 0.79,
        "out_of_sample_maximum_drawdown": 0.151,
        "stressed_cagr": 0.059,
        "stressed_sharpe": 0.59,
        "closed_trades": 149,
        "bootstrap_cagr_q05": -0.001,
        "bootstrap_sharpe_q05": -0.01,
        "bootstrap_maximum_drawdown_q95": 0.251,
    }
    for name, value in cases.items():
        assessment = assess_deployment_gates(_passing_inputs(**{name: value}))

        assert assessment.by_name()[name].status is GateStatus.FAIL
        assert not assessment.ready_for_paper_trading


def test_catastrophic_bootstrap_tail_prevents_readiness() -> None:
    assessment = assess_deployment_gates(
        _passing_inputs(
            bootstrap_cagr_q05=-0.40,
            bootstrap_sharpe_q05=-1.2,
            bootstrap_maximum_drawdown_q95=0.70,
        )
    )
    assert assessment.by_name()["bootstrap_cagr_q05"].status is GateStatus.FAIL
    assert assessment.by_name()["bootstrap_sharpe_q05"].status is GateStatus.FAIL
    assert assessment.by_name()["bootstrap_maximum_drawdown_q95"].status is GateStatus.FAIL
    assert not assessment.ready_for_paper_trading


def test_concentration_gates_fail_above_limits() -> None:
    assessment = assess_deployment_gates(
        _passing_inputs(
            realized_profit_loss_by_year={2020: 36.0, 2021: 32.0, 2022: 32.0},
            realized_profit_loss_by_stock={
                "A": 21.0,
                "B": 20.0,
                "C": 20.0,
                "D": 20.0,
                "E": 19.0,
            },
        )
    )

    assert assessment.by_name()["year_profit_concentration"].status is GateStatus.FAIL
    assert assessment.by_name()["stock_profit_concentration"].status is GateStatus.FAIL
    assert not assessment.ready_for_paper_trading


def test_losses_reduce_net_profit_and_can_make_concentration_fail() -> None:
    assessment = assess_deployment_gates(
        _passing_inputs(
            realized_profit_loss_by_year={2020: 50.0, 2021: 50.0, 2022: -20.0},
            realized_profit_loss_by_stock={
                "A": 20.0,
                "B": 20.0,
                "C": 20.0,
                "D": 20.0,
                "E": 20.0,
                "F": -10.0,
            },
        )
    )

    assert assessment.by_name()["year_profit_concentration"].observed == 0.625
    assert assessment.by_name()["year_profit_concentration"].status is GateStatus.FAIL
    assert assessment.by_name()["stock_profit_concentration"].status is GateStatus.FAIL


def test_zero_or_nonpositive_net_total_profit_is_not_assessable() -> None:
    zero = assess_deployment_gates(
        _passing_inputs(
            realized_profit_loss_by_year={2020: 0.0},
            realized_profit_loss_by_stock={"A": 0.0},
        )
    )
    nonpositive = assess_deployment_gates(
        _passing_inputs(
            realized_profit_loss_by_year={2020: 10.0, 2021: -10.0},
            realized_profit_loss_by_stock={"A": 5.0, "B": -6.0},
        )
    )

    assert zero.by_name()["year_profit_concentration"].status is GateStatus.NOT_ASSESSABLE
    assert zero.by_name()["stock_profit_concentration"].status is GateStatus.NOT_ASSESSABLE
    assert nonpositive.by_name()["year_profit_concentration"].status is GateStatus.NOT_ASSESSABLE
    assert nonpositive.by_name()["stock_profit_concentration"].status is GateStatus.NOT_ASSESSABLE
    assert not zero.ready_for_paper_trading
    assert not nonpositive.ready_for_paper_trading


def test_nonfinite_profit_loss_is_not_assessable() -> None:
    assessment = assess_deployment_gates(
        _passing_inputs(
            realized_profit_loss_by_year={2020: math.inf},
            realized_profit_loss_by_stock={"A": math.nan},
        )
    )

    assert assessment.by_name()["year_profit_concentration"].status is GateStatus.NOT_ASSESSABLE
    assert assessment.by_name()["stock_profit_concentration"].status is GateStatus.NOT_ASSESSABLE


def test_missing_and_nonfinite_metrics_are_not_assessable() -> None:
    assessment = assess_deployment_gates(
        _passing_inputs(out_of_sample_cagr=None, stressed_sharpe=math.inf, closed_trades=None)
    )

    assert assessment.by_name()["out_of_sample_cagr"].status is GateStatus.NOT_ASSESSABLE
    assert assessment.by_name()["stressed_sharpe"].status is GateStatus.NOT_ASSESSABLE
    assert assessment.by_name()["closed_trades"].status is GateStatus.NOT_ASSESSABLE
    assert not assessment.ready_for_paper_trading


def test_admissibility_and_parameter_robustness_are_mandatory() -> None:
    inadmissible = assess_deployment_gates(_passing_inputs(admissible_point_in_time_evidence=False))
    fragile = assess_deployment_gates(_passing_inputs(nearby_parameters_economically_viable=False))
    unknown = assess_deployment_gates(_passing_inputs(nearby_parameters_economically_viable=None))

    assert inadmissible.by_name()["admissible_point_in_time_evidence"].status is GateStatus.FAIL
    assert fragile.by_name()["parameter_robustness"].status is GateStatus.FAIL
    assert unknown.by_name()["parameter_robustness"].status is GateStatus.NOT_ASSESSABLE
    assert not inadmissible.ready_for_paper_trading
    assert not fragile.ready_for_paper_trading
    assert not unknown.ready_for_paper_trading
