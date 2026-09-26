from copy import deepcopy

import pytest
from test_v2_backtest import market_fixture, run

from src.backtest.v2_execution import FeeModel
from src.config.v2 import V2Config
from src.validation.v2_audit import audit_v2_ledger


def test_reconciliation_rebuilds_cash_shares_and_nav_from_canonical_inputs() -> None:
    market, fx, start, end = market_fixture()
    ledger = run(market, fx, start, end)
    result = audit_v2_ledger(
        ledger,
        market,
        fx,
        V2Config(),
        FeeModel(),
        initial_capital_gbp=3000,
        start=start,
        end=end,
        monthly_fee_gbp=0,
    )
    assert result.passed, result.findings
    assert result.reconciled_sessions == len(ledger["points"])
    assert result.trading_fills == len(ledger["fills"])


@pytest.mark.parametrize(
    "mutation",
    [
        "nav",
        "holding",
        "commission",
        "duplicate",
        "missing",
        "future",
        "episodes",
        "lots",
        "usd_capital",
        "decision_reason",
        "decision_amendment",
    ],
)
def test_ledger_mutations_fail_independent_reconciliation(mutation: str) -> None:
    market, fx, start, end = market_fixture()
    ledger = deepcopy(run(market, fx, start, end))
    if mutation == "nav":
        ledger["points"][-1]["equity_gbp"] += 10
    elif mutation == "holding":
        ledger["points"][1]["holdings"]["A"] += 1
    elif mutation == "commission":
        ledger["fills"][0]["commission_usd"] = 0
    elif mutation == "duplicate":
        ledger["fills"].insert(0, dict(ledger["fills"][0]))
    elif mutation == "missing":
        ledger["fills"].pop(0)
    elif mutation == "usd_capital":
        ledger["initial_capital_usd"] *= 2
    elif mutation.startswith("decision_"):
        decision = next(d for d in ledger["decisions"] if d["status"] == "applied")
        if mutation == "decision_reason":
            decision["reason"] = "invented"
        else:
            decision["amended_at"] = start.isoformat()
    elif mutation == "episodes":
        ledger["episodes"].append(
            dict(security_id="invented", entry=start.isoformat(), exit=end.isoformat())
        )
    elif mutation == "lots":
        ledger["closed_lots"].append(
            dict(
                security_id="invented",
                entry=start.isoformat(),
                exit=end.isoformat(),
                basis_gbp=1,
                basis_usd=1,
                proceeds_gbp=100,
                proceeds_usd=100,
            )
        )
    else:
        ledger["fills"][0]["signal_date"] = ledger["fills"][0]["date"]
    result = audit_v2_ledger(
        ledger,
        market,
        fx,
        V2Config(),
        FeeModel(),
        initial_capital_gbp=3000,
        start=start,
        end=end,
        monthly_fee_gbp=0,
    )
    assert not result.passed
    assert result.findings
