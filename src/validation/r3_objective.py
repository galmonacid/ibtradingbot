"""Exact one-year GBP objective accounting for R3."""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class R3WealthPoint:
    session: date
    gross_wealth_gbp: float
    commissions_gbp: float = 0.0
    regulatory_fees_gbp: float = 0.0
    spread_slippage_gbp: float = 0.0
    fx_costs_gbp: float = 0.0
    account_charges_gbp: float = 0.0
    withholding_gbp: float = 0.0
    recurring_operating_gbp: float = 0.0
    research_from_capital_gbp: float = 0.0
    research_outside_capital_gbp: float = 0.0
    liquidation_reserve_gbp: float = 0.0
    external_flow_gbp: float = 0.0
    unsettled_cash_gbp: float = 0.0
    nonspendable_accrual_gbp: float = 0.0
    unresolved_held_valuation: bool = False

    def __post_init__(self) -> None:
        numeric = tuple(
            value
            for name, value in vars(self).items()
            if name not in ("session", "unresolved_held_valuation")
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("wealth components must be finite")
        costs = numeric[1:11]
        if any(value < 0 for value in costs):
            raise ValueError("cost and reserve components must be nonnegative")


@dataclass(frozen=True)
class R3ObjectiveResult:
    status: Literal["passed", "failed", "blocked"]
    inception: date
    anniversary: date
    endpoint: date | None
    initial_capital_gbp: float
    gross_wealth_gbp: float | None
    trading_net_wealth_gbp: float | None
    all_in_wealth_gbp: float | None
    economic_wealth_gbp: float | None
    net_profit_gbp: float | None
    return_12m: float | None
    objective_met: bool
    cost_bridge_gbp: dict[str, float]
    unsettled_cash_gbp: float | None
    nonspendable_accrual_gbp: float | None
    blockers: tuple[str, ...]


def _anniversary(value: date) -> date:
    day = min(value.day, calendar.monthrange(value.year + 1, value.month)[1])
    return date(value.year + 1, value.month, day)


def evaluate_r3_objective(
    points: tuple[R3WealthPoint, ...],
    *,
    inception: date,
    initial_capital_gbp: float = 3000.0,
) -> R3ObjectiveResult:
    """Evaluate the last session on/before the fixed 12-calendar-month endpoint."""
    if initial_capital_gbp != 3000:
        raise ValueError("R3 objective must use exactly £3,000 initial capital")
    if not points or tuple(sorted({point.session for point in points})) != tuple(
        point.session for point in points
    ):
        raise ValueError("wealth points must be non-empty, unique and increasing")
    anniversary = _anniversary(inception)
    eligible = tuple(point for point in points if inception <= point.session <= anniversary)
    endpoint = eligible[-1] if eligible else None
    blockers: list[str] = []
    if endpoint is None:
        blockers.append("no_exchange_session_on_or_before_12_month_anniversary")
    elif endpoint.session == inception:
        blockers.append("no_post_inception_endpoint")
    if points[-1].session < anniversary:
        blockers.append("history_does_not_reach_12_month_anniversary")
    if any(point.external_flow_gbp != 0 for point in eligible):
        blockers.append("external_funding_or_withdrawal_present")
    if endpoint is not None and endpoint.unresolved_held_valuation:
        blockers.append("unresolved_held_asset_valuation")
    if blockers or endpoint is None:
        return R3ObjectiveResult(
            "blocked",
            inception,
            anniversary,
            None if endpoint is None else endpoint.session,
            initial_capital_gbp,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            {},
            None if endpoint is None else endpoint.unsettled_cash_gbp,
            None if endpoint is None else endpoint.nonspendable_accrual_gbp,
            tuple(sorted(blockers)),
        )
    trading_costs = (
        endpoint.commissions_gbp
        + endpoint.regulatory_fees_gbp
        + endpoint.spread_slippage_gbp
        + endpoint.fx_costs_gbp
    )
    fixed_costs = (
        endpoint.account_charges_gbp
        + endpoint.withholding_gbp
        + endpoint.recurring_operating_gbp
        + endpoint.research_from_capital_gbp
    )
    trading_net = endpoint.gross_wealth_gbp - trading_costs
    all_in = trading_net - fixed_costs - endpoint.liquidation_reserve_gbp
    economic = all_in - endpoint.research_outside_capital_gbp
    profit = all_in - initial_capital_gbp
    r12 = all_in / initial_capital_gbp - 1
    objective_met = r12 > 0.10 and profit > 300 and all_in > 3300
    bridge = {
        "commissions": endpoint.commissions_gbp,
        "regulatory_fees": endpoint.regulatory_fees_gbp,
        "spread_slippage": endpoint.spread_slippage_gbp,
        "fx_costs": endpoint.fx_costs_gbp,
        "account_charges": endpoint.account_charges_gbp,
        "withholding": endpoint.withholding_gbp,
        "recurring_operating": endpoint.recurring_operating_gbp,
        "research_from_capital": endpoint.research_from_capital_gbp,
        "liquidation_reserve": endpoint.liquidation_reserve_gbp,
        "research_outside_capital": endpoint.research_outside_capital_gbp,
    }
    return R3ObjectiveResult(
        "passed" if objective_met else "failed",
        inception,
        anniversary,
        endpoint.session,
        initial_capital_gbp,
        endpoint.gross_wealth_gbp,
        trading_net,
        all_in,
        economic,
        profit,
        r12,
        objective_met,
        bridge,
        endpoint.unsettled_cash_gbp,
        endpoint.nonspendable_accrual_gbp,
        (),
    )
