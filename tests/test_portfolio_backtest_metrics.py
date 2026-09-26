import math
from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from src.backtest.costs import CostModel
from src.backtest.engine import (
    BacktestDataError,
    DelistingEvent,
    PriceBar,
    RiskState,
    run_backtest,
)
from src.backtest.metrics import TradeOutcome, benchmark_relative_metrics, performance_metrics
from src.portfolio.equal_weight import Regime, build_equal_weight_targets


def bar(day: int, symbol: str, opening: float, close: float | None = None) -> PriceBar:
    return PriceBar(date(2024, 1, day), symbol, opening, close or opening, close or opening)


def test_equal_weight_targets_preserve_all_hard_caps() -> None:
    targets = build_equal_weight_targets(
        ["AAA", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"],
        target_positions=6,
        regime_ceiling=1.0,
        cash_buffer=0.02,
        max_position_weight=0.30,
        max_positions=5,
    )
    assert Regime.RISK_ON.value == "risk_on"
    assert list(targets) == ["AAA", "BBB", "CCC", "DDD", "EEE"]
    assert sum(targets.values()) == pytest.approx(0.98)
    assert max(targets.values()) <= 0.30

    sparse = build_equal_weight_targets(
        ["AAA", "BBB"],
        target_positions=4,
        regime_ceiling=1.0,
        cash_buffer=0.02,
        max_position_weight=0.30,
        max_positions=5,
    )
    assert sparse == {"AAA": 0.30, "BBB": 0.30}
    assert (
        build_equal_weight_targets(
            ["AAA"],
            target_positions=4,
            regime_ceiling=0.0,
            cash_buffer=0.02,
            max_position_weight=0.30,
            max_positions=5,
        )
        == {}
    )


def test_backtest_executes_next_session_with_costs_and_never_negative_cash() -> None:
    bars = [bar(day, symbol, 100.0) for day in (2, 3, 4) for symbol in ("AAA", "BBB")]
    result = run_backtest(
        bars,
        {date(2024, 1, 2): {"AAA": 0.30, "BBB": 0.30}},
        initial_cash=1_000.0,
        costs=CostModel(commission_per_order=0.35, slippage_bps_each_side=5, fx_buffer_bps=5),
    )
    assert {trade.date for trade in result.trades} == {date(2024, 1, 3)}
    assert all(trade.signal_date == date(2024, 1, 2) for trade in result.trades)
    assert all(trade.side == "buy" for trade in result.trades)
    assert all(point.cash >= 0.0 for point in result.equity_curve)
    fill_point = next(point for point in result.equity_curve if point.date == date(2024, 1, 3))
    assert fill_point.cash / fill_point.equity >= 0.02
    assert result.equity_curve[-1].equity < 1_000.0
    assert sum(trade.total_cost for trade in result.trades) > 0.0

    trace = result.execution_trace
    assert len(trace.decisions) == 1
    assert trace.decisions[0].status == "applied"
    assert tuple(row.security_id for row in trace.decisions[0].target_weights) == ("AAA", "BBB")
    assert len(trace.order_intents) == len(trace.fills) == 2
    assert {row.order_id for row in trace.order_intents} == {row.order_id for row in trace.fills}
    assert not trace.missing_open_dispositions
    assert len(trace.sha256) == 64
    with pytest.raises(FrozenInstanceError):
        trace.sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(ValueError, match="digest"):
        replace(trace, sha256="0" * 64)


def test_execution_trace_is_semantically_deterministic_and_records_no_op_and_no_next() -> None:
    bars = [bar(day, symbol, 100.0) for day in (2, 3, 4) for symbol in ("AAA", "BBB")]
    targets = {
        date(2024, 1, 2): {"BBB": 0.2, "AAA": 0.3},
        date(2024, 1, 3): {"AAA": 0.3, "BBB": 0.2},
        date(2024, 1, 4): {},
    }
    first = run_backtest(bars, targets, costs=CostModel(0.0, 0.0, 0.0))
    second = run_backtest(
        bars,
        {
            day: dict(reversed(tuple(weights.items())))
            for day, weights in reversed(tuple(targets.items()))
        },
        costs=CostModel(0.0, 0.0, 0.0),
    )

    assert first.execution_trace == second.execution_trace
    assert [row.status for row in first.execution_trace.decisions] == [
        "applied",
        "no_op",
        "no_next_session",
    ]
    assert all(isinstance(row.target_weights, tuple) for row in first.execution_trace.decisions)


def test_execution_trace_records_superseded_decisions() -> None:
    bars = [bar(day, "AAA", 100.0) for day in (3, 4)]
    result = run_backtest(
        bars,
        {
            date(2024, 1, 1): {"AAA": 0.2},
            date(2024, 1, 2): {"AAA": 0.3},
        },
        costs=CostModel(0.0, 0.0, 0.0),
    )

    assert [row.status for row in result.execution_trace.decisions] == ["superseded", "applied"]
    assert result.execution_trace.decisions[0].execution_date == date(2024, 1, 3)


@pytest.mark.parametrize(
    "targets,expected_exposure",
    [({"AAA": 0.30}, 0.30), ({"AAA": 0.25, "BBB": 0.25}, 0.50)],
)
def test_post_cost_fills_respect_actual_exposure_ceiling(
    targets: dict[str, float], expected_exposure: float
) -> None:
    bars = [bar(day, symbol, 100.0) for day in (2, 3) for symbol in ("AAA", "BBB")]
    result = run_backtest(bars, {date(2024, 1, 2): targets}, initial_cash=1_000.0)
    fill = result.equity_curve[-1]

    assert fill.gross_exposure == pytest.approx(expected_exposure, abs=1e-12)
    assert fill.cash / fill.equity >= 0.02


def test_infeasible_fixed_cost_target_fails_before_any_partial_fill() -> None:
    bars = [bar(day, symbol, 100.0) for day in (2, 3) for symbol in ("AAA", "BBB")]

    with pytest.raises(BacktestDataError, match="cannot be executed safely|infeasible"):
        run_backtest(
            bars,
            {date(2024, 1, 2): {"AAA": 0.30, "BBB": 0.30}},
            initial_cash=0.50,
        )


def test_round_trip_reconciles_each_cost_once_in_adverse_direction() -> None:
    bars = [bar(day, "AAA", 100.0) for day in (2, 3, 4)]
    result = run_backtest(
        bars,
        {date(2024, 1, 2): {"AAA": 0.30}, date(2024, 1, 3): {}},
        initial_cash=1_000.0,
        costs=CostModel(0.35, 5.0, 5.0),
    )
    buy, sell = result.trades

    assert buy.execution_price == pytest.approx(100.05)
    assert sell.execution_price == pytest.approx(99.95)
    assert buy.commission == sell.commission == 0.35
    assert buy.fx_cost == pytest.approx(buy.gross_notional * 0.0005)
    assert sell.fx_cost == pytest.approx(sell.gross_notional * 0.0005)
    assert result.equity_curve[-1].equity == pytest.approx(
        1_000.0 - buy.total_cost - sell.total_cost
    )


def test_no_change_target_generates_no_second_fee_and_sells_happen_before_buys() -> None:
    bars = [bar(day, symbol, 100.0) for day in (2, 3, 4, 5) for symbol in ("AAA", "BBB")]
    no_change = run_backtest(
        bars,
        {
            date(2024, 1, 2): {"AAA": 0.3},
            date(2024, 1, 3): {"AAA": 0.3},
        },
        costs=CostModel(0.0, 0.0, 0.0),
    )
    assert [(trade.date, trade.symbol, trade.side) for trade in no_change.trades] == [
        (date(2024, 1, 3), "AAA", "buy")
    ]

    replacement = run_backtest(
        bars,
        {
            date(2024, 1, 2): {"AAA": 0.30},
            date(2024, 1, 3): {"BBB": 0.30},
        },
        costs=CostModel(0.0, 0.0, 0.0),
    )
    day_four = [trade for trade in replacement.trades if trade.date == date(2024, 1, 4)]
    assert [trade.side for trade in day_four] == ["sell", "buy"]


def test_adjusted_open_and_disappearing_symbol_liquidation_are_explicit() -> None:
    bars = [
        bar(2, "AAA", 100.0),
        PriceBar(date(2024, 1, 3), "AAA", 100.0, 100.0, 50.0),
        bar(2, "SPY", 100.0),
        bar(3, "SPY", 100.0),
        bar(4, "SPY", 100.0),
    ]
    result = run_backtest(
        bars,
        {date(2024, 1, 2): {"AAA": 0.3}},
        costs=CostModel(0.0, 0.0, 0.0),
        initial_cash=1_000.0,
        delistings=(DelistingEvent(date(2024, 1, 4), "AAA", 40.0),),
    )
    assert result.trades[0].reference_price == pytest.approx(50.0)
    assert result.trades[-1].reason == "disappearance"
    assert result.trades[-1].date == date(2024, 1, 4)
    assert result.trades[-1].reference_price == pytest.approx(40.0)
    assert result.trades[-1].total_cost == 0.0
    assert result.final_positions == {}
    settlement = result.execution_trace.corporate_action_settlements
    assert len(settlement) == 1
    assert settlement[0].security_id == "AAA"
    assert settlement[0].proceeds == pytest.approx(result.trades[-1].gross_notional)
    assert all(
        fill.order_id != settlement[0].settlement_id for fill in result.execution_trace.fills
    )


def test_missing_held_bar_without_delisting_fails_closed() -> None:
    bars = [bar(2, "AAA", 100.0), bar(3, "AAA", 100.0), bar(4, "SPY", 100.0)]
    with pytest.raises(BacktestDataError, match="no bar or delisting"):
        run_backtest(bars, {date(2024, 1, 2): {"AAA": 0.3}})


def test_missing_target_open_is_recorded_and_never_fabricated() -> None:
    result = run_backtest(
        [bar(2, "SPY", 100.0), bar(3, "SPY", 100.0)],
        {date(2024, 1, 2): {"AAA": 0.3}},
    )

    assert result.trades == ()
    assert len(result.execution_issues) == 1
    assert result.execution_issues[0].reason == "missing_open"
    trace = result.execution_trace
    assert len(trace.decisions) == len(trace.order_intents) == 1
    assert not trace.fills
    assert len(trace.missing_open_dispositions) == 1
    assert trace.order_intents[0].requested_shares is None
    assert trace.order_intents[0].reference_price is None
    assert trace.order_intents[0].order_id == trace.missing_open_dispositions[0].order_id


@pytest.mark.parametrize(
    "targets",
    [
        {"AAA": 0.31},
        {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.1, "FFF": 0.05},
        {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.19},
    ],
)
def test_backtest_rejects_targets_that_bypass_hard_limits(targets: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        run_backtest(
            [bar(2, symbol, 100.0) for symbol in targets],
            {date(2024, 1, 1): targets},
        )


def test_metrics_cover_standard_trade_and_benchmark_outputs_without_infinity() -> None:
    dates = [date(2023, 12, 29), date(2024, 1, 2), date(2024, 1, 3), date(2024, 2, 1)]
    values = [100.0, 110.0, 99.0, 108.0]
    report = performance_metrics(
        dates,
        values,
        trade_outcomes=[TradeOutcome(0.10, 5), TradeOutcome(-0.05, 10)],
        traded_notional=200.0,
        exposures=[0.0, 0.5, 0.5, 1.0],
    )
    assert report.maximum_drawdown == pytest.approx(0.10)
    assert report.win_rate == 0.5
    assert report.profit_factor == pytest.approx(2.0)
    assert report.average_holding_period == pytest.approx(7.5)
    assert report.exposure == pytest.approx(0.5)
    assert report.best_month is not None and report.worst_year is not None

    relative = benchmark_relative_metrics(dates, values, [100.0, 105.0, 100.0, 102.0])
    assert relative.excess_cagr is not None
    assert relative.tracking_error is not None
    assert relative.up_market_capture is not None
    assert relative.down_market_capture is not None
    assert all(
        value is None or math.isfinite(value)
        for value in (
            relative.excess_cagr,
            relative.tracking_error,
            relative.information_ratio,
            relative.up_market_capture,
            relative.down_market_capture,
        )
    )


def test_undefined_metrics_are_none_not_infinity() -> None:
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    report = performance_metrics(dates, [100.0, 100.0])
    assert report.sharpe_ratio is None
    assert report.sortino_ratio is None
    assert report.calmar_ratio is None
    assert report.profit_factor is None
    assert report.number_of_trades == 0

    relative = benchmark_relative_metrics(dates, [100.0, 100.0], [100.0, 100.0])
    assert relative.information_ratio is None
    assert relative.up_market_capture is None
    assert relative.down_market_capture is None


def test_profit_factor_uses_monetary_profit_not_unweighted_returns() -> None:
    report = performance_metrics(
        [date(2024, 1, 2), date(2024, 1, 3)],
        [100.0, 101.0],
        trade_outcomes=[
            TradeOutcome(1.0, 1, profit_loss=100.0),
            TradeOutcome(-0.10, 1, profit_loss=-1_000.0),
        ],
    )

    assert report.profit_factor == pytest.approx(0.1)


def test_standard_metric_formulas_are_explicit() -> None:
    dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    values = [100.0, 110.0, 99.0]
    report = performance_metrics(
        dates,
        values,
        traded_notional=150.0,
        exposures=[0.0, 0.5, 1.0],
    )

    daily_std = math.sqrt(0.02)
    expected_cagr = 0.99 ** (365.2425 / 2) - 1.0
    assert report.cagr == pytest.approx(expected_cagr)
    assert report.annualized_volatility == pytest.approx(daily_std * math.sqrt(252))
    assert report.sharpe_ratio == pytest.approx(0.0)
    assert report.sortino_ratio == pytest.approx(0.0)
    assert report.maximum_drawdown == pytest.approx(0.10)
    assert report.calmar_ratio == pytest.approx(expected_cagr / 0.10)
    assert report.turnover == pytest.approx(150.0 / 103.0)
    assert report.exposure == pytest.approx(0.5)


def test_soft_drawdown_is_causal_and_reduces_the_next_target() -> None:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    bars = [
        PriceBar(date(2024, 1, day), symbol, price, price, price)
        for day, price in ((1, 100.0), (2, 100.0), (3, 89.0), (4, 89.0))
        for symbol in symbols
    ]
    full_target = dict.fromkeys(symbols, 0.245)
    result = run_backtest(
        bars,
        {date(2024, 1, 1): full_target, date(2024, 1, 3): full_target},
        costs=CostModel(0.0, 0.0, 0.0),
        soft_drawdown_threshold=0.10,
        hard_drawdown_threshold=0.15,
    )

    assert result.risk_events[0].date == date(2024, 1, 3)
    assert result.risk_events[0].state is RiskState.SOFT
    assert all(trade.date > trade.signal_date for trade in result.trades if trade.signal_date)
    final_equity = result.equity_curve[-1].equity
    final_weights = {
        symbol: shares * 89.0 / final_equity for symbol, shares in result.final_positions.items()
    }
    assert max(final_weights.values()) == pytest.approx(0.15)
    assert sum(final_weights.values()) == pytest.approx(0.60)


def test_hard_drawdown_liquidates_next_session_and_remains_latched() -> None:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    bars = [
        PriceBar(date(2024, 1, day), symbol, price, price, price)
        for day, price in (
            (1, 100.0),
            (2, 100.0),
            (3, 80.0),
            (4, 80.0),
            (5, 100.0),
        )
        for symbol in symbols
    ]
    full_target = dict.fromkeys(symbols, 0.245)
    result = run_backtest(
        bars,
        {
            date(2024, 1, 1): full_target,
            date(2024, 1, 3): full_target,
            date(2024, 1, 4): full_target,
        },
        costs=CostModel(0.0, 0.0, 0.0),
        soft_drawdown_threshold=0.10,
        hard_drawdown_threshold=0.15,
    )

    assert result.risk_events[0].date == date(2024, 1, 3)
    assert result.risk_events[0].state is RiskState.HARD
    liquidation = [trade for trade in result.trades if trade.reason == "drawdown_hard"]
    assert liquidation
    assert {trade.date for trade in liquidation} == {date(2024, 1, 4)}
    assert not result.final_positions
    assert result.final_risk_state is RiskState.HARD
    assert not [
        trade for trade in result.trades if trade.side == "buy" and trade.date > date(2024, 1, 3)
    ]
    assert all(
        point.high_water_mark >= result.equity_curve[index - 1].high_water_mark
        for index, point in enumerate(result.equity_curve[1:], start=1)
    )
    hard_decision = next(
        row for row in result.execution_trace.decisions if row.reason == "drawdown_hard"
    )
    assert hard_decision.signal_date == date(2024, 1, 3)
    assert hard_decision.execution_date == date(2024, 1, 4)
    assert hard_decision.status == "applied"


def test_execution_trace_records_unexecutable_final_session_risk_decision() -> None:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    bars = [
        PriceBar(date(2024, 1, day), symbol, price, price, price)
        for day, price in ((1, 100.0), (2, 100.0), (3, 80.0))
        for symbol in symbols
    ]
    result = run_backtest(
        bars,
        {date(2024, 1, 1): dict.fromkeys(symbols, 0.245)},
        costs=CostModel(0.0, 0.0, 0.0),
        soft_drawdown_threshold=0.10,
        hard_drawdown_threshold=0.15,
    )

    final_decision = next(
        row for row in result.execution_trace.decisions if row.reason == "drawdown_hard"
    )
    assert final_decision.signal_date == date(2024, 1, 3)
    assert final_decision.execution_date is None
    assert final_decision.status == "no_next_session"


def test_soft_drawdown_queues_risk_reduction_without_a_strategy_signal() -> None:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    bars = [
        PriceBar(date(2024, 2, day), symbol, price, price, price)
        for day, price in ((1, 100.0), (2, 100.0), (3, 89.0), (4, 89.0))
        for symbol in symbols
    ]
    result = run_backtest(
        bars,
        {date(2024, 2, 1): dict.fromkeys(symbols, 0.245)},
        costs=CostModel(0.0, 0.0, 0.0),
        soft_drawdown_threshold=0.10,
        hard_drawdown_threshold=0.15,
    )

    reductions = [target for target in result.applied_targets if target.reason == "risk_reduction"]
    assert len(reductions) == 1
    assert reductions[0].signal_date == date(2024, 2, 3)
    assert reductions[0].date == date(2024, 2, 4)
    assert max(reductions[0].weights.values()) == pytest.approx(0.15)


def test_concentration_drift_is_reduced_on_the_next_session() -> None:
    prices = {
        1: {"AAA": 100.0, "BBB": 100.0},
        2: {"AAA": 100.0, "BBB": 100.0},
        3: {"AAA": 300.0, "BBB": 50.0},
        4: {"AAA": 300.0, "BBB": 50.0},
    }
    bars = [
        PriceBar(date(2024, 3, day), symbol, price, price, price)
        for day, by_symbol in prices.items()
        for symbol, price in by_symbol.items()
    ]
    result = run_backtest(
        bars,
        {date(2024, 3, 1): {"AAA": 0.30, "BBB": 0.30}},
        costs=CostModel(0.0, 0.0, 0.0),
    )

    reduction = [target for target in result.applied_targets if target.reason == "risk_reduction"]
    assert len(reduction) == 1
    assert reduction[0].signal_date == date(2024, 3, 3)
    assert reduction[0].date == date(2024, 3, 4)
    assert max(reduction[0].weights.values()) <= 0.30
    reduction_trades = [trade for trade in result.trades if trade.reason == "risk_reduction"]
    assert {(trade.symbol, trade.side) for trade in reduction_trades} == {("AAA", "sell")}


def test_scheduled_exit_supersedes_pending_concentration_reduction() -> None:
    prices = {
        1: {"AAA": 100.0, "BBB": 100.0},
        2: {"AAA": 100.0, "BBB": 100.0},
        3: {"AAA": 300.0, "BBB": 50.0},
        4: {"AAA": 300.0, "BBB": 50.0},
    }
    bars = [
        PriceBar(date(2024, 6, day), symbol, price, price, price)
        for day, by_symbol in prices.items()
        for symbol, price in by_symbol.items()
    ]
    result = run_backtest(
        bars,
        {
            date(2024, 6, 1): {"AAA": 0.30, "BBB": 0.30},
            date(2024, 6, 3): {},
        },
        costs=CostModel(0.0, 0.0, 0.0),
    )

    applied = [target for target in result.applied_targets if target.date == date(2024, 6, 4)]
    assert len(applied) == 1
    assert applied[0].reason == "rebalance"
    assert applied[0].weights == {}
    assert not result.final_positions


@pytest.mark.parametrize(
    ("drawdown", "expected"),
    [
        (0.099999, RiskState.NORMAL),
        (0.10, RiskState.SOFT),
        (0.149999, RiskState.SOFT),
        (0.15, RiskState.HARD),
    ],
)
def test_drawdown_boundaries_are_inclusive(drawdown: float, expected: RiskState) -> None:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    crash_price = ((100_000.0 * (1.0 - drawdown)) - 2_000.0) / 980.0
    bars = [
        PriceBar(date(2024, 4, day), symbol, price, price, price)
        for day, price in ((1, 100.0), (2, 100.0), (3, crash_price))
        for symbol in symbols
    ]
    result = run_backtest(
        bars,
        {date(2024, 4, 1): dict.fromkeys(symbols, 0.245)},
        costs=CostModel(0.0, 0.0, 0.0),
        soft_drawdown_threshold=0.10,
        hard_drawdown_threshold=0.15,
    )
    assert result.final_risk_state is expected


def test_hard_liquidation_uses_next_available_session_across_gap() -> None:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    bars = [
        PriceBar(session, symbol, price, price, price)
        for session, price in (
            (date(2024, 5, 1), 100.0),
            (date(2024, 5, 2), 100.0),
            (date(2024, 5, 3), 80.0),
            (date(2024, 5, 6), 80.0),
        )
        for symbol in symbols
    ]
    result = run_backtest(
        bars,
        {date(2024, 5, 1): dict.fromkeys(symbols, 0.245)},
        costs=CostModel(0.0, 0.0, 0.0),
        soft_drawdown_threshold=0.10,
        hard_drawdown_threshold=0.15,
    )
    liquidations = [trade for trade in result.trades if trade.reason == "drawdown_hard"]
    assert {trade.signal_date for trade in liquidations} == {date(2024, 5, 3)}
    assert {trade.date for trade in liquidations} == {date(2024, 5, 6)}
