from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.data.calendar import CalendarError, load_trading_calendar, weekly_signal_dates
from src.data.corporate_actions import CorporateActionsError, load_corporate_actions

ROOT = Path(__file__).parents[1]


def test_versioned_fixture_calendar_drives_week_ends() -> None:
    calendar = load_trading_calendar(ROOT / "data/sample/us_sessions.csv")
    available = tuple(session for session in calendar.sessions if session <= date(2024, 7, 9))

    signals = weekly_signal_dates(available, calendar)

    assert calendar.exchange == "XNYS"
    assert calendar.version == "xnys-fixture-v1"
    assert signals[-1] == date(2024, 7, 5)
    assert date(2024, 3, 28) in signals  # Good Friday was not fabricated.


def test_calendar_rejects_weekend_and_incorrect_week_end_flags(tmp_path: Path) -> None:
    wrong_flag = tmp_path / "wrong.csv"
    wrong_flag.write_text(
        "exchange,version,date,is_week_end\n"
        "XNYS,test,2024-01-02,true\n"
        "XNYS,test,2024-01-03,false\n",
        encoding="utf-8",
    )
    with pytest.raises(CalendarError, match="exactly the final session"):
        load_trading_calendar(wrong_flag)

    weekend = tmp_path / "weekend.csv"
    weekend.write_text(
        "exchange,version,date,is_week_end\nXNYS,test,2024-01-06,true\n",
        encoding="utf-8",
    )
    with pytest.raises(CalendarError, match="weekend"):
        load_trading_calendar(weekend)

    short = tmp_path / "short-calendar.csv"
    short.write_text(
        "exchange,version,date,is_week_end\nXNYS,test,2024-01-02\n",
        encoding="utf-8",
    )
    with pytest.raises(CalendarError, match="malformed"):
        load_trading_calendar(short)


def test_corporate_action_loader_supports_empty_and_explicit_delistings(
    tmp_path: Path,
) -> None:
    empty = load_corporate_actions(ROOT / "data/sample/corporate_actions.csv")
    assert empty.delistings == ()

    path = tmp_path / "actions.csv"
    path.write_text(
        "date,symbol,event_type,cash_per_share\n2024-01-03,aaa,delisting,12.5\n",
        encoding="utf-8",
    )
    actions = load_corporate_actions(path)
    assert actions.delistings[0].symbol == "AAA"
    assert actions.delistings[0].cash_per_share == 12.5

    path.write_text(
        "date,symbol,event_type,cash_per_share\n2024-01-03,AAA,split,2\n",
        encoding="utf-8",
    )
    with pytest.raises(CorporateActionsError, match="unsupported"):
        load_corporate_actions(path)

    path.write_text(
        "date,symbol,event_type,cash_per_share\n2024-01-03,AAA,delisting\n",
        encoding="utf-8",
    )
    with pytest.raises(CorporateActionsError, match="malformed"):
        load_corporate_actions(path)
