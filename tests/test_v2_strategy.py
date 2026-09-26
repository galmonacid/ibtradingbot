"""Exact V2 formation, scheduling, state, and configuration contracts."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.config.v2 import V2Config, load_v2_config, sensitivity_configs
from src.data.calendar import TradingCalendar
from src.strategy.ranking import RankedStock
from src.strategy.v2 import (
    V2Regime,
    completed_week_dates,
    rank_v2,
    select_v2,
    selection_dates,
    update_weekly_regime,
)


def fixture_calendar(count: int = 300) -> TradingCalendar:
    start = date(2023, 1, 3)
    dates = tuple(
        start + timedelta(days=offset)
        for offset in range(500)
        if (start + timedelta(days=offset)).weekday() < 5
    )[:count]
    return TradingCalendar("XNYS", "synthetic-test-only", dates, (), "fixture-hash")


def test_exact_endpoints_missing_sessions_and_prefix() -> None:
    calendar = fixture_calendar()
    prices = {day: 100 + index for index, day in enumerate(calendar.sessions)}
    day = calendar.sessions[252]
    result = rank_v2({"B": prices, "A": prices}, day, calendar, V2Config())
    assert [item.symbol for item in result.ranked] == ["A", "B"]
    assert result.ranked[0].score == pytest.approx(331 / 100 - 1)
    assert result == rank_v2(
        {"B": dict(list(prices.items())[:253]), "A": dict(list(prices.items())[:253])},
        day,
        calendar,
        V2Config(),
    )
    assert not rank_v2({"A": prices}, calendar.sessions[251], calendar, V2Config()).ranked
    del prices[calendar.sessions[10]]
    excluded = rank_v2({"A": prices}, day, calendar, V2Config())
    assert excluded.exclusions[0].reason == "missing_exchange_session"


def test_holiday_boundaries_and_truncated_period() -> None:
    sessions = (date(2024, 3, 27), date(2024, 3, 28), date(2024, 4, 1), date(2024, 4, 2))
    calendar = TradingCalendar("XNYS", "good-friday", sessions, (), "fixture")
    assert selection_dates(calendar, V2Config()) == (date(2024, 3, 28),)
    assert completed_week_dates(calendar) == (date(2024, 3, 28),)
    assert selection_dates(
        calendar, replace(V2Config(), selection_schedule="penultimate_monthly")
    ) == (date(2024, 3, 27),)
    assert selection_dates(replace(calendar, sessions=sessions[:1]), V2Config()) == ()


def test_actual_fills_buffer_and_failed_entry() -> None:
    ranked = tuple(RankedStock(str(index), index, 1 / index) for index in range(1, 10))
    result = select_v2(ranked, {"5": 1, "6": 1, "7": 1, "8": 1}, V2Config())
    assert tuple(item.symbol for item in result.selected) == ("5", "6", "7", "8")
    result = select_v2(ranked, {"5": 1, "6": 1, "7": 1, "8": 0}, V2Config())
    assert tuple(item.symbol for item in result.selected) == ("1", "5", "6", "7")
    with pytest.raises(ValueError):
        select_v2(ranked, {"1": -1}, V2Config())


def test_weekly_regime_timing_and_missing_inputs() -> None:
    calendar = fixture_calendar()
    prices = {day: 100 + index for index, day in enumerate(calendar.sessions)}
    friday = next(day for day in completed_week_dates(calendar) if day >= calendar.sessions[200])
    state = update_weekly_regime(V2Regime(), prices, friday, calendar, V2Config())
    assert state.ceiling == 0.98 and state.valid
    index = calendar.sessions.index(friday)
    monday = calendar.sessions[index + 1]
    prices[monday] = 1
    assert update_weekly_regime(state, prices, monday, calendar, V2Config()) == state
    next_friday = calendar.sessions[index + 5]
    prices[next_friday] = 1
    off = update_weekly_regime(state, prices, next_friday, calendar, V2Config())
    assert off.ceiling == 0 and off.valid
    del prices[next_friday]
    missing = update_weekly_regime(state, prices, next_friday, calendar, V2Config())
    assert missing.ceiling == state.ceiling and not missing.valid


def test_strict_config_and_fixed_sensitivity(tmp_path: Path) -> None:
    assert load_v2_config(Path("config.phase3-v2.yaml")) == V2Config(max_fx_age_days=6)
    assert len(sensitivity_configs(date(2024, 1, 5))) == 16
    for kwargs in (
        {"hard_drawdown": 0.16},
        {"target_positions": True},
        {"cash_buffer": float("nan")},
        {"max_position_weight": 0.31},
        {"selection_schedule": "biweekly"},
        {"slippage_bps": 0},
    ):
        with pytest.raises(ValueError):
            V2Config(**kwargs)
    config_path = tmp_path / "config.yaml"
    for content in (
        "strategy_version: monthly-momentum-v2\nunknown: 1\n",
        "strategy_version: monthly-momentum-v2\ncash_buffer: .02\ncash_buffer: .1\n",
        "target_positions: 4\n",
    ):
        config_path.write_text(content)
        with pytest.raises(ValueError):
            load_v2_config(config_path)


def test_biweekly_anchor_is_explicit_and_stable() -> None:
    calendar = fixture_calendar()
    weeks = completed_week_dates(calendar)
    config = replace(V2Config(), selection_schedule="biweekly", biweekly_anchor=weeks[2])
    assert selection_dates(calendar, config) == weeks[2::2]
    assert len({item.sha256 for _, item in sensitivity_configs(weeks[2])}) == 16
    with pytest.raises(ValueError, match="anchor"):
        selection_dates(calendar, replace(config, biweekly_anchor=calendar.sessions[0]))


def test_signal_filters_fail_closed() -> None:
    calendar = fixture_calendar()
    prices = {day: 100.0 for day in calendar.sessions}
    as_of = calendar.sessions[252]
    assert (
        rank_v2({"A": prices}, as_of, calendar, V2Config()).exclusions[0].reason
        == "nonpositive_momentum"
    )
    prices[calendar.sessions[231]] = 120
    assert (
        rank_v2({"A": prices}, as_of, calendar, V2Config()).exclusions[0].reason
        == "price_not_above_stock_sma"
    )
    prices[as_of] = float("nan")
    assert (
        rank_v2({"A": prices}, as_of, calendar, V2Config()).exclusions[0].reason
        == "invalid_adjusted_close"
    )
