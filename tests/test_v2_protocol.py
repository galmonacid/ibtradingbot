"""V2 guards reject inspected history, changed identities and manufactured episodes."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from src.data.calendar import TradingCalendar
from src.validation.v2_protocol import (
    BOUND_IDENTITIES,
    FIXED_SENSITIVITIES,
    PositionEpisode,
    PositionFill,
    SensitivityMetrics,
    V2FreezeManifest,
    assess_v2_robustness,
    completed_position_episodes,
    validate_fresh_window,
)


def test_fixed_neighbors_require_13_and_every_axis() -> None:
    metrics = {item.name: SensitivityMetrics(0.06, 0.6, 0.15) for item in FIXED_SENSITIVITIES}
    assert len(metrics) == 16
    assert assess_v2_robustness(metrics).passed
    for item in FIXED_SENSITIVITIES[::2][:3]:
        del metrics[item.name]
    assert assess_v2_robustness(metrics).passed
    del metrics[FIXED_SENSITIVITIES[6].name]
    assert not assess_v2_robustness(metrics).passed
    metrics = {item.name: SensitivityMetrics(0.07, 0.8, 0.1) for item in FIXED_SENSITIVITIES}
    for item in FIXED_SENSITIVITIES[:2]:
        metrics[item.name] = SensitivityMetrics(1, 1, 0.1, executable=False)
    assert len(assess_v2_robustness(metrics).viable_variants) == 14
    assert assess_v2_robustness(metrics).failed_axes == ("target_positions",)
    metrics[FIXED_SENSITIVITIES[0].name] = SensitivityMetrics(float("nan"), 1, 0)
    assert not assess_v2_robustness(metrics).passed


def test_episodes_follow_actual_inventory_and_stable_identity() -> None:
    def fill(day: int, quantity: str, ticker: str = "OLD") -> PositionFill:
        return PositionFill("stable", date(2027, 1, day), Decimal(quantity), ticker)

    fills = (
        fill(1, "2"),
        fill(2, "-1"),
        fill(3, "3", "NEW"),
        fill(4, "-4", "NEW"),
        fill(5, "1", "NEW"),
        fill(6, "-1", "NEW"),
    )
    assert completed_position_episodes(fills, start=date(2027, 1, 1), end=date(2027, 1, 6)) == (
        PositionEpisode("stable", date(2027, 1, 1), date(2027, 1, 4)),
        PositionEpisode("stable", date(2027, 1, 5), date(2027, 1, 6)),
    )
    assert (
        len(completed_position_episodes(fills, start=date(2027, 1, 2), end=date(2027, 1, 6))) == 1
    )
    assert not completed_position_episodes(fills[:3], start=date(2027, 1, 1), end=date(2027, 1, 6))
    with pytest.raises(ValueError, match="short"):
        completed_position_episodes((fill(1, "-1"),), start=date(2027, 1, 1), end=date(2027, 1, 6))
    with pytest.raises(ValueError, match="chronological"):
        completed_position_episodes(
            (fill(2, "1"), fill(1, "1")), start=date(2027, 1, 1), end=date(2027, 1, 6)
        )


def fixture() -> tuple[V2FreezeManifest, TradingCalendar]:
    # Deliberately synthetic weekday calendar: this tests protocol accounting, not
    # real XNYS holiday accuracy or performance admissibility.
    days = tuple(date(2026, 9, 18) + timedelta(days=i) for i in range(1600))
    sessions = tuple(day for day in days if day.weekday() < 5)
    calendar = TradingCalendar("XNYS", "synthetic-test", sessions, (date(2026, 9, 18),), "a" * 64)
    freeze = V2FreezeManifest(
        datetime(2026, 9, 22, 20, tzinfo=UTC),
        "b" * 40,
        tuple((key, "a" * 64) for key in BOUND_IDENTITIES),
        date(2026, 9, 22),
        date(2026, 9, 18),
    )
    return freeze, calendar


def test_freeze_is_complete_immutable_and_deterministic() -> None:
    freeze, _ = fixture()
    assert len(freeze.sha256) == 64
    assert replace(freeze, identities=freeze.identities[::-1]).sha256 == freeze.sha256
    with pytest.raises(ValueError, match="every required"):
        replace(freeze, identities=freeze.identities[:-1])
    with pytest.raises(ValueError, match="timezone"):
        replace(freeze, frozen_at=datetime(2026, 9, 22))
    with pytest.raises(ValueError, match="protocol"):
        replace(freeze, sensitivities=freeze.sensitivities[:-1])
    with pytest.raises(ValueError, match="cutoff"):
        replace(freeze, data_cutoff=date(2026, 9, 23))


def test_fresh_window_first_endpoint_and_no_development_qualification() -> None:
    freeze, calendar = fixture()
    observed = tuple(
        day for day in calendar.sessions if date(2026, 9, 22) < day <= date(2029, 12, 31)
    )
    episodes = tuple(PositionEpisode(str(i), observed[0], observed[1]) for i in range(150))

    def evaluate(**overrides: object) -> object:
        # Explicit argument defaults permit mutation tests without changing frozen values.
        arguments = dict(
            development=False,
            freeze=freeze,
            actual_identities=dict(freeze.identities),
            actual_source_revision=freeze.source_revision,
            calendar=calendar,
            observed_sessions=observed,
            closed_lot_dates=(observed[1],) * 150,
            episodes=episodes,
        )
        arguments.update(overrides)
        return validate_fresh_window(**arguments)  # type: ignore[arg-type]

    assert not evaluate(episodes=(episodes[0],) * 150).eligible  # type: ignore[attr-defined]
    assert evaluate().eligible  # type: ignore[attr-defined]
    assert not evaluate(development=True).eligible  # type: ignore[attr-defined]
    assert not evaluate(freeze=None).eligible  # type: ignore[attr-defined]
    assert not evaluate(actual_source_revision="c" * 40).eligible  # type: ignore[attr-defined]
    assert not evaluate(actual_identities={}).eligible  # type: ignore[attr-defined]
    assert not evaluate(observed_sessions=observed[1:]).eligible  # type: ignore[attr-defined]
    assert not evaluate(observed_sessions=observed[:-1]).eligible  # type: ignore[attr-defined]
    assert not evaluate(episodes=episodes[:149]).eligible  # type: ignore[attr-defined]
    assert not evaluate(closed_lot_dates=(observed[1],) * 149).eligible  # type: ignore[attr-defined]
    extended = observed + (date(2030, 1, 1),)
    assert not evaluate(observed_sessions=extended).eligible  # type: ignore[attr-defined]
    shorter_calendar = replace(
        calendar, sessions=calendar.sessions[: calendar.sessions.index(observed[-1]) + 1]
    )
    assert not evaluate(calendar=shorter_calendar).eligible  # type: ignore[attr-defined]
