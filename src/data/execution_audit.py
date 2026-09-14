"""Concrete causal-timing and stressed-cost audit for historical executions."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date


class ExecutionAuditError(ValueError):
    """Raised when execution evidence is malformed or incomplete."""


_EXECUTION_AUDIT_ATTESTATION = object()


@dataclass(frozen=True, order=True)
class ExecutionAuditRecord:
    decision_session: date
    fill_session: date
    security_id: str
    notional: float
    fill_price: float
    baseline_commission: float
    stressed_commission: float
    baseline_slippage_bps: float
    stressed_slippage_bps: float


@dataclass(frozen=True, order=True)
class ExecutionAuditFinding:
    code: str
    security_id: str
    decision_session: date
    detail: str


@dataclass(frozen=True)
class ExecutionAuditReport:
    record_count: int
    findings: tuple[ExecutionAuditFinding, ...]
    passed: bool
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _EXECUTION_AUDIT_ATTESTATION:
            raise ExecutionAuditError("execution reports must be issued by the concrete auditor")

    def to_json(self) -> str:
        payload = {key: value for key, value in asdict(self).items() if key != "_attestation"}
        return json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))


def audit_historical_executions(
    sessions: tuple[date, ...], records: tuple[ExecutionAuditRecord, ...]
) -> ExecutionAuditReport:
    """Require each decision to fill on the next session under the documented cost stress."""
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ExecutionAuditError("execution audit sessions must be sorted and unique")
    if not records:
        raise ExecutionAuditError("execution audit requires concrete fill records")
    session_index = {day: index for index, day in enumerate(sessions)}
    keys: set[tuple[str, date, date]] = set()
    findings: list[ExecutionAuditFinding] = []
    for row in records:
        key = (row.security_id, row.decision_session, row.fill_session)
        if key in keys:
            raise ExecutionAuditError("duplicate execution audit record")
        keys.add(key)
        numbers = (
            row.notional,
            row.fill_price,
            row.baseline_commission,
            row.stressed_commission,
            row.baseline_slippage_bps,
            row.stressed_slippage_bps,
        )
        if (
            not row.security_id.strip()
            or any(not math.isfinite(value) for value in numbers)
            or row.notional <= 0
            or row.fill_price <= 0
            or min(numbers[2:]) < 0
        ):
            raise ExecutionAuditError("execution audit record has invalid economics")
        decision_index = session_index.get(row.decision_session)
        expected_fill = (
            sessions[decision_index + 1]
            if decision_index is not None and decision_index + 1 < len(sessions)
            else None
        )
        if row.fill_session != expected_fill:
            findings.append(
                ExecutionAuditFinding(
                    "NOT_NEXT_SESSION",
                    row.security_id,
                    row.decision_session,
                    f"expected {expected_fill}; observed {row.fill_session}",
                )
            )
        if row.stressed_commission + 1e-12 < 2.0 * row.baseline_commission:
            findings.append(
                ExecutionAuditFinding(
                    "COMMISSION_STRESS_TOO_LOW",
                    row.security_id,
                    row.decision_session,
                    "stressed commission must be at least 2x baseline",
                )
            )
        if row.stressed_slippage_bps + 1e-12 < max(10.0, 2.0 * row.baseline_slippage_bps):
            findings.append(
                ExecutionAuditFinding(
                    "SLIPPAGE_STRESS_TOO_LOW",
                    row.security_id,
                    row.decision_session,
                    "stressed slippage must be at least 10 bps and 2x baseline",
                )
            )
    ordered = tuple(sorted(findings))
    return ExecutionAuditReport(len(records), ordered, not ordered, _EXECUTION_AUDIT_ATTESTATION)
