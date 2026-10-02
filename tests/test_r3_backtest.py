from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from src.backtest.r3 import R3MarketBar, R3MarketData, _select, simulate_r3_account
from src.config.r3 import load_r3_config
from src.config.r3_development import load_r3_development_config
from src.data.fx import FXHistory, FXObservation
from src.features.r3 import monthly_decision_dates


def _sessions(count: int) -> tuple[date, ...]:
    rows: list[date] = []
    current = date(2020, 1, 1)
    while len(rows) < count:
        if current.weekday() < 5:
            rows.append(current)
        current += timedelta(days=1)
    return tuple(rows)


def _market() -> R3MarketData:
    sessions = _sessions(700)
    bars: list[R3MarketBar] = []
    for index, day in enumerate(sessions):
        spy = 100 + index * 0.05
        stock = 40 + index * 0.04
        bars.extend(
            (
                R3MarketBar("SPY", day, spy, spy, spy, 10_000_000),
                R3MarketBar("AAA", day, stock, stock, stock, 5_000_000),
            )
        )
    week_ends = frozenset(
        left
        for left, right in zip(sessions, sessions[1:], strict=False)
        if left.isocalendar()[:2] != right.isocalendar()[:2]
    )
    observations = tuple(
        FXObservation(
            datetime.combine(day - timedelta(days=1), datetime.min.time(), UTC),
            datetime.combine(day, datetime.min.time(), UTC),
            0.8,
        )
        for day in sessions
    )
    fx = FXHistory(observations, "fixture", "fixture", "a" * 64, synthetic=True)
    return R3MarketData(sessions, week_ends, "SPY", tuple(bars), (), fx)


def test_common_engine_obeys_causal_fill_cost_and_account_limits() -> None:
    market = _market()
    config = load_r3_config(__import__("pathlib").Path("config.r3.yaml"))
    development = load_r3_development_config(
        __import__("pathlib").Path("config.r3-development.yaml")
    )
    decisions = monthly_decision_dates(market.sessions)
    first = next(day for day in decisions if market.sessions.index(day) >= 252)
    scores = {day: {"AAA": 1.0} for day in decisions if day >= first}
    result = simulate_r3_account(
        candidate_id="R3-M",
        scores_by_decision=scores,
        market=market,
        config=config,
        development=development,
        first_decision=first,
    )
    assert result.failure is None
    assert result.end_session <= first.replace(year=first.year + 1) + timedelta(days=7)
    assert result.account_fees_gbp == 36.0
    assert all(fill.session > fill.decision_date for fill in result.fills)
    assert all(point.gross_exposure <= 1.0 + 1e-12 for point in result.nav)
    assert result.liquidation_reserve_gbp == 5.03


def test_missing_model_scores_do_not_silently_switch_candidates() -> None:
    market = _market()
    config = load_r3_config(__import__("pathlib").Path("config.r3.yaml"))
    development = load_r3_development_config(
        __import__("pathlib").Path("config.r3-development.yaml")
    )
    decisions = monthly_decision_dates(market.sessions)
    first = next(day for day in decisions if market.sessions.index(day) >= 252)
    result = simulate_r3_account(
        candidate_id="R3-L-a1",
        scores_by_decision={},
        market=market,
        config=config,
        development=development,
        first_decision=first,
    )
    assert result.failure is None
    assert result.fills == ()
    assert result.mean_exposure == 0.0


def test_full_incumbent_set_does_not_add_a_fifth_target() -> None:
    config = load_r3_config(__import__("pathlib").Path("config.r3.yaml"))
    ranked = ("A", "B", "C", "D", "E")
    holdings = {security_id: 1 for security_id in ranked[:4]}
    assert _select(ranked, holdings, config) == ranked[:4]


def test_missing_held_valuation_fails_closed() -> None:
    market = _market()
    config = load_r3_config(__import__("pathlib").Path("config.r3.yaml"))
    development = load_r3_development_config(
        __import__("pathlib").Path("config.r3-development.yaml")
    )
    decisions = monthly_decision_dates(market.sessions)
    first = next(day for day in decisions if market.sessions.index(day) >= 252)
    missing_day = market.sessions[market.sessions.index(first) + 10]
    broken = R3MarketData(
        market.sessions,
        market.week_ends,
        market.benchmark_id,
        tuple(
            row
            for row in market.bars
            if not (row.security_id == "AAA" and row.session == missing_day)
        ),
        market.actions,
        market.fx,
    )
    scores = {day: {"AAA": 1.0} for day in decisions if day >= first}
    result = simulate_r3_account(
        candidate_id="R3-M",
        scores_by_decision=scores,
        market=broken,
        config=config,
        development=development,
        first_decision=first,
    )
    assert result.failure is not None
    assert result.failure.startswith("missing held valuation:AAA:")


def test_daily_concentration_breach_queues_mandatory_reduction() -> None:
    market = _market()
    config = load_r3_config(__import__("pathlib").Path("config.r3.yaml"))
    development = load_r3_development_config(
        __import__("pathlib").Path("config.r3-development.yaml")
    )
    decisions = monthly_decision_dates(market.sessions)
    first = next(day for day in decisions if market.sessions.index(day) >= 252)
    breach_day = market.sessions[market.sessions.index(first) + 30]
    shocked_bars = tuple(
        R3MarketBar(
            row.security_id,
            row.session,
            row.open_usd * 2,
            row.close_usd * 2,
            row.adjusted_close * 2,
            row.volume,
        )
        if row.security_id == "AAA" and row.session >= breach_day
        else row
        for row in market.bars
    )
    shocked = R3MarketData(
        market.sessions,
        market.week_ends,
        market.benchmark_id,
        shocked_bars,
        market.actions,
        market.fx,
    )
    scores = {day: {"AAA": 1.0} for day in decisions if day >= first}
    result = simulate_r3_account(
        candidate_id="R3-M",
        scores_by_decision=scores,
        market=shocked,
        config=config,
        development=development,
        first_decision=first,
    )
    assert result.failure is None
    assert any(
        fill.side == "sell" and fill.mandatory and fill.decision_date >= breach_day
        for fill in result.fills
    )
