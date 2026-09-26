"""Raw-price, small-account and two-currency research execution tests."""

from datetime import date

import pytest

from src.backtest.v2_execution import Account, FeeModel, execute_plan

SIGNAL = date(2026, 1, 30)
EXECUTION = date(2026, 2, 2)


def test_fractional_small_account_postcost_caps_and_conservation() -> None:
    account = Account(1000, 0)
    result = execute_plan(
        account,
        dict.fromkeys("ABCD", 0.245),
        dict.fromkeys("ABCD", 100.0),
        0.8,
        fractional=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert len(result.fills) == 4
    assert all(fill.side == "buy" for fill in result.fills)
    assert sum(result.accepted_weights.values()) <= 0.98 + 1e-12
    assert max(result.accepted_weights.values()) <= 0.3
    assert result.account.cash_usd == pytest.approx(0)
    nav = result.account.cash_gbp + sum(result.account.holdings.values()) * 100 * 0.8
    fees = sum(f.total_cost_gbp for f in result.fills) + sum(c.fee_gbp for c in result.conversions)
    assert nav == pytest.approx(1000 - fees)
    assert result.account.cash_gbp >= nav * 0.02 - 1e-9
    assert account == Account(1000, 0)


@pytest.mark.parametrize("capital", [1000, 3000])
def test_whole_share_rounding_leaves_cash(capital: int) -> None:
    result = execute_plan(
        Account(capital, 0),
        dict.fromkeys("ABCD", 0.245),
        dict.fromkeys("ABCD", 101.0),
        0.8,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert all(q == int(q) for q in result.account.holdings.values())
    assert sum(result.accepted_weights.values()) <= 0.98


def test_small_buy_skipped_without_roundup_or_redistribution() -> None:
    result = execute_plan(
        Account(1000, 0),
        {"A": 0.1, "B": 0.3},
        {"A": 100.0, "B": 100.0},
        0.8,
        fractional=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert "A" not in result.account.holdings
    assert result.skips[0].symbol == "A"
    assert result.account.holdings["B"] < 3.75


def test_tiny_mandatory_sell_bypasses_economic_minimum_and_sweeps_gbp() -> None:
    account = Account(1000, 0, {"A": 0.01})
    result = execute_plan(
        account,
        {},
        {"A": 100.0},
        0.8,
        fractional=True,
        mandatory_ids=["A"],
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert result.fills[0].shares == 0.01
    assert result.fills[0].mandatory
    assert result.account.holdings == {}
    assert result.account.cash_usd == 0
    assert result.conversions[0].direction == "GBP_TO_USD"  # Fees exceed sale proceeds.


def test_unsupported_fractional_residual_rejects_atomically() -> None:
    account = Account(1000, 0, {"A": 0.01})
    result = execute_plan(
        account, {}, {"A": 100.0}, 0.8, signal_date=SIGNAL, execution_date=EXECUTION
    )
    assert not result.succeeded
    assert result.account == account
    assert not result.fills and not result.conversions
    assert result.failure and "fractional" in result.failure


def test_sell_before_buy_and_costs_in_both_currencies() -> None:
    result = execute_plan(
        Account(300, 0, {"Z": 10}),
        {"A": 0.3},
        {"Z": 100.0, "A": 100.0},
        0.8,
        fractional=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert [f.side for f in result.fills] == ["sell", "buy"]
    assert [c.direction for c in result.conversions] == ["USD_TO_GBP", "GBP_TO_USD"]
    for fill in result.fills:
        assert fill.total_cost_gbp == pytest.approx(fill.total_cost_usd * 0.8)
        assert fill.fx_friction_usd > 0
    assert all(c.fee_usd > 0 for c in result.conversions)


def test_unpaid_dividends_count_nav_but_are_not_spendable() -> None:
    account = Account(0, 0, {}, receivables_usd=1000)
    result = execute_plan(
        account,
        {"A": 0.3},
        {"A": 100.0},
        0.8,
        fractional=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert not result.succeeded
    assert result.account == account
    account = Account(1000, 0, {}, receivables_usd=10)
    result = execute_plan(
        account,
        {"A": 0.3},
        {"A": 100.0},
        0.8,
        fractional=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert result.account.receivables_usd == 10


def test_missing_held_price_blocks_all_orders_without_fabricating_exit() -> None:
    account = Account(1000, 0, {"Z": 10})
    result = execute_plan(
        account, {"A": 0.3}, {"A": 100.0}, 0.8, signal_date=SIGNAL, execution_date=EXECUTION
    )
    assert not result.succeeded
    assert result.account == account and not result.fills


def test_same_day_execution_fails() -> None:
    result = execute_plan(
        Account(1000, 0), {"A": 0.3}, {"A": 100.0}, 0.8, signal_date=SIGNAL, execution_date=SIGNAL
    )
    assert not result.succeeded


def test_skipped_discretionary_sell_cannot_leave_postcost_cap_violation() -> None:
    # A small optional trim cannot waive the name cap even when other buys execute.
    account = Account(700, 0, {"A": 3.75})
    result = execute_plan(
        account,
        {"A": 0.29, "B": 0.2},
        {"A": 100.0, "B": 100.0},
        0.8,
        fractional=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert not result.succeeded
    assert result.account == account and not result.fills
    required = execute_plan(
        account,
        {"A": 0.29, "B": 0.2},
        {"A": 100.0, "B": 100.0},
        0.8,
        fractional=True,
        mandatory_ids=["A"],
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert required.succeeded, required.failure


def test_cost_stress_and_commission_floor_cannot_be_disabled() -> None:
    result = execute_plan(
        Account(1000, 0),
        {"A": 0.3},
        {"A": 100.0},
        0.8,
        costs=FeeModel(commission_min_usd=0.1),
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert not result.succeeded


def test_zero_holdings_require_no_price() -> None:
    result = execute_plan(
        Account(1000, 0, {"A": 0}), {}, {}, 0.8, signal_date=SIGNAL, execution_date=EXECUTION
    )
    assert result.succeeded


def test_risk_only_plan_never_buys_after_overnight_relative_price_move() -> None:
    account = Account(800, 0, {"A": 5, "B": 5})
    result = execute_plan(
        account,
        {"A": 0.15, "B": 0.15},
        {"A": 50.0, "B": 100.0},
        0.8,
        fractional=True,
        reductions_only=True,
        mandatory_ids=["A", "B"],
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert all(fill.side == "sell" for fill in result.fills)
    assert all(q <= account.holdings[s] for s, q in result.account.holdings.items())


def test_public_execution_boundary_preserves_economic_order_minimum() -> None:
    result = execute_plan(
        Account(1000, 0),
        {"A": 0.1},
        {"A": 100.0},
        0.8,
        min_order_gbp=1,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert not result.succeeded
    assert not result.fills


def test_entry_rounding_to_zero_has_an_explicit_skip_reason() -> None:
    result = execute_plan(
        Account(1000, 0),
        {"A": 0.2},
        {"A": 1000.0},
        0.8,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded and not result.fills
    assert [(skip.symbol, skip.reason) for skip in result.skips] == [
        ("A", "rounded_below_one_share")
    ]


@pytest.mark.parametrize("residual_id", ["A", "Z"])
def test_funded_liquidation_does_not_depend_on_identity_sort(residual_id: str) -> None:
    account = Account(0, 0, {residual_id: 0.001, "B": 10})
    result = execute_plan(
        account,
        {},
        {residual_id: 100.0, "B": 100.0},
        0.8,
        fractional=True,
        mandatory_ids=[residual_id, "B"],
        reductions_only=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert result.succeeded, result.failure
    assert [fill.symbol for fill in result.fills] == ["B", residual_id]
    assert result.account.holdings == {}
    assert result.account.cash_usd == 0
    assert result.account.cash_gbp == pytest.approx(797.4403839360061)
    assert account.cash_gbp == account.cash_usd == 0  # Original immutable ledger preserved.


def test_unfunded_tiny_liquidation_cannot_borrow_sale_fees() -> None:
    account = Account(0, 0, {"A": 0.001})
    result = execute_plan(
        account,
        {},
        {"A": 100.0},
        0.8,
        fractional=True,
        mandatory_ids=["A"],
        reductions_only=True,
        signal_date=SIGNAL,
        execution_date=EXECUTION,
    )
    assert not result.succeeded
    assert result.failure == "insufficient cash for mandatory sale fees"
    assert result.account == account and not result.fills
