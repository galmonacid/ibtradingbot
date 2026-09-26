"""Attribution preserves first-session costs, complete halt tails and currencies."""

from copy import deepcopy
from typing import Any

import pytest

from src.validation.v2_report import summarize_v2_run


def payload() -> dict[str, Any]:
    return {
        "initial_capital_gbp": 1000,
        "initial_capital_usd": 1250,
        "points": [
            {
                "date": "2027-01-04",
                "equity_gbp": 999,
                "equity_usd": 1248.75,
                "gross_exposure": 0.2,
                "regime": "on",
                "hard_halted": False,
                "soft_active": False,
            },
            {
                "date": "2027-01-05",
                "equity_gbp": 850,
                "equity_usd": 1062.5,
                "gross_exposure": 0.2,
                "regime": "off",
                "hard_halted": True,
                "soft_active": True,
            },
            {
                "date": "2027-01-06",
                "equity_gbp": 850,
                "equity_usd": 1062.5,
                "gross_exposure": 0,
                "regime": "off",
                "hard_halted": True,
                "soft_active": True,
            },
        ],
        "fills": [
            {
                "date": "2027-01-04",
                "shares": 2,
                "execution_price": 100,
                "gbp_per_usd": 0.8,
                "commission_gbp": 1,
                "commission_usd": 1.25,
                "slippage_gbp": 0.1,
                "slippage_usd": 0.125,
                "fx_friction_gbp": 0,
                "fx_friction_usd": 0,
                "side": "BUY",
                "reason": "monthly",
            }
        ],
        "conversions": [{"date": "2027-01-04", "fee_gbp": 0.2, "fee_usd": 0.25}],
        "fees": [{"date": "2027-01-06", "amount_gbp": 0.5}],
        "closed_lots": [
            {
                "security_id": "S",
                "entry": "2027-01-04",
                "exit": "2027-01-06",
                "basis_gbp": 160,
                "proceeds_gbp": 150,
                "basis_usd": 200,
                "proceeds_usd": 187.5,
            }
        ],
        "episodes": [{"security_id": "S", "entry": "2027-01-04", "exit": "2027-01-06"}],
    }


def test_report_accounts_first_session_costs_currencies_and_full_halt_tail() -> None:
    source = payload()
    original = deepcopy(source)
    report = summarize_v2_run(source)
    assert source == original
    assert report == summarize_v2_run(source)
    assert not report["admissible_for_qualification"]
    assert not report["ready_for_paper_trading"]
    assert report["currencies"]["gbp"]["net_total_return"] == pytest.approx(-0.15)
    assert report["currencies"]["gbp"]["buy_plus_sell_notional"] == 160
    assert report["currencies"]["usd"]["buy_plus_sell_notional"] == 200
    assert report["currencies"]["gbp"]["realized_profit_loss_by_year"] == {2027: -10}
    assert report["closed_fifo_lots"] == report["completed_position_episodes"] == 1
    assert report["mean_episode_holding_days"] == 2
    assert report["first_hard_halt"] == "2027-01-05"
    assert report["hard_halted_sessions"] == 2
    assert report["end"] == "2027-01-06"
    assert report["bootstrap"]["gbp"]["status"] == "available"
    assert report["bootstrap"]["gbp"]["iterations"] == 2000
    assert report["costs"]["gbp"] == {
        "commission": 1,
        "slippage": 0.1,
        "fill_fx_friction": 0,
        "conversion": 0.2,
        "account_fees": 0.5,
    }
    assert report["pre_halt_metrics"]["gbp"]["maximum_drawdown"] == pytest.approx(0.001)


def test_unavailable_bootstrap_and_bad_evidence_do_not_become_passes() -> None:
    source = payload()
    for point in source["points"]:
        point["regime"] = "on"
    report = summarize_v2_run(source)
    assert report["bootstrap"]["gbp"]["status"] == "unavailable"
    assert "two distinct regimes" in report["bootstrap"]["gbp"]["reason"]
    source["episodes"][0]["entry"] = "2026-12-31"
    with pytest.raises(ValueError, match="inside report"):
        summarize_v2_run(source)


def test_delisting_cash_disposition_is_not_a_trading_order_or_turnover() -> None:
    source = payload()
    disposition = dict(source["fills"][0], reason="delisting_recovery", side="sell")
    source["fills"].append(disposition)
    report = summarize_v2_run(source)
    assert report["orders"] == 1
    assert report["corporate_dispositions"] == 1
    assert report["currencies"]["gbp"]["buy_plus_sell_notional"] == 160
    assert report["closed_fifo_lots"] == report["completed_position_episodes"] == 1


def test_fixed_fill_gross_refunds_preserve_currency_and_do_not_reinvest() -> None:
    source = payload()
    # USD doubles relative to GBP after the first-day USD trading costs.
    source["points"][-1]["equity_usd"] = 531.25
    result = summarize_v2_run(source, include_bootstrap=False)
    gbp = result["currencies"]["gbp"]
    usd = result["currencies"]["usd"]
    assert gbp["gross_fixed_fill_terminal_nav"] == pytest.approx(850 + 0.7 + 1.375 * 1.6)
    assert usd["gross_fixed_fill_terminal_nav"] == pytest.approx(531.25 + 0.7 / 1.6 + 1.375)
    assert not gbp["concentration_evidence_admissible"]
    assert gbp["unallocated_account_profit"] == -140


def test_report_compacts_exclusions_by_reason_without_mutating_ledger() -> None:
    source = payload()
    source["exclusions"] = [
        {"date": "2027-01-04", "security_id": "A", "reason": "liquidity"},
        {"date": "2027-01-05", "security_id": "B", "reason": "liquidity"},
        {"date": "2027-01-06", "security_id": "C", "reason": "trend"},
    ]
    original = deepcopy(source)
    result = summarize_v2_run(source, include_bootstrap=False)
    assert source == original
    assert "exclusions" not in result
    assert result["exclusion_events"] == 3
    assert result["exclusion_counts_by_reason"] == {"liquidity": 2, "trend": 1}
    assert result["exclusion_detail_location"] == "content-bound scenario ledger"
