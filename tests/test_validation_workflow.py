from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from src.data.execution_audit import ExecutionAuditRecord, audit_historical_executions
from src.data.membership_audit import (
    ConstituentChange,
    IndependentEvidence,
    audit_constituent_changes,
)
from src.data.semantic_certification import SemanticCertificationReport
from src.validation.ablation import (
    AblationContext,
    AblationEvaluation,
    AblationMetrics,
    AblationScenario,
)
from src.validation.engine import EvaluationContext, SegmentEvaluation, WalkForwardEvaluation
from src.validation.gates import GateStatus
from src.validation.sensitivity import ParameterSet, parameter_grid
from src.validation.workflow import (
    RealizedTradeEvidence,
    TrustedProducerEvidence,
    WorkflowEvidence,
    issue_trusted_producer_evidence,
    run_validation_workflow,
)


def _sessions() -> tuple[date, ...]:
    start = date(2007, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(14 * 366))


def _segment_evaluator(
    window: EvaluationContext, parameters: ParameterSet, segment: str
) -> SegmentEvaluation:
    positions = int(parameters.as_dict()["positions"])
    if segment == "validation":
        return SegmentEvaluation({3: 1.0, 4: 0.95}[positions])
    returns = tuple(
        (day, 0.001 if index % 3 else -0.0005) for index, day in enumerate(window.evaluation_dates)
    )
    return SegmentEvaluation(0.5, returns)


