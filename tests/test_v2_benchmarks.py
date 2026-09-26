from copy import deepcopy
from dataclasses import replace

import pytest
from test_v2_backtest import market_fixture

from src.config.v2 import V2Config
from src.validation.v2_benchmarks import run_v2_benchmarks


def test_references_are_causal_costed_and_do_not_relax_strategy_caps() -> None:
    market, fx, start, end = market_fixture()
    result = run_v2_benchmarks(
        market, fx, V2Config(), start=start, end=end, initial_capital_gbp=3000, monthly_fee_gbp=0
    )
    assert set(result) == {"cash", "spy_buy_hold", "spy_risk_budget"}
    assert all(point["equity_gbp"] == 3000 for point in result["cash"]["points"])
    for name in ("spy_buy_hold", "spy_risk_budget"):
        run = result[name]
        assert run["fills"]
        assert all(fill["date"] > fill["signal_date"] for fill in run["fills"])
        assert all(fill["commission_usd"] >= 1 for fill in run["fills"])
        assert max(point["gross_exposure"] for point in run["points"]) > 0.3
        assert not run["deployment_admissible"] and not run["paper_execution_permitted"]


def test_benchmark_hard_halt_latches_and_buyhold_remains_a_reference() -> None:
    market, fx, start, end = market_fixture()
    bars = deepcopy(market.bars)
    crash = market.calendar.sessions[market.calendar.sessions.index(start) + 5]
    for day, row in bars["SPY"].items():
        if day >= crash:
            bars["SPY"][day] = replace(
                row,
                open=row.open * 0.5,
                close=row.close * 0.5,
                adjusted_close=row.adjusted_close * 0.5,
            )
    result = run_v2_benchmarks(
        replace(market, bars=bars),
        fx,
        V2Config(),
        start=start,
        end=end,
        initial_capital_gbp=3000,
        monthly_fee_gbp=0,
    )
    risk = result["spy_risk_budget"]
    assert risk["points"][-1]["hard_halted"]
    assert risk["points"][-1]["holdings"] == {}
    assert result["spy_buy_hold"]["points"][-1]["holdings"]
    assert result["cash"]["points"][-1]["equity_gbp"] == pytest.approx(3000)


def test_delayed_reference_entry_cancelled_by_invalid_covariance() -> None:
    market, fx, start, _ = market_fixture()
    index = market.calendar.sessions.index(start)
    invalid_day = market.calendar.sessions[index + 1]
    bars = deepcopy(market.bars)
    bars["SPY"][invalid_day] = replace(bars["SPY"][invalid_day], adjusted_close=float("nan"))
    result = run_v2_benchmarks(
        replace(market, bars=bars),
        fx,
        replace(V2Config(), execution_delay_sessions=2),
        start=start,
        end=market.calendar.sessions[index + 3],
        initial_capital_gbp=3000,
        monthly_fee_gbp=0,
        modes=("spy_risk_budget",),
    )["spy_risk_budget"]
    assert not result["fills"]
    assert any("invalid_risk_inputs" in issue["reason"] for issue in result["issues"])
    assert any(d["status"] == "cancelled_risk_inputs_or_regime" for d in result["decisions"])


def test_delayed_reference_entry_cancelled_by_weekly_risk_off() -> None:
    market, fx, start, _ = market_fixture()
    index = market.calendar.sessions.index(start)
    # Start is Wednesday month-end; Friday completes the next observed week.
    friday = market.calendar.sessions[index + 2]
    assert friday.weekday() == 4
    bars = deepcopy(market.bars)
    bars["SPY"][friday] = replace(bars["SPY"][friday], adjusted_close=1.0)
    result = run_v2_benchmarks(
        replace(market, bars=bars),
        fx,
        replace(V2Config(), execution_delay_sessions=3),
        start=start,
        end=market.calendar.sessions[index + 3],
        initial_capital_gbp=3000,
        monthly_fee_gbp=0,
        modes=("spy_risk_budget",),
    )["spy_risk_budget"]
    assert not result["fills"]
    assert any(d["status"] == "cancelled_risk_inputs_or_regime" for d in result["decisions"])


def test_cash_reference_is_independent_of_corrupt_spy_prices() -> None:
    market, fx, start, end = market_fixture()
    bars = deepcopy(market.bars)
    for day, row in bars["SPY"].items():
        if start <= day <= end:
            bars["SPY"][day] = replace(row, open=float("nan"), close=float("nan"))
    result = run_v2_benchmarks(
        replace(market, bars=bars),
        fx,
        V2Config(),
        start=start,
        end=end,
        initial_capital_gbp=1000,
        modes=("cash",),
    )["cash"]
    assert all(point["equity_gbp"] == 1000 for point in result["points"])
    assert not result["issues"] and not result["fills"]
