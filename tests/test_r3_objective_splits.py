from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.features.r3 import R3Label
from src.validation.r3_objective import R3WealthPoint, evaluate_r3_objective
from src.validation.r3_splits import (
    build_r3_scoring_assignments,
    build_r3_split_assignments,
)


def test_one_year_endpoint_is_strict_and_cost_bridge_conserves_wealth() -> None:
    points = (
        R3WealthPoint(date(2024, 1, 3), 3000),
        R3WealthPoint(
            date(2025, 1, 3),
            3341.0,
            commissions_gbp=5,
            regulatory_fees_gbp=1,
            spread_slippage_gbp=4,
            fx_costs_gbp=2,
            account_charges_gbp=36,
            recurring_operating_gbp=1,
            liquidation_reserve_gbp=2,
            research_outside_capital_gbp=10,
            unsettled_cash_gbp=3,
            nonspendable_accrual_gbp=4,
        ),
        R3WealthPoint(date(2025, 1, 6), 9999),
    )

    result = evaluate_r3_objective(points, inception=date(2024, 1, 3))

    assert result.endpoint == date(2025, 1, 3)
    assert result.trading_net_wealth_gbp == 3329
    assert result.all_in_wealth_gbp == 3290
    assert result.economic_wealth_gbp == 3280
    assert sum(result.cost_bridge_gbp.values()) == 61
    assert result.status == "failed"
    assert result.objective_met is False


def test_exactly_ten_percent_fails_but_strictly_more_passes() -> None:
    base = (R3WealthPoint(date(2024, 1, 2), 3000),)
    exact = evaluate_r3_objective(
        base + (R3WealthPoint(date(2025, 1, 2), 3300),), inception=date(2024, 1, 2)
    )
    above = evaluate_r3_objective(
        base + (R3WealthPoint(date(2025, 1, 2), 3300.01),), inception=date(2024, 1, 2)
    )

    assert exact.status == "failed"
    assert above.status == "passed"


@pytest.mark.parametrize(
    "endpoint, blocker",
    [
        (
            R3WealthPoint(date(2025, 1, 2), 3400, external_flow_gbp=1),
            "external_funding_or_withdrawal_present",
        ),
        (
            R3WealthPoint(date(2025, 1, 2), 3400, unresolved_held_valuation=True),
            "unresolved_held_asset_valuation",
        ),
    ],
)
def test_objective_fails_closed_on_invalid_account_evidence(
    endpoint: R3WealthPoint, blocker: str
) -> None:
    result = evaluate_r3_objective(
        (R3WealthPoint(date(2024, 1, 2), 3000), endpoint), inception=date(2024, 1, 2)
    )
    assert result.status == "blocked"
    assert blocker in result.blockers


def _label(symbol: str, decision: date, exit_day: date, *, matured: bool = True) -> R3Label:
    entry = datetime.combine(decision, datetime.min.time(), UTC)
    exit_at = datetime.combine(exit_day, datetime.min.time(), UTC)
    return R3Label(
        symbol,
        decision,
        entry,
        exit_at,
        exit_at if matured else None,
        0.01 if matured else None,
        None if matured else "unresolved",
        "r3-gbp-open-to-open-excess-v1",
    )


def test_splits_keep_dates_together_and_purge_actual_label_overlap() -> None:
    sessions = tuple(date(2007, 1, 1) + timedelta(days=index) for index in range(12 * 366))
    labels = (
        _label("AAA", date(2014, 9, 1), date(2014, 9, 30)),
        _label("BBB", date(2014, 9, 1), date(2014, 9, 30)),
        _label("PURGED", date(2014, 11, 1), date(2014, 12, 15)),
        _label("IMMATURE", date(2014, 8, 1), date(2014, 8, 31), matured=False),
    )
    assignments = build_r3_split_assignments(
        labels,
        sessions,
        verified_complete_through=sessions[-1],
        as_of=datetime(2030, 1, 1, tzinfo=UTC),
    )

    first_train = [row for row in assignments if row.fold_id == 0 and row.split == "train"]
    assert [(row.security_id, row.decision_date) for row in first_train] == [
        ("AAA", date(2014, 9, 1)),
        ("BBB", date(2014, 9, 1)),
    ]
    assert all(row.security_id != "PURGED" for row in first_train)
    assert all(row.security_id != "IMMATURE" for row in assignments)


def test_scoring_assignments_keep_same_date_features_independent_of_labels() -> None:
    sessions = tuple(date(2007, 1, 1) + timedelta(days=index) for index in range(12 * 366))
    decision = date(2017, 6, 1)
    keys = (("MATURED", decision), ("UNRESOLVED", decision))

    assignments = build_r3_scoring_assignments(
        keys,
        sessions,
        verified_complete_through=sessions[-1],
    )

    matching = [row for row in assignments if row.decision_date == decision]
    assert matching
    by_fold = {
        row.fold_id: [member for member in matching if member.fold_id == row.fold_id]
        for row in matching
    }
    assert all(
        {row.security_id for row in fold_rows} == {"MATURED", "UNRESOLVED"}
        and len({row.split for row in fold_rows}) == 1
        for fold_rows in by_fold.values()
    )
