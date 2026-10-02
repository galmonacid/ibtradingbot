from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from src.data.fx import FXHistory, FXObservation
from src.features.r3 import (
    MembershipEvidence,
    R3Action,
    R3FeatureRow,
    R3Price,
    build_r3_feature_rows,
    build_r3_labels,
)


def _weekdays(start: date, count: int) -> tuple[date, ...]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return tuple(result)


def _stamp(day: date, hour: int = 21) -> datetime:
    return datetime.combine(day, time(hour), UTC)


def _price(symbol: str, day: date, index: int, *, open_usd: float | None = None) -> R3Price:
    close = 100 + index * (0.07 if symbol == "SPY" else 0.1)
    return R3Price(
        symbol,
        day,
        close if open_usd is None else open_usd,
        close,
        close,
        3_000_000,
        _stamp(day, 14),
        _stamp(day),
        f"{symbol}-raw-v1",
        f"{symbol}-adjusted-v1",
    )


def test_future_price_append_does_not_mutate_existing_feature_rows() -> None:
    sessions = _weekdays(date(2023, 1, 2), 280)
    prices = tuple(
        _price(symbol, day, index)
        for symbol in ("AAA", "SPY")
        for index, day in enumerate(sessions)
    )
    membership = (
        MembershipEvidence("AAA", sessions[0], None, _stamp(sessions[0]), True, "pit-v1"),
    )
    prefix_sessions = sessions[:270]
    prefix_prices = tuple(row for row in prices if row.session in set(prefix_sessions))

    prefix = build_r3_feature_rows(
        prefix_prices, membership, sessions, benchmark_id="SPY"
    )
    extended = build_r3_feature_rows(prices, membership, sessions, benchmark_id="SPY")

    assert prefix
    assert tuple(row for row in extended if row.decision_date <= prefix[-1].decision_date) == prefix
    assert all(len(row.values) == 12 for row in prefix)


def _fx(days: tuple[date, ...], rates: dict[date, float] | None = None) -> FXHistory:
    observations = tuple(
        FXObservation(_stamp(day, 9), _stamp(day, 9), (rates or {}).get(day, 0.8))
        for day in days
    )
    return FXHistory(observations, "fixture", "test-only", "0" * 64, synthetic=True)


def _usable_row(security_id: str, decision: date) -> R3FeatureRow:
    return R3FeatureRow(
        security_id,
        decision,
        _stamp(decision),
        _stamp(decision),
        decision,
        None,
        "raw-v1",
        "adjusted-v1",
        tuple(float(index) for index in range(12)),
        (),
        "r3-stock-month-v1",
    )


def test_label_uses_causal_fx_and_paid_action_cash() -> None:
    sessions = (date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), date(2024, 3, 1))
    prices = (
        _price("AAA", sessions[1], 0, open_usd=100),
        _price("AAA", sessions[3], 0, open_usd=110),
        _price("SPY", sessions[1], 0, open_usd=100),
        _price("SPY", sessions[3], 0, open_usd=100),
    )
    payment = datetime(2024, 2, 20, 9, tzinfo=UTC)
    action = R3Action(
        "AAA",
        "dividend",
        datetime(2024, 2, 15, 9, tzinfo=UTC),
        datetime(2024, 3, 5, 9, tzinfo=UTC),
        2.0,
        payment_at=payment,
        withholding_fraction=0.25,
    )
    fx_days = (sessions[1], date(2024, 2, 20), sessions[3])
    fx = _fx(fx_days, {sessions[1]: 0.8, date(2024, 2, 20): 0.7, sessions[3]: 0.6})

    labels = build_r3_labels(
        (_usable_row("AAA", sessions[0]),), prices, (action,), fx, sessions, benchmark_id="SPY"
    )

    assert labels[0].matured
    # AAA: (110*0.6 + 2*(1-.25)*0.7)/(100*0.8)-1; SPY: 100*0.6/(100*0.8)-1.
    assert labels[0].excess_return_gbp == pytest.approx((67.05 / 80 - 1) - (60 / 80 - 1))
    assert labels[0].available_at == datetime(2024, 3, 5, 9, tzinfo=UTC)


def test_missing_exit_requires_explicit_delisting_recovery() -> None:
    sessions = (date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), date(2024, 3, 1))
    prices = (
        _price("AAA", sessions[1], 0, open_usd=100),
        _price("SPY", sessions[1], 0, open_usd=100),
        _price("SPY", sessions[3], 0, open_usd=100),
    )
    fx = _fx((sessions[1], date(2024, 2, 20), sessions[3]))

    unresolved = build_r3_labels(
        (_usable_row("AAA", sessions[0]),), prices, (), fx, sessions, benchmark_id="SPY"
    )[0]
    assert not unresolved.matured
    assert unresolved.unresolved_reason == "missing_exit_or_delisting_recovery"

    future_recovery = R3Action(
        "AAA",
        "delisting",
        datetime(2024, 3, 5, 9, tzinfo=UTC),
        datetime(2024, 3, 5, 16, tzinfo=UTC),
        40.0,
        payment_at=datetime(2024, 3, 5, 16, tzinfo=UTC),
        withholding_fraction=0.0,
    )
    still_unresolved = build_r3_labels(
        (_usable_row("AAA", sessions[0]),),
        prices,
        (future_recovery,),
        fx,
        sessions,
        benchmark_id="SPY",
    )[0]
    assert still_unresolved.unresolved_reason == "missing_exit_or_delisting_recovery"

    recovery = R3Action(
        "AAA",
        "delisting",
        datetime(2024, 2, 15, 9, tzinfo=UTC),
        datetime(2024, 2, 15, 9, tzinfo=UTC),
        40.0,
        payment_at=datetime(2024, 2, 20, 9, tzinfo=UTC),
        withholding_fraction=0.0,
    )
    resolved = build_r3_labels(
        (_usable_row("AAA", sessions[0]),), prices, (recovery,), fx, sessions, benchmark_id="SPY"
    )[0]
    assert resolved.matured
    assert resolved.excess_return_gbp is not None


def test_membership_end_is_exclusive_and_unavailable_cash_action_is_retained() -> None:
    evidence = MembershipEvidence(
        "AAA",
        date(2024, 1, 1),
        date(2024, 2, 1),
        datetime(2024, 1, 1, 16, tzinfo=UTC),
        True,
        "pit-v1",
    )
    assert evidence.active(date(2024, 1, 31), datetime(2024, 1, 31, 21, tzinfo=UTC))
    assert not evidence.active(date(2024, 2, 1), datetime(2024, 2, 1, 21, tzinfo=UTC))

    sessions = (date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), date(2024, 3, 1))
    prices = (
        _price("AAA", sessions[1], 0, open_usd=100),
        _price("AAA", sessions[3], 0, open_usd=102),
        _price("SPY", sessions[1], 0, open_usd=100),
        _price("SPY", sessions[3], 0, open_usd=100),
    )
    action = R3Action(
        "AAA",
        "dividend",
        datetime(2024, 2, 15, 9, tzinfo=UTC),
        datetime(2024, 2, 15, 16, tzinfo=UTC),
        1.0,
        payment_at=None,
        withholding_fraction=None,
    )
    labels = build_r3_labels(
        (
            _usable_row("AAA", sessions[0]),
            _usable_row("AAA", sessions[2]),
        ),
        prices,
        (action,),
        _fx((sessions[1], sessions[3])),
        sessions,
        benchmark_id="SPY",
    )

    assert labels[0].unresolved_reason == "cash_action_payment_date_unavailable"
    assert labels[1].unresolved_reason == "label_horizon_not_complete"
