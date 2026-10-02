"""R3.1 cost, exposure and causal eligibility attribution.

This module audits retained development evidence and constructs flat-account
execution-feasibility plans. It does not simulate R3 returns or qualify a model.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from src.config.r3_feasibility import R3FeasibilityConfig
from src.data.calendar import TradingCalendar
from src.data.canonical_historical import VerifiedCanonicalInputs
from src.portfolio.v2 import build_v2_targets, estimate_dual_covariance
from src.validation.v2_report import summarize_v2_run


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result


def _validate_ledger(ledger: Mapping[str, Any], config: R3FeasibilityConfig) -> None:
    if _finite(ledger.get("initial_capital_gbp"), "initial capital") != config.initial_capital_gbp:
        raise ValueError("R3.1 requires the retained £3,000 ledger")
    if ledger.get("fractional") is not False:
        raise ValueError("legacy ledger must prove whole-share accounting")
    points = ledger.get("points")
    if not isinstance(points, list) or not points:
        raise ValueError("ledger needs daily account points")
    dates = [date.fromisoformat(str(point["date"])) for point in points]
    if dates != sorted(set(dates)):
        raise ValueError("ledger points must be uniquely chronological")
    for fill in ledger.get("fills", []):
        if date.fromisoformat(str(fill["date"])) <= date.fromisoformat(str(fill["signal_date"])):
            raise ValueError("ledger contains a non-causal fill")
        shares = _finite(fill["shares"], "fill shares")
        if shares <= 0 or not shares.is_integer():
            raise ValueError("ledger fill is not a positive whole-share quantity")


def _source_execution_audit(
    ledger: Mapping[str, Any], legacy_report: Mapping[str, Any] | None
) -> dict[str, Any]:
    if legacy_report is None:
        return {"verified": False, "reason": "content-bound parent report not supplied"}
    scenario = legacy_report.get("scenarios", {}).get("gbp3000/baseline", {})
    audit = scenario.get("execution_audit", {})
    expected = _digest(ledger)
    audit_expected = hashlib.sha256(
        json.dumps(ledger, sort_keys=True, default=str, allow_nan=False).encode()
    ).hexdigest()
    if scenario.get("status") != "executed":
        raise ValueError("parent report does not contain an executed £3,000 baseline")
    if scenario.get("ledger_sha256") != expected:
        raise ValueError("parent report does not bind the supplied £3,000 ledger")
    if audit.get("passed") is not True or audit.get("findings") != []:
        raise ValueError("parent report execution audit is not passing")
    if audit.get("ledger_sha256") != audit_expected:
        raise ValueError("parent execution audit does not bind the supplied ledger")
    return {
        "verified": True,
        "parent_run_id": legacy_report.get("run_id"),
        "content_ledger_sha256": expected,
        "trading_fills": audit.get("trading_fills"),
        "reconciled_sessions": audit.get("reconciled_sessions"),
    }


def _ledger_attribution(
    ledger: Mapping[str, Any], source_execution_audit: Mapping[str, Any]
) -> dict[str, Any]:
    summary = summarize_v2_run(ledger, include_bootstrap=False)
    points = ledger["points"]
    fills_by_signal: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for fill in ledger.get("fills", []):
        if fill.get("reason") != "delisting_recovery":
            fills_by_signal[str(fill["signal_date"])].append(fill)
    skips_by_signal: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    decision_status: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for decision in ledger.get("decisions", []):
        signal = str(decision["signal_date"])
        decision_status[signal][str(decision["status"])] += 1
        skips_by_signal[signal].extend(decision.get("skips", []))
    exclusions_by_date: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in ledger.get("exclusions", []):
        exclusions_by_date[str(row["date"])][str(row["reason"])] += 1
    point_by_date = {str(point["date"]): point for point in points}
    # Retain every account date so exposure and halted time are attributable even
    # when no selection/order event occurred on that session.
    event_dates = sorted(point_by_date)
    daily = []
    for day in event_dates:
        point = point_by_date.get(day, {})
        daily.append(
            {
                "date": day,
                "exclusions": dict(sorted(exclusions_by_date[day].items())),
                "decision_status": dict(sorted(decision_status[day].items())),
                "skips": dict(
                    sorted(Counter(str(item["reason"]) for item in skips_by_signal[day]).items())
                ),
                "actual_fills": len(fills_by_signal[day]),
                "gross_exposure": _finite(point.get("gross_exposure", 0), "gross exposure"),
                "regime": point.get("regime"),
                "hard_halted": bool(point.get("hard_halted", False)),
            }
        )
    gbp = summary["currencies"]["gbp"]
    cost_total = math.fsum(summary["costs"]["gbp"].values())
    terminal = _finite(points[-1]["equity_gbp"], "terminal wealth")
    fixed_fill_terminal = _finite(gbp["gross_fixed_fill_terminal_nav"], "gross terminal")
    return {
        "ledger_structure_validated": True,
        "source_execution_audit": dict(source_execution_audit),
        "ledger_reconciled": source_execution_audit["verified"],
        "start": points[0]["date"],
        "end": points[-1]["date"],
        "sessions": len(points),
        "initial_capital_gbp": ledger["initial_capital_gbp"],
        "terminal_wealth_gbp": terminal,
        "net_profit_gbp": terminal - _finite(ledger["initial_capital_gbp"], "initial capital"),
        "actual_fills": summary["orders"],
        "mean_exposure": summary["mean_exposure"],
        "all_cash_sessions": summary["all_cash_sessions"],
        "hard_halted_sessions": summary["hard_halted_sessions"],
        "first_hard_halt": summary["first_hard_halt"],
        "recorded_costs_gbp": summary["costs"]["gbp"],
        "recorded_cost_total_gbp": cost_total,
        "same_fill_gross_terminal_gbp": fixed_fill_terminal,
        "same_fill_gross_profit_gbp": fixed_fill_terminal
        - _finite(ledger["initial_capital_gbp"], "initial capital"),
        "same_fill_cost_drag_gbp": fixed_fill_terminal - terminal,
        "cost_bridge_note": gbp["gross_fixed_fill_note"],
        "exclusion_counts": summary["exclusion_counts_by_reason"],
        "daily_attribution": daily,
    }


def _membership_ids(canonical: VerifiedCanonicalInputs, day: date) -> set[str]:
    return {
        row.security_id
        for row in canonical.memberships
        if row.effective_from <= day and (row.effective_to is None or day < row.effective_to)
    }


def _round_trip_cost(
    notional_gbp: float,
    shares: int,
    gbp_per_usd: float,
    config: R3FeasibilityConfig,
) -> float:
    commission = max(config.commission_min_usd, shares * config.commission_per_share_usd)
    bps = 2 * (config.slippage_bps + config.fx_friction_bps + config.conversion_bps)
    return 2 * commission * gbp_per_usd + notional_gbp * bps / 10_000


def _sell_reserve(
    notional_gbp: float,
    shares: int,
    gbp_per_usd: float,
    config: R3FeasibilityConfig,
) -> float:
    commission = max(config.commission_min_usd, shares * config.commission_per_share_usd)
    bps = config.slippage_bps + config.fx_friction_bps + config.conversion_bps
    return commission * gbp_per_usd + notional_gbp * bps / 10_000


def _policy_funnel(
    ledger: Mapping[str, Any],
    canonical: VerifiedCanonicalInputs,
    calendar: TradingCalendar,
    config: R3FeasibilityConfig,
) -> dict[str, Any]:
    if calendar.exchange != "XNYS":
        raise ValueError("R3.1 requires a pinned XNYS calendar")
    sessions = calendar.sessions
    index_by_day = {day: index for index, day in enumerate(sessions)}
    bars: dict[str, dict[date, Any]] = defaultdict(dict)
    for row in canonical.bars:
        bars[row.security_id][row.date] = row
    benchmark_ids = {row.security_id for row in canonical.bars if row.symbol == "SPY"}
    if len(benchmark_ids) != 1:
        raise ValueError("canonical inputs must resolve SPY to one stable identity")
    benchmark_id = benchmark_ids.pop()
    points = {str(point["date"]): point for point in ledger["points"]}
    actual_fills_by_signal = Counter(
        str(fill["signal_date"])
        for fill in ledger.get("fills", [])
        if fill.get("reason") != "delisting_recovery"
    )
    skips_by_signal: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for decision in ledger.get("decisions", []):
        skips_by_signal[str(decision["signal_date"])].update(
            str(skip["reason"]) for skip in decision.get("skips", [])
        )
    signal_dates = sorted(
        {
            date.fromisoformat(str(row["date"])) for row in ledger.get("exclusions", [])
        }
        | {
            date.fromisoformat(str(row["signal_date"]))
            for row in ledger.get("decisions", [])
            if row.get("reason") == "monthly_selection"
        }
    )
    rows: list[dict[str, Any]] = []
    feasible_plan_count = 0
    feasible_order_count = 0
    for day in signal_dates:
        if day not in index_by_day or str(day) not in points:
            raise ValueError("funnel date is absent from the pinned calendar or ledger")
        index = index_by_day[day]
        history253 = sessions[max(0, index - 252) : index + 1]
        history20 = sessions[max(0, index - 19) : index + 1]
        active = _membership_ids(canonical, day) - {benchmark_id}
        data_ready: dict[str, tuple[list[float], float]] = {}
        raw_price: dict[str, tuple[list[float], float]] = {}
        for identity in sorted(active):
            security = bars.get(identity, {})
            if (
                len(history253) == 253
                and len(history20) == 20
                and all(session in security for session in history253)
                and all(
                    math.isfinite(security[session].adjusted_close)
                    and security[session].adjusted_close > 0
                    and math.isfinite(security[session].close)
                    and security[session].close > 0
                    and security[session].volume >= 0
                    for session in history253
                )
            ):
                adjusted = [security[session].adjusted_close for session in history253]
                adv = median(
                    security[session].close * security[session].volume for session in history20
                )
                data_ready[identity] = (adjusted, adv)
                if security[day].close >= config.minimum_price_usd:
                    raw_price[identity] = (adjusted, adv)
        legacy_liquid = {
            identity: values
            for identity, values in raw_price.items()
            if values[1] >= config.legacy_liquidity_usd
        }
        r3_liquid = {
            identity: values
            for identity, values in raw_price.items()
            if values[1] >= config.r3_liquidity_usd
        }
        legacy_signal = {
            identity: values
            for identity, values in legacy_liquid.items()
            if values[0][-22] / values[0][0] - 1 > 0
            and values[0][-1] > math.fsum(values[0][-200:]) / 200
        }
        scores = {
            identity: values[0][-22] / values[0][0] - 1
            for identity, values in r3_liquid.items()
        }
        ranked = sorted(scores, key=lambda identity: (-scores[identity], identity))
        selected = ranked[: config.target_positions]
        point = points[str(day)]
        risk_on = point["regime"] == "risk_on" and not point["hard_halted"]
        plan_orders: list[dict[str, Any]] = []
        plan_reason: str | None = None
        next_day = sessions[index + 1] if index + 1 < len(sessions) else None
        if risk_on and selected and next_day is not None:
            try:
                covariance = estimate_dual_covariance(
                    {identity: r3_liquid[identity][0][-64:] for identity in selected},
                    longer_window=63,
                )
                weights = build_v2_targets(
                    selected,
                    covariance,
                    regime_ceiling=1 - config.cash_buffer,
                    cash_buffer=config.cash_buffer,
                    target_annual_volatility=config.volatility_ceiling,
                    max_position_weight=config.max_position_weight,
                )
                gbp_per_usd = _finite(point["equity_gbp"], "GBP NAV") / _finite(
                    point["equity_usd"], "USD NAV"
                )
                for identity in selected:
                    next_bar = bars.get(identity, {}).get(next_day)
                    weight = weights.get(identity, 0.0)
                    allocation = config.initial_capital_gbp * weight
                    if next_bar is not None and next_bar.open > 0:
                        shares = math.floor(allocation / (next_bar.open * gbp_per_usd))
                        notional = shares * next_bar.open * gbp_per_usd
                    else:
                        shares = 0
                        notional = 0.0
                    capacity = config.capacity_fraction * r3_liquid[identity][1] * gbp_per_usd
                    cost = (
                        _round_trip_cost(notional, shares, gbp_per_usd, config)
                        if notional > 0
                        else 0.0
                    )
                    reason = None
                    if next_bar is None:
                        reason = "missing_next_session_open"
                    elif shares < 1:
                        reason = "rounded_below_one_share"
                    elif notional > capacity + 1e-9:
                        reason = "capacity_limit"
                    elif cost / notional > config.round_trip_cost_ceiling + 1e-12:
                        reason = "cost_derived_floor"
                    plan_orders.append(
                        {
                            "security_id": identity,
                            "target_weight": weight,
                            "shares": shares,
                            "notional_gbp": notional,
                            "capacity_gbp": capacity,
                            "estimated_round_trip_cost_gbp": cost,
                            "round_trip_cost_fraction": cost / notional if notional else None,
                            "status": "feasible" if reason is None else "blocked",
                            "reason": reason,
                        }
                    )
                funded_orders = [order for order in plan_orders if order["status"] == "feasible"]
                purchase_total = math.fsum(order["notional_gbp"] for order in funded_orders)
                reserve = math.fsum(
                    _sell_reserve(
                        order["notional_gbp"], order["shares"], gbp_per_usd, config
                    )
                    for order in funded_orders
                )
                cash_required = config.initial_capital_gbp * config.cash_buffer + reserve
                if purchase_total > config.initial_capital_gbp - cash_required + 1e-9:
                    plan_reason = "cash_and_liquidation_reserve"
                elif len(funded_orders) == len(plan_orders) and funded_orders:
                    feasible_plan_count += 1
                    feasible_order_count += len(funded_orders)
                elif not funded_orders:
                    plan_reason = "zero_feasible_orders"
                else:
                    plan_reason = "one_or_more_orders_blocked"
            except (ValueError, ArithmeticError) as error:
                plan_reason = f"invalid_volatility_or_plan:{error}"
        else:
            plan_reason = "hard_halted_or_regime_off" if not risk_on else "no_scored_candidates"
        rows.append(
            {
                "date": day.isoformat(),
                "pit_members": len(active),
                "complete_data": len(data_ready),
                "raw_price_at_least_10": len(raw_price),
                "legacy_liquidity_500m": len(legacy_liquid),
                "legacy_positive_momentum_and_trend": len(legacy_signal),
                "r3_liquidity_20m": len(r3_liquid),
                "r3_momentum_scores": len(scores),
                "regime_allows_increase": risk_on,
                "volatility_selected": len(selected) if risk_on else 0,
                "whole_share_orders": sum(order["shares"] >= 1 for order in plan_orders),
                "capacity_feasible_orders": sum(
                    order["shares"] >= 1
                    and order["notional_gbp"] <= order["capacity_gbp"] + 1e-9
                    for order in plan_orders
                ),
                "cost_floor_feasible_orders": sum(
                    order["status"] == "feasible" for order in plan_orders
                ),
                "legacy_actual_fills": actual_fills_by_signal[day.isoformat()],
                "legacy_skips": dict(sorted(skips_by_signal[day.isoformat()].items())),
                "plan_status": "feasible" if plan_reason is None else "blocked",
                "plan_reason": plan_reason,
                "orders": plan_orders,
            }
        )
    return {
        "method": (
            "Causal decision-date recomputation from PIT membership and pinned sessions; "
            "next-session opens are used only for historical execution feasibility, never ranking."
        ),
        "performance_claim": False,
        "dates": rows,
        "feasible_flat_account_plans": feasible_plan_count,
        "feasible_orders": feasible_order_count,
        "total_decision_dates": len(rows),
        "legacy_policy": {
            "liquidity_usd": config.legacy_liquidity_usd,
            "discretionary_minimum_gbp": config.legacy_min_order_gbp,
            "signal_vetoes": ["positive momentum", "price above SMA200"],
        },
        "r3_policy": {
            "liquidity_usd": config.r3_liquidity_usd,
            "capacity_fraction": config.capacity_fraction,
            "round_trip_cost_ceiling": config.round_trip_cost_ceiling,
            "signal_vetoes": [],
        },
    }


def _budget(
    config: R3FeasibilityConfig,
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    recurring = {
        "data": config.annual_data_gbp,
        "hosting": config.annual_hosting_gbp,
        "software": config.annual_software_gbp,
    }
    unresolved = [name for name, value in recurring.items() if value is None]
    if not config.account_tariff_verified:
        unresolved.append("account_tariff_and_commission_offset_evidence")
    if not config.account_permissions_verified:
        unresolved.append("account_permissions_and_instrument_eligibility_evidence")
    if not config.operating_costs_verified:
        unresolved.append("incremental_operating_cost_evidence")
    annual_account_max = 12 * config.monthly_account_minimum_gbp
    recurring_known = math.fsum(value for value in recurring.values() if value is not None)
    reserve_values = [
        math.fsum(order["estimated_round_trip_cost_gbp"] / 2 for order in row["orders"])
        for row in (policy or {}).get("dates", [])
        if row["plan_status"] == "feasible"
    ]
    liquidation_reserve = max(reserve_values, default=None)
    if liquidation_reserve is None:
        unresolved.append("mandatory_liquidation_reserve")
    known_conservative_cost = (
        annual_account_max
        + recurring_known
        + config.research_cost_from_capital_gbp
        + (liquidation_reserve or 0.0)
    )
    return {
        "initial_capital_gbp": config.initial_capital_gbp,
        "strict_terminal_wealth_target_gbp": config.initial_capital_gbp
        + config.target_profit_gbp,
        "strict_net_profit_target_gbp": config.target_profit_gbp,
        "account_charge_alternatives_gbp": {
            "commissions_fully_offset_minimum": 0.0,
            "conservative_full_monthly_minimum": annual_account_max,
            "overlap_not_double_counted": True,
        },
        "recurring_operating_costs_gbp": recurring,
        "assumption_status": {
            "commission_offset_treatment": config.commission_offset_treatment,
            "whole_share_us_stocks_assumed_permitted": (
                config.whole_share_us_stocks_assumed_permitted
            ),
            "account_tariff_verified": config.account_tariff_verified,
            "account_permissions_verified": config.account_permissions_verified,
            "operating_costs_verified": config.operating_costs_verified,
            "account_tariff_basis": config.account_tariff_evidence,
            "account_permissions_basis": config.account_permissions_evidence,
        },
        "research_cost_from_starting_capital_gbp": config.research_cost_from_capital_gbp,
        "mandatory_liquidation_reserve_gbp": liquidation_reserve,
        "known_conservative_cost_gbp": known_conservative_cost,
        "gross_profit_needed_before_known_costs_gbp": config.target_profit_gbp
        + known_conservative_cost,
        "fractional_shares_assumed": config.fractional_shares,
        "additional_funding_assumed_gbp": 0.0,
        "unresolved": sorted(set(unresolved)),
        "all_in_cost_known": not unresolved,
    }


def build_r3_feasibility_report(
    ledger: Mapping[str, Any],
    config: R3FeasibilityConfig,
    *,
    run_timestamp: datetime,
    ledger_sha256: str,
    config_file_sha256: str,
    canonical: VerifiedCanonicalInputs | None = None,
    calendar: TradingCalendar | None = None,
    provenance: Mapping[str, Any] | None = None,
    legacy_report: Mapping[str, Any] | None = None,
    legacy_report_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the fail-closed R3.1 report without mutating source evidence."""

    if run_timestamp.tzinfo is None or run_timestamp.utcoffset() is None:
        raise ValueError("run timestamp must include timezone")
    _validate_ledger(ledger, config)
    if (canonical is None) != (calendar is None):
        raise ValueError("canonical inputs and calendar must be supplied together")
    source_audit = _source_execution_audit(ledger, legacy_report)
    attribution = _ledger_attribution(ledger, source_audit)
    policy = (
        _policy_funnel(ledger, canonical, calendar, config)
        if canonical is not None and calendar is not None
        else None
    )
    budget = _budget(config, policy)
    blockers = list(budget["unresolved"])
    if policy is None:
        blockers.append("canonical_policy_recomputation_not_run")
    elif policy["feasible_flat_account_plans"] == 0:
        blockers.append("zero_feasible_flat_account_plans")
    if ledger.get("invalid_evidence"):
        blockers.append("legacy_ledger_contains_known_data_limitations")
    if not source_audit["verified"]:
        blockers.append("content_bound_source_execution_audit_not_verified")
    research_acceptance = not blockers
    scope_override = config.scope_decision == "proceed_with_open_evidence"
    phase_closed = research_acceptance or scope_override
    result: dict[str, Any] = {
        "stage": "R3.1",
        "evidence_class": "development",
        "objective": {
            "initial_capital_gbp": 3000,
            "net_profit_strictly_greater_than_gbp": 300,
            "terminal_wealth_strictly_greater_than_gbp": 3300,
            "guaranteed": False,
        },
        "identities": {
            "run_timestamp": run_timestamp.astimezone(UTC).isoformat(),
            "ledger_sha256": ledger_sha256,
            "legacy_report_sha256": legacy_report_sha256,
            "config_file_sha256": config_file_sha256,
            "config_content_sha256": config.sha256,
            "canonical_manifest_sha256": canonical.manifest_sha256 if canonical else None,
            "calendar_sha256": calendar.source_sha256 if calendar else None,
            "provenance": dict(provenance or {}),
        },
        "legacy_ledger_attribution": attribution,
        "policy_comparison": policy,
        "starting_account_budget": budget,
        "implementation_complete": True,
        "research_acceptance_passed": research_acceptance,
        "phase_closed": phase_closed,
        "phase_closure_basis": (
            "research_acceptance"
            if research_acceptance
            else "explicit_scope_decision_with_open_evidence"
            if scope_override
            else "not_closed"
        ),
        "scope_decision": {
            "decision": config.scope_decision,
            "recorded_at": config.scope_decision_recorded_at,
            "note": config.scope_decision_note,
            "resolves_evidence_blockers": False,
            "authorizes_execution": False,
        },
        "qualification_permitted": False,
        "paper_execution_permitted": False,
        "blockers": sorted(set(blockers)),
        "next_stage_permitted": phase_closed,
        "next_stage_started": False,
        "limitations": [
            "The retained ledger and all recomputed dates are inspected development evidence.",
            "Flat-account plans test order economics, not continuous R3 returns or "
            "target attainment.",
            "Account-specific tariff, permissions and incremental operating costs "
            "require evidence.",
            "R3.1 neither trains ML nor implements the R3 event simulator or objective evaluator.",
            "A scope decision can close R3.1 but cannot satisfy research or deployment gates.",
        ],
    }
    result["report_sha256"] = _digest(result)
    return result


