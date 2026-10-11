"""Accounting identities and failure boundaries, not strategy-performance tests."""

from dataclasses import replace
from datetime import date

import pytest

from src.data.r3_adjustments import (
    AdjustmentEvent,
    adjustment_context_keys,
    check_adjustment_pair,
)
from src.data.semantic_certification import CanonicalBar

PREVIOUS = date(2024, 1, 5)
CURRENT = date(2024, 1, 8)


def test_first_membership_day_action_keeps_prior_bar_as_context_only() -> None:
    members = frozenset({("S", CURRENT)})
    bars = {
        ("S", PREVIOUS): CanonicalBar("S", PREVIOUS, 100, 50),
        ("S", CURRENT): CanonicalBar("S", CURRENT, 110, 60),
    }
    context = adjustment_context_keys(members, sessions=(PREVIOUS, CURRENT))
    assert set(bars) == context
    assert ("S", PREVIOUS) not in members
    assert check_adjustment_pair(
        bars[("S", PREVIOUS)], bars[("S", CURRENT)],
        AdjustmentEvent("S", CURRENT, distribution_amount=10),
        previous_session=PREVIOUS, relative_tolerance=1e-12, absolute_tolerance=1e-12,
    ).consistent
    # Selecting a required key never fabricates its absent source observation.
    del bars[("S", PREVIOUS)]
    assert context - bars.keys() == {("S", PREVIOUS)}


@pytest.mark.parametrize(
    "sessions,day",
    [((CURRENT,), CURRENT), ((CURRENT, PREVIOUS), CURRENT),
     ((PREVIOUS, CURRENT, CURRENT), CURRENT), ((PREVIOUS, CURRENT), date(2024, 1, 6))],
)
def test_context_rejects_missing_predecessor_and_invalid_calendar(
    sessions: tuple[date, ...], day: date,
) -> None:
    with pytest.raises(ValueError):
        adjustment_context_keys(frozenset({("S", day)}), sessions=sessions)


def test_dividend_reconciles_one_share_total_wealth_not_prior_close_discount() -> None:
    # One share rises from 100 to 110 and distributes 10: total wealth is 120.
    before = CanonicalBar("S", PREVIOUS, 100, 50)
    after = CanonicalBar("S", CURRENT, 110, 60)
    result = check_adjustment_pair(
        before, after, AdjustmentEvent("S", CURRENT, distribution_amount=10),
        previous_session=PREVIOUS, relative_tolerance=1e-12, absolute_tolerance=1e-12,
    )
    assert result.consistent
    assert result.expected == pytest.approx(120 / 110)
    assert result.expected != pytest.approx(100 / 90)


@pytest.mark.parametrize("ratio,price", [(2.0, 50.0), (0.1, 1000.0)])
def test_split_and_reverse_split_preserve_wealth(ratio: float, price: float) -> None:
    result = check_adjustment_pair(
        CanonicalBar("S", PREVIOUS, 100, 25), CanonicalBar("S", CURRENT, price, 25),
        AdjustmentEvent("S", CURRENT, split_ratio=ratio),
        previous_session=PREVIOUS, relative_tolerance=1e-12, absolute_tolerance=1e-12,
    )
    assert result.consistent


def test_combined_action_units_must_be_explicit_and_equivalent() -> None:
    before = CanonicalBar("S", PREVIOUS, 100, 50)
    after = CanonicalBar("S", CURRENT, 50, 52)
    event = AdjustmentEvent("S", CURRENT, 2, 4, "pre_split_share")
    kwargs = dict(previous_session=PREVIOUS, relative_tolerance=1e-12, absolute_tolerance=1e-12)
    pre = check_adjustment_pair(before, after, event, **kwargs)
    post = check_adjustment_pair(
        before, after, replace(event, distribution_amount=2, cash_basis="post_split_share"),
        **kwargs,
    )
    assert pre == post
    assert pre.consistent
    with pytest.raises(ValueError, match="explicit share units"):
        check_adjustment_pair(before, after, replace(event, cash_basis=None), **kwargs)


def test_unexplained_adjustment_is_not_consistent() -> None:
    result = check_adjustment_pair(
        CanonicalBar("S", PREVIOUS, 100, 50), CanonicalBar("S", CURRENT, 100, 55),
        AdjustmentEvent("S", CURRENT), previous_session=PREVIOUS,
        relative_tolerance=1e-5, absolute_tolerance=1e-8,
    )
    assert not result.consistent


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 0.0, -1.0])
def test_invalid_prices_rejected(invalid: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        check_adjustment_pair(
            CanonicalBar("S", PREVIOUS, invalid, 50), CanonicalBar("S", CURRENT, 100, 50),
            AdjustmentEvent("S", CURRENT), previous_session=PREVIOUS,
            relative_tolerance=1e-5, absolute_tolerance=1e-8,
        )


def test_identity_event_date_and_stale_bar_mismatches_rejected() -> None:
    before = CanonicalBar("S", PREVIOUS, 100, 50)
    after = CanonicalBar("S", CURRENT, 100, 50)
    event = AdjustmentEvent("S", CURRENT)
    for b, a, e in [
        (before, replace(after, security_id="OTHER"), event),
        (before, after, replace(event, session=PREVIOUS)),
        (replace(before, session=date(2024, 1, 4)), after, event),
    ]:
        with pytest.raises(ValueError):
            check_adjustment_pair(
                b, a, e, previous_session=PREVIOUS,
                relative_tolerance=1e-5, absolute_tolerance=1e-8,
            )


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf"), -0.1])
def test_invalid_tolerance_cannot_bypass_check(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerances"):
        check_adjustment_pair(
            CanonicalBar("S", PREVIOUS, 100, 50), CanonicalBar("S", CURRENT, 100, 50),
            AdjustmentEvent("S", CURRENT), previous_session=PREVIOUS,
            relative_tolerance=tolerance, absolute_tolerance=1e-8,
        )
