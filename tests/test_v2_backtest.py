"""Sequential V2 integration tests with synthetic, explicitly inadmissible prices."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest

from src.backtest.v2 import V2Market, run_v2_backtest
from src.backtest.v2_execution import FeeModel
from src.config.v2 import V2Config
from src.data.calendar import TradingCalendar
from src.data.canonical_historical import CanonicalCorporateAction, CanonicalDailyBar
from src.data.fx import FXHistory, FXObservation
from src.strategy.v2 import selection_dates


def market_fixture() -> tuple[V2Market, FXHistory, date, date]:
    candidates = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(540))
    sessions = tuple(day for day in candidates if day.weekday() < 5)
    week_ends = tuple(
        left
        for left, right in zip(sessions, sessions[1:], strict=False)
        if left.isocalendar()[:2] != right.isocalendar()[:2]
    )
    calendar = TradingCalendar("XNYS", "synthetic-no-holidays", sessions, week_ends, "a" * 64)
    bars: dict[str, dict[date, CanonicalDailyBar]] = {}
    for offset, symbol in enumerate(("SPY", "A", "B", "C", "D")):
        bars[symbol] = {}
        for index, day in enumerate(sessions):
            price = 40 * math.exp(0.001 * index + 0.004 * math.sin(index * 0.37 + offset))
            bars[symbol][day] = CanonicalDailyBar(
                symbol,
                symbol,
                day,
                price,
                price,
                price,
                price,
                price,
                50_000_000,
                price,
                price,
                price,
                50_000_000,
            )
    active = {day: frozenset(("A", "B", "C", "D")) for day in sessions}
    market = V2Market(calendar, "SPY", bars, active, ())
    observations = tuple(
        FXObservation(datetime.combine(day, time(0), UTC), datetime.combine(day, time(0), UTC), 0.8)
        for day in sessions
    )
    fx = FXHistory(observations, "synthetic", "test", "b" * 64, True)
    selections = tuple(
        day for day in selection_dates(calendar, V2Config()) if sessions.index(day) >= 253
    )
    return market, fx, selections[0], selections[2]


def run(
    market: V2Market,
    fx: FXHistory,
    start: date,
    end: date,
    config: V2Config | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return run_v2_backtest(
        market,
        fx,
        config or V2Config(),
        start=start,
        end=end,
        initial_capital_gbp=3000,
        monthly_fee_gbp=0,
        costs=FeeModel(),
        **kwargs,
    )


def test_next_open_timing_prefix_invariance_and_cash_start() -> None:
    market, fx, start, end = market_fixture()
    result = run(market, fx, start, end)
    assert result["points"][0]["holdings"] == {}
    assert result["fills"]
    next_day = market.calendar.sessions[market.calendar.sessions.index(start) + 1]
    assert result["fills"][0]["date"] == next_day.isoformat()
    assert all(fill["date"] > fill["signal_date"] for fill in result["fills"])
    assert all(
        fill["reference_price"]
        == market.bars[fill["security_id"]][date.fromisoformat(fill["date"])].open
        for fill in result["fills"]
    )
    prefix_end = market.calendar.sessions[market.calendar.sessions.index(start) + 15]
    prefix = run(market, fx, start, prefix_end)
    assert prefix["points"] == result["points"][: len(prefix["points"])]
    assert prefix["fills"] == [
        fill for fill in result["fills"] if fill["date"] <= prefix_end.isoformat()
    ]
    assert not result["deployment_admissible"]
    assert not result["paper_execution_permitted"]


def test_unaffordable_fill_does_not_become_incumbent() -> None:
    market, fx, start, end = market_fixture()
    expensive = deepcopy(market.bars)
    for day, bar in expensive["A"].items():
        expensive["A"][day] = replace(
            bar,
            open=bar.open * 1000,
            high=bar.high * 1000,
            low=bar.low * 1000,
            close=bar.close * 1000,
        )
    result = run(replace(market, bars=expensive), fx, start, end)
    assert all("A" not in point["holdings"] for point in result["points"])
    assert all(fill["security_id"] != "A" for fill in result["fills"])
    assert any(decision.get("skips") for decision in result["decisions"])


def test_splits_preserve_nav_and_episode_and_dividends_are_not_spendable() -> None:
    market, fx, start, end = market_fixture()
    split_day = market.calendar.sessions[market.calendar.sessions.index(start) + 5]
    before = run(market, fx, start, split_day)
    modified = deepcopy(market.bars)
    for day, bar in modified["A"].items():
        if day >= split_day:
            modified["A"][day] = replace(
                bar, open=bar.open / 2, high=bar.high / 2, low=bar.low / 2, close=bar.close / 2
            )
    split = CanonicalCorporateAction("A", "A", split_day, "split", 2)
    after = run(replace(market, bars=modified, actions=(split,)), fx, start, split_day)
    assert after["points"][-1]["equity_gbp"] == pytest.approx(before["points"][-1]["equity_gbp"])
    assert after["points"][-1]["holdings"]["A"] == before["points"][-1]["holdings"]["A"] * 2
    assert after["episodes"] == before["episodes"]
    dividend = CanonicalCorporateAction("A", "A", split_day, "dividend", 1)
    dividend_run = run(replace(market, actions=(dividend,)), fx, start, split_day)
    holding = before["points"][-1]["holdings"]["A"]
    assert dividend_run["points"][-1]["receivables_usd"] == holding
    assert dividend_run["points"][-1]["cash_usd"] == before["points"][-1]["cash_usd"]
    assert dividend_run["invalid_evidence"]


def test_permanent_hard_halt_retains_full_tail_and_closes_episodes() -> None:
    market, fx, start, end = market_fixture()
    crash = market.calendar.sessions[market.calendar.sessions.index(start) + 5]
    bars = deepcopy(market.bars)
    for symbol in ("A", "B", "C", "D"):
        for day, bar in bars[symbol].items():
            if day >= crash:
                bars[symbol][day] = replace(
                    bar,
                    open=bar.open * 0.5,
                    high=bar.high * 0.5,
                    low=bar.low * 0.5,
                    close=bar.close * 0.5,
                    adjusted_close=bar.adjusted_close * 0.5,
                )
    result = run(replace(market, bars=bars), fx, start, end)
    halted = [point for point in result["points"] if point["hard_halted"]]
    assert halted and halted[0]["date"] == crash.isoformat()
    assert all(
        point["hard_halted"] for point in result["points"] if point["date"] >= crash.isoformat()
    )
    assert result["points"][-1]["date"] == end.isoformat()
    assert result["points"][-1]["holdings"] == {}
    assert len(result["episodes"]) == 4
    assert all(
        fill["side"] != "buy" for fill in result["fills"] if fill["date"] > crash.isoformat()
    )


@pytest.mark.parametrize("missing_spy", [False, True])
def test_delayed_hard_halt_is_not_starved_by_repeated_daily_signals(missing_spy: bool) -> None:
    market, fx, start, end = market_fixture()
    sessions = market.calendar.sessions
    crash_index = sessions.index(start) + 8
    crash = sessions[crash_index]
    bars = deepcopy(market.bars)
    for symbol in ("A", "B", "C", "D"):
        for day, bar in bars[symbol].items():
            if day >= crash:
                bars[symbol][day] = replace(
                    bar,
                    open=bar.open * 0.5,
                    high=bar.high * 0.5,
                    low=bar.low * 0.5,
                    close=bar.close * 0.5,
                    adjusted_close=bar.adjusted_close * 0.5,
                )
    if missing_spy:
        del bars["SPY"][sessions[crash_index + 1]]
    result = run(
        replace(market, bars=bars), fx, start, end, replace(V2Config(), execution_delay_sessions=3)
    )
    due = sessions[crash_index + 3].isoformat()
    assert any(fill["date"] == due and fill["side"] == "sell" for fill in result["fills"])
    assert all(not point["holdings"] for point in result["points"] if point["date"] >= due)


def test_weekly_risk_off_liquidates_and_reentry_waits_for_month_end() -> None:
    market, fx, start, end = market_fixture()
    sessions = market.calendar.sessions
    weekly = next(
        day for day in market.calendar.week_ends if day > sessions[sessions.index(start) + 5]
    )
    bars = deepcopy(market.bars)
    bar = bars["SPY"][weekly]
    bars["SPY"][weekly] = replace(
        bar, close=bar.close * 0.5, adjusted_close=bar.adjusted_close * 0.5
    )
    result = run(replace(market, bars=bars), fx, start, end)
    execution = sessions[sessions.index(weekly) + 1]
    assert any(
        fill["date"] == execution.isoformat() and fill["side"] == "sell" for fill in result["fills"]
    )
    reentry_signal = next(
        day for day in selection_dates(market.calendar, V2Config()) if day > weekly
    )
    assert all(
        fill["side"] != "buy"
        for fill in result["fills"]
        if execution.isoformat() <= fill["date"] <= reentry_signal.isoformat()
    )
    assert any(
        fill["side"] == "buy" and fill["signal_date"] == reentry_signal.isoformat()
        for fill in result["fills"]
    )


def test_missing_held_price_invalidates_run_instead_of_inventing_liquidation() -> None:
    market, fx, start, end = market_fixture()
    missing = market.calendar.sessions[market.calendar.sessions.index(start) + 5]
    bars = deepcopy(market.bars)
    del bars["A"][missing]
    with pytest.raises(ValueError, match="missing held raw price"):
        run(replace(market, bars=bars), fx, start, end)


def test_risk_reduction_cannot_buy_after_overnight_price_reversal() -> None:
    market, fx, start, end = market_fixture()
    sessions = market.calendar.sessions
    spike = sessions[sessions.index(start) + 6]
    following = sessions[sessions.index(spike) + 1]
    bars = deepcopy(market.bars)
    bar = bars["A"][spike]
    bars["A"][spike] = replace(bar, close=bar.close * 1.5, high=bar.high * 1.5)
    following_bar = bars["A"][following]
    bars["A"][following] = replace(
        following_bar, open=following_bar.open * 0.8, low=following_bar.low * 0.8
    )
    result = run(replace(market, bars=bars), fx, start, end)
    assert any(
        decision["signal_date"] == spike.isoformat() and decision["reason"] == "risk_reduction"
        for decision in result["decisions"]
    )
    assert all(
        fill["side"] == "sell" for fill in result["fills"] if fill["reason"] == "risk_reduction"
    )


def test_delisting_cash_recovery_closes_inventory_without_a_raw_mark() -> None:
    market, fx, start, end = market_fixture()
    recovery = market.calendar.sessions[market.calendar.sessions.index(start) + 5]
    bars = deepcopy(market.bars)
    bars["A"] = {day: bar for day, bar in bars["A"].items() if day < recovery}
    active = {
        day: names - {"A"} if day >= recovery else names for day, names in market.active.items()
    }
    action = CanonicalCorporateAction("A", "A", recovery, "delisting", 20)
    result = run(replace(market, bars=bars, active=active, actions=(action,)), fx, start, end)
    fills = [fill for fill in result["fills"] if fill["reason"] == "delisting_recovery"]
    assert len(fills) == 1 and fills[0]["execution_price"] == 20
    assert any(
        episode["security_id"] == "A" and episode["exit"] == recovery.isoformat()
        for episode in result["episodes"]
    )
    assert all(
        "A" not in point["holdings"]
        for point in result["points"]
        if point["date"] >= recovery.isoformat()
    )


def test_hard_halt_escalates_pending_soft_reduction_without_extending_deadline() -> None:
    market, fx, start, end = market_fixture()
    sessions = market.calendar.sessions
    soft_index = sessions.index(start) + 6
    hard_index = soft_index + 1
    bars = deepcopy(market.bars)
    for symbol in ("A", "B", "C", "D"):
        for day, row in bars[symbol].items():
            factor = (
                0.72 if day >= sessions[hard_index] else 0.87 if day >= sessions[soft_index] else 1
            )
            bars[symbol][day] = replace(
                row,
                open=row.open * factor,
                close=row.close * factor,
                adjusted_close=row.adjusted_close * factor,
            )
    result = run(
        replace(market, bars=bars), fx, start, end, replace(V2Config(), execution_delay_sessions=3)
    )
    points = {p["date"]: p for p in result["points"]}
    assert points[sessions[soft_index].isoformat()]["soft_active"]
    assert points[sessions[hard_index].isoformat()]["hard_halted"]
    due = sessions[soft_index + 3].isoformat()
    assert points[due]["holdings"] == {}
    exits = [f for f in result["fills"] if f["date"] == due]
    assert exits and all(f["reason"] == "hard_halt" for f in exits)
    assert all(f["amended_at"] >= sessions[hard_index].isoformat() for f in exits)


def test_missing_spy_cancels_delayed_monthly_increases() -> None:
    market, fx, start, _ = market_fixture()
    sessions = market.calendar.sessions
    index = sessions.index(start)
    missing_day, execution_day = sessions[index + 1 : index + 3]
    config = replace(V2Config(), execution_delay_sessions=2)
    control = run(market, fx, start, execution_day, config)
    assert any(fill["side"] == "buy" for fill in control["fills"])
    changed = deepcopy(market.bars)
    del changed["SPY"][missing_day]
    result = run(replace(market, bars=changed), fx, start, execution_day, config)
    assert not result["fills"]
    assert result["invalid_evidence"]
    assert all(not point["holdings"] for point in result["points"])
    assert any(
        decision["reason"] == "invalid_spy_blocks_pending_increase"
        and decision["status"] == "cancelled"
        for decision in result["decisions"]
    )


def test_monthly_stock_exit_merges_with_concentration_reduction() -> None:
    market, fx, start, _ = market_fixture()
    sessions = market.calendar.sessions
    month_end = next(day for day in selection_dates(market.calendar, V2Config()) if day > start)
    execution_day = sessions[sessions.index(month_end) + 1]
    bars = deepcopy(market.bars)
    # A's steady decline leaves the name below its SMA at monthly selection.
    # B's simultaneous gain creates a concentration correction without an account halt.
    between = tuple(day for day in sessions if start < day <= month_end)
    for index, day in enumerate(between):
        a, b = bars["A"][day], bars["B"][day]
        factor_a = 1 - 0.12 * (index + 1) / len(between)
        factor_b = 1 + 0.20 * (index + 1) / len(between)
        for symbol, row, factor in (("A", a, factor_a), ("B", b, factor_b)):
            bars[symbol][day] = replace(
                row,
                open=row.open * factor,
                close=row.close * factor,
                adjusted_close=row.adjusted_close * factor,
            )
    # Guarantee an additional concentration breach exactly on the selection close.
    b = bars["B"][month_end]
    bars["B"][month_end] = replace(b, close=b.close * 1.3, adjusted_close=b.adjusted_close * 1.3)
    result = run(replace(market, bars=bars), fx, start, execution_day)
    prior = next(point for point in result["points"] if point["date"] == month_end.isoformat())
    assert "A" in prior["holdings"]
    following = [fill for fill in result["fills"] if fill["date"] == execution_day.isoformat()]
    assert any(fill["security_id"] == "A" and fill["side"] == "sell" for fill in following)
    assert all(fill["side"] == "sell" for fill in following)
    assert "A" not in result["points"][-1]["holdings"]