def write_r3_feasibility_report(report: Mapping[str, Any], output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "r3_1_feasibility.json").write_text(_json(report), encoding="utf-8")
    attribution = report["legacy_ledger_attribution"]
    budget = report["starting_account_budget"]
    policy = report["policy_comparison"]
    lines = [
        "# R3.1 account economics and exposure attribution",
        "",
        "Development evidence only. No qualification, paper execution or live order is permitted.",
        "",
        f"Report SHA-256: `{report['report_sha256']}`",
        "",
        "## Legacy £3,000 account",
        "",
        "| Initial | Terminal | Net profit | Fills | Mean exposure | Halted sessions |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| £{attribution['initial_capital_gbp']:.2f} | "
            f"£{attribution['terminal_wealth_gbp']:.2f} | "
            f"£{attribution['net_profit_gbp']:.2f} | {attribution['actual_fills']} | "
            f"{attribution['mean_exposure']:.3%} | {attribution['hard_halted_sessions']} |"
        ),
        "",
        "Same-fill bridge: gross profit "
        f"£{attribution['same_fill_gross_profit_gbp']:.2f}; "
        f"cost drag £{attribution['same_fill_cost_drag_gbp']:.2f}; "
        f"recorded nominal costs £{attribution['recorded_cost_total_gbp']:.2f}.",
        "",
        "## Policy feasibility",
        "",
    ]
    if policy is None:
        lines.append("Canonical recomputation was not run; policy comparison is blocked.")
    else:
        lines.extend(
            [
                f"Decision dates: {policy['total_decision_dates']}; "
                f"feasible flat-account plans: {policy['feasible_flat_account_plans']}; "
                f"feasible orders: {policy['feasible_orders']}.",
                "",
                "These plans compare the fixed $500m/£150 policy with the predeclared "
                "$20m/capacity/cost policy. They do not simulate R3 performance.",
            ]
        )
    lines.extend(
        [
            "",
            "## £3,000 first-year budget",
            "",
            f"Known conservative cost: £{budget['known_conservative_cost_gbp']:.2f}.",
            f"Gross profit needed before known costs: strictly above "
            f"£{budget['gross_profit_needed_before_known_costs_gbp']:.2f}.",
            f"All-in cost known: **{str(budget['all_in_cost_known']).lower()}**.",
            "",
            "Unresolved: " + (", ".join(budget["unresolved"]) or "none"),
            "",
            "## Acceptance",
            "",
            "Research acceptance: **"
            + ("passed" if report["research_acceptance_passed"] else "blocked")
            + "**.",
            f"Phase closed: **{str(report['phase_closed']).lower()}**.",
            f"Next stage permitted: **{str(report['next_stage_permitted']).lower()}**; "
            "not started.",
            "",
            "Blockers: " + (", ".join(report["blockers"]) or "none"),
            "",
        ]
    )
    (output_directory / "r3_1_feasibility.md").write_text("\n".join(lines), encoding="utf-8")
