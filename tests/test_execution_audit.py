from datetime import date

import pytest

from src.data.execution_audit import (
    ExecutionAuditError,
    ExecutionAuditRecord,
    ExecutionAuditReport,
    audit_historical_executions,
)

SESSIONS = (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6))


def _record(**changes: object) -> ExecutionAuditRecord:
    values: dict[str, object] = {
        "decision_session": SESSIONS[0],
        "fill_session": SESSIONS[1],
        "security_id": "SEC",
        "notional": 1_000.0,
        "fill_price": 10.0,
        "baseline_commission": 0.35,
        "stressed_commission": 0.70,
        "baseline_slippage_bps": 5.0,
        "stressed_slippage_bps": 10.0,
    }
    values.update(changes)
    return ExecutionAuditRecord(**values)  # type: ignore[arg-type]


def test_concrete_next_session_and_cost_stress_pass() -> None:
    report = audit_historical_executions(SESSIONS, (_record(),))
    assert report.passed
    assert report.record_count == 1


def test_late_fill_and_weak_stress_fail() -> None:
    report = audit_historical_executions(
        SESSIONS,
        (_record(fill_session=SESSIONS[2], stressed_commission=0.69, stressed_slippage_bps=9.9),),
    )
    assert {finding.code for finding in report.findings} == {
        "NOT_NEXT_SESSION",
        "COMMISSION_STRESS_TOO_LOW",
        "SLIPPAGE_STRESS_TOO_LOW",
    }


def test_empty_or_duplicate_evidence_is_rejected() -> None:
    with pytest.raises(ExecutionAuditError, match="concrete"):
        audit_historical_executions(SESSIONS, ())
    with pytest.raises(ExecutionAuditError, match="duplicate"):
        audit_historical_executions(SESSIONS, (_record(), _record()))
    with pytest.raises(ExecutionAuditError, match="concrete auditor"):
        ExecutionAuditReport(1, (), True)