def _evidence(walk_forward: WalkForwardEvaluation) -> WorkflowEvidence:
    count = len(walk_forward.stitched_test_observations)
    regimes = tuple("on" if index % 40 < 20 else "off" for index in range(count))
    dates = tuple(day for day, _value in walk_forward.stitched_test_observations)
    trades = tuple(
        RealizedTradeEvidence(
            f"lot-{index}",
            dates[max(0, close_index - 1)],
            dates[close_index],
            str(index % 6),
            100.0,
            101.0,
        )
        for index in range(200)
        for close_index in (1 + index * (len(dates) - 1) // 200,)
    )
    returns = tuple(value for _day, value in walk_forward.stitched_test_observations)
    return WorkflowEvidence(regimes, returns, trades)


def _membership_audit():
    events = tuple(
        ConstituentChange(f"e-{index}", f"s-{index}", f"S{index}", "add", date(2000, 1, 1))
        for index in range(50)
    )
    evidence = tuple(
        IndependentEvidence(
            source,
            event.symbol,
            event.action,
            event.effective_date,
        )
        for event in events
        for source in ("qa-one", "qa-two")
    )
    return audit_constituent_changes(events, evidence, sample_size=50, seed=1)


def _trusted_evidence():
    audit = _membership_audit()
    semantics = SemanticCertificationReport(True, 1, 0, 1, 0, ())
    execution = audit_historical_executions(
        (date(2020, 1, 2), date(2020, 1, 3)),
        (
            ExecutionAuditRecord(
                date(2020, 1, 2),
                date(2020, 1, 3),
                "SEC",
                1_000.0,
                10.0,
                0.35,
                0.70,
                5.0,
                10.0,
            ),
        ),
    )
    return issue_trusted_producer_evidence(
        producer_id="historical-producer",
        producer_version="v1",
        dataset_manifest_sha256="a" * 64,
        membership_audit=audit,
        semantic_report=semantics,
        execution_audit=execution,
    )


def test_workflow_combines_all_stages_and_is_machine_serializable() -> None:
    sessions = _sessions()
    ablation_calls: list[str] = []

    def ablation(scenario: AblationScenario, context: AblationContext) -> AblationEvaluation:
        name = scenario.name
        ablation_calls.append(name)
        return AblationEvaluation(context, AblationMetrics.from_mapping({"sharpe": 0.8}))

    result = run_validation_workflow(
        sessions,
        parameter_grid({"positions": (3, 4)}),
        {"positions": (3, 4)},
        _segment_evaluator,
        _evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=True,
        complete_data_coverage=True,
        ablation_evaluator=ablation,
        ablation_data_id="pit-v1",
        ablation_cost_id="stress-v1",
        bootstrap_seed=9,
        trusted_producer_evidence=_trusted_evidence(),
    )
    assert result.windows
    assert result.walk_forward.stitched_test_observations
    assert len(result.bootstrap.daily.cagr.samples) == 2_000
    assert result.gates.ready_for_paper_trading
    assert result.ablations is not None
    assert tuple(item.scenario.name for item in result.ablations.results) == tuple(ablation_calls)
    json.dumps(result.as_dict(), sort_keys=True, allow_nan=False)


def test_trade_bootstrap_is_invariant_to_caller_order() -> None:
    sessions = _sessions()

    def reversed_evidence(result: WalkForwardEvaluation) -> WorkflowEvidence:
        evidence = _evidence(result)
        return WorkflowEvidence(
            evidence.regimes,
            evidence.stressed_oos_returns,
            tuple(reversed(evidence.realized_trades)),
        )

    candidates = parameter_grid({"positions": (3, 4)})
    axes = {"positions": (3, 4)}
    chronological = run_validation_workflow(
        sessions,
        candidates,
        axes,
        _segment_evaluator,
        _evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=False,
        complete_data_coverage=False,
        bootstrap_seed=17,
    )
    reversed_result = run_validation_workflow(
        sessions,
        candidates,
        axes,
        _segment_evaluator,
        reversed_evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=False,
        complete_data_coverage=False,
        bootstrap_seed=17,
    )
    assert chronological.bootstrap.mean_trade_return == reversed_result.bootstrap.mean_trade_return


def test_trusted_evidence_cannot_be_constructed_directly() -> None:
    with pytest.raises(ValueError, match="issued from concrete reports"):
        TrustedProducerEvidence(
            "producer",
            "v1",
            True,
            True,
            True,
            True,
            True,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            object(),
        )


def test_trusted_evidence_factory_binds_passing_reports_and_hashes() -> None:
    evidence = _trusted_evidence()
    assert evidence.semantically_validated
    assert evidence.dataset_manifest_sha256 == "a" * 64
    assert len(evidence.membership_audit_sha256) == 64
    assert len(evidence.semantic_report_sha256) == 64
    assert len(evidence.execution_audit_sha256) == 64

    with pytest.raises(ValueError, match="canonical SHA-256"):
        issue_trusted_producer_evidence(
            producer_id="historical-producer",
            producer_version="v1",
            dataset_manifest_sha256="not-a-hash",
            membership_audit=_membership_audit(),
            semantic_report=SemanticCertificationReport(True, 1, 0, 1, 0, ()),
            execution_audit=audit_historical_executions(
                (date(2020, 1, 2), date(2020, 1, 3)),
                (
                    ExecutionAuditRecord(
                        date(2020, 1, 2), date(2020, 1, 3), "SEC", 1, 1, 0.35, 0.7, 5, 10
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="passing semantic report"):
        issue_trusted_producer_evidence(
            producer_id="historical-producer",
            producer_version="v1",
            dataset_manifest_sha256="a" * 64,
            membership_audit=_membership_audit(),
            semantic_report=SemanticCertificationReport(False, 1, 0, 1, 0, ()),
            execution_audit=audit_historical_executions(
                (date(2020, 1, 2), date(2020, 1, 3)),
                (
                    ExecutionAuditRecord(
                        date(2020, 1, 2), date(2020, 1, 3), "SEC", 1, 1, 0.35, 0.7, 5, 10
                    ),
                ),
            ),
        )


def test_legacy_admissibility_booleans_cannot_self_certify() -> None:
    sessions = _sessions()
    result = run_validation_workflow(
        sessions,
        parameter_grid({"positions": (3, 4)}),
        {"positions": (3, 4)},
        _segment_evaluator,
        _evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=True,
        complete_data_coverage=True,
    )
    assert not result.admissible_evidence
    assert not result.gates.ready_for_paper_trading


def test_workflow_rejects_trade_opened_outside_oos() -> None:
    sessions = _sessions()

    def boundary_crossing_evidence(result: WalkForwardEvaluation) -> WorkflowEvidence:
        evidence = _evidence(result)
        first_date = result.stitched_test_observations[0][0]
        trade = RealizedTradeEvidence(
            "boundary-lot", first_date - timedelta(days=1), first_date, "ABC", 100.0, 101.0
        )
        return WorkflowEvidence(evidence.regimes, evidence.stressed_oos_returns, (trade,))

    with pytest.raises(ValueError, match="open and close"):
        run_validation_workflow(
            sessions,
            parameter_grid({"positions": (3, 4)}),
            {"positions": (3, 4)},
            _segment_evaluator,
            boundary_crossing_evidence,
            verified_complete_through=sessions[-1],
            point_in_time_universe=True,
            complete_data_coverage=True,
        )


@pytest.mark.parametrize(("pit", "coverage"), [(False, True), (True, False), (False, False)])
def test_workflow_cannot_override_false_admissibility(pit: bool, coverage: bool) -> None:
    sessions = _sessions()
    result = run_validation_workflow(
        sessions,
        parameter_grid({"positions": (3, 4)}),
        {"positions": (3, 4)},
        _segment_evaluator,
        _evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=pit,
        complete_data_coverage=coverage,
    )
    gate = result.gates.by_name()["admissible_point_in_time_evidence"]
    assert not result.admissible_evidence
    assert gate.status is GateStatus.FAIL
    assert not result.gates.ready_for_paper_trading


def test_workflow_rejects_misaligned_regime_evidence() -> None:
    sessions = _sessions()

    def bad_evidence(result: WalkForwardEvaluation) -> WorkflowEvidence:
        evidence = _evidence(result)
        return WorkflowEvidence(
            evidence.regimes[:-1],
            evidence.stressed_oos_returns,
            evidence.realized_trades,
        )

    with pytest.raises(ValueError, match="align"):
        run_validation_workflow(
            sessions,
            parameter_grid({"positions": (3, 4)}),
            {"positions": (3, 4)},
            _segment_evaluator,
            bad_evidence,
            verified_complete_through=sessions[-1],
            point_in_time_universe=True,
            complete_data_coverage=True,
        )


def test_supported_but_economically_bad_plateau_fails_robustness_gate() -> None:
    sessions = _sessions()

    def bad_scores(
        context: EvaluationContext, parameters: ParameterSet, segment: str
    ) -> SegmentEvaluation:
        if segment == "validation":
            return SegmentEvaluation(-10.0)
        return SegmentEvaluation(0.0, tuple((day, 0.0) for day in context.evaluation_dates))

    result = run_validation_workflow(
        sessions,
        parameter_grid({"positions": (3, 4)}),
        {"positions": (3, 4)},
        bad_scores,
        _evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=True,
        complete_data_coverage=True,
    )
    assert result.gates.by_name()["parameter_robustness"].status is GateStatus.FAIL


def test_economically_bad_supporting_neighbour_fails_robustness_gate() -> None:
    sessions = _sessions()

    def scores(
        context: EvaluationContext, parameters: ParameterSet, segment: str
    ) -> SegmentEvaluation:
        if segment == "validation":
            score = 0.61 if parameters.as_dict()["positions"] == 3 else 0.49
            return SegmentEvaluation(score)
        return SegmentEvaluation(0.0, tuple((day, 0.0) for day in context.evaluation_dates))

    result = run_validation_workflow(
        sessions,
        parameter_grid({"positions": (3, 4)}),
        {"positions": (3, 4)},
        scores,
        _evidence,
        verified_complete_through=sessions[-1],
        point_in_time_universe=True,
        complete_data_coverage=True,
    )
    assert result.gates.by_name()["parameter_robustness"].status is GateStatus.FAIL
