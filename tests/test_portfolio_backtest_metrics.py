import math
from datetime import date

import pytest

from src.backtest.costs import CostModel
from src.backtest.engine import (
    BacktestDataError,
    DelistingEvent,
    PriceBar,
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
    assert build_equal_weight_targets(
        ["AAA"],
        target_positions=4,
        regime_ceiling=0.0,
        cash_buffer=0.02,
        max_position_weight=0.30,
        max_positions=5,
    ) == {}


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
