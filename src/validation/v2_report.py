"""Deterministic attribution for V2 development ledgers; never qualification evidence."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, timedelta
from statistics import fmean
from typing import Any

from src.backtest.metrics import TradeOutcome, performance_metrics
from src.validation.bootstrap import MetricDistribution, bootstrap_validation


def _number(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("report inputs must be finite")
    return result


def _quantiles(value: MetricDistribution | None) -> dict[str, float] | None:
    if value is None:
        return None
    return {"q05": value.q05, "q50": value.q50, "q95": value.q95}


def summarize_v2_run(
    payload: Mapping[str, Any],
    *,
    bootstrap_iterations: int = 2000,
    seed: int = 20260909,
    include_bootstrap: bool = True,
) -> dict[str, Any]:
    """Summarize account-lifetime accounting, preserving post-halt cash sessions.

    Engine supplies initial capital and each actual session close. NAVs in both
    currencies must describe the same portfolio at each close. Costs are explicit
    ledger debits, not a synthesized frictionless strategy counterfactual.
    """
    points = payload["points"]
    if not points:
        raise ValueError("report requires account points")
    dates = tuple(date.fromisoformat(point["date"]) for point in points)
    dispositions = [
        fill for fill in payload.get("fills", []) if fill.get("reason") == "delisting_recovery"
    ]
    fills = [
        fill for fill in payload.get("fills", []) if fill.get("reason") != "delisting_recovery"
    ]
    lots = payload.get("closed_lots", [])
    episodes = payload.get("episodes", [])
    if any(
        not dates[0]
        <= date.fromisoformat(item["entry"])
        <= date.fromisoformat(item["exit"])
        <= dates[-1]
        for item in episodes
    ):
        raise ValueError("completed episodes must lie inside report window")
    exposures = tuple(_number(point["gross_exposure"]) for point in points)
    regimes = tuple(str(point["regime"]) for point in points)
    navs = {
        currency: tuple(_number(point[f"equity_{currency}"]) for point in points)
        for currency in ("gbp", "usd")
    }
    if any(value <= 0 for values in navs.values() for value in values):
        raise ValueError("report NAV must remain positive")
    metric_dates = (dates[0] - timedelta(days=1),) + dates
    fx_by_date = {
        point["date"]: _number(point["equity_usd"]) / _number(point["equity_gbp"])
        for point in points
    }
    # Fixed-fill gross accounting: replay the same shares and currency transfers,
    # refund USD trading costs and GBP conversion/account fees into idle cash.
    # Refund balances are revalued at each close, never reinvested or used to resize.
    refunds: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for fill in fills:
        refunds[fill["date"]][1] += sum(
            _number(fill[f"{kind}_usd"]) for kind in ("commission", "slippage", "fx_friction")
        )
    for conversion in payload.get("conversions", []):
        refunds[conversion["date"]][0] += _number(conversion["fee_gbp"])
    for fee in payload.get("fees", []):
        refunds[fee["date"]][0] += _number(fee["amount_gbp"])
    gross_navs: dict[str, list[float]] = {"gbp": [], "usd": []}
    refund_gbp = refund_usd = 0.0
    for point in points:
        extra_gbp, extra_usd = refunds[point["date"]]
        refund_gbp += extra_gbp
        refund_usd += extra_usd
        usd_per_gbp = fx_by_date[point["date"]]
        gross_navs["gbp"].append(
            _number(point["equity_gbp"]) + refund_gbp + refund_usd / usd_per_gbp
        )
        gross_navs["usd"].append(
            _number(point["equity_usd"]) + refund_gbp * usd_per_gbp + refund_usd
        )
    costs: dict[str, dict[str, float]] = {}
    results: dict[str, Any] = {}
    annual: dict[str, Any] = {}
    bootstrap: dict[str, Any] = {}
    for currency in ("gbp", "usd"):
        initial = _number(payload[f"initial_capital_{currency}"])
        values = (initial,) + navs[currency]
        year_profit: defaultdict[int, float] = defaultdict(float)
        stock_profit: defaultdict[str, float] = defaultdict(float)
        trades = []
        for lot in lots:
            basis = _number(lot[f"basis_{currency}"])
            proceeds = _number(lot[f"proceeds_{currency}"])
            if basis <= 0:
                raise ValueError("closed lots need positive cost basis")
            entry, exit_day = date.fromisoformat(lot["entry"]), date.fromisoformat(lot["exit"])
            if not dates[0] <= entry <= exit_day <= dates[-1]:
                raise ValueError("closed lot lies outside report window")
            profit = proceeds - basis
            year_profit[exit_day.year] += profit
            stock_profit[str(lot["security_id"])] += profit
            trades.append(TradeOutcome(profit / basis, (exit_day - entry).days, profit))
        notional = sum(
            _number(fill["shares"])
            * _number(fill["execution_price"])
            * (_number(fill["gbp_per_usd"]) if currency == "gbp" else 1)
            for fill in fills
        )
        metrics = performance_metrics(
            metric_dates,
            values,
            trade_outcomes=trades,
            traded_notional=notional,
            exposures=(0.0,) + exposures,
        )
        costs[currency] = {
            "commission": sum(_number(fill[f"commission_{currency}"]) for fill in fills),
            "slippage": sum(_number(fill[f"slippage_{currency}"]) for fill in fills),
            "fill_fx_friction": sum(_number(fill[f"fx_friction_{currency}"]) for fill in fills),
            "conversion": sum(
                _number(item[f"fee_{currency}"]) for item in payload.get("conversions", [])
            ),
            "account_fees": sum(
                _number(item["amount_gbp"]) * (fx_by_date[item["date"]] if currency == "usd" else 1)
                for item in payload.get("fees", [])
            ),
        }
        total_costs = sum(costs[currency].values())
        results[currency] = {
            "net_metrics": asdict(metrics),
            "gross_fixed_fill_metrics": asdict(
                performance_metrics(metric_dates, (initial, *gross_navs[currency]))
            ),
            "gross_fixed_fill_terminal_nav": gross_navs[currency][-1],
            "gross_fixed_fill_note": (
                "Same actual share quantities and currency transfers at reference prices; "
                "cost refunds stay idle in their debit currency, revalued daily. "
                "No zero-cost strategy reoptimization, extra trades or halt reset."
            ),
            "buy_plus_sell_notional": notional,
            "net_total_return": values[-1] / values[0] - 1,
            "realized_profit_loss_by_year": dict(sorted(year_profit.items())),
            "realized_profit_loss_by_stock": dict(sorted(stock_profit.items())),
            "concentration_evidence_admissible": False,
            "realized_attribution_note": (
                "FIFO trading P&L includes fill commissions and FX buffer, but excludes "
                "conversion/account fees, dividends and open-position P&L. Diagnostic only; "
                "year/stock concentration gates are unassessable without a full allocation bridge."
            ),
            "unallocated_account_profit": values[-1] - values[0] - sum(stock_profit.values()),
            "additive_cost_return_diagnostic": (values[-1] + total_costs) / values[0] - 1,
            "additive_cost_return_note": (
                "Net terminal NAV plus recorded costs; not a gross counterfactual"
            ),
        }
        yearly_returns: dict[int, float] = {}
        previous = values[0]
        for year in sorted({day.year for day in dates}):
            year_end = next(
                value
                for day, value in reversed(tuple(zip(dates, navs[currency], strict=True)))
                if day.year == year
            )
            yearly_returns[year] = year_end / previous - 1
            previous = year_end
        annual[currency] = yearly_returns
        returns = tuple(right / left - 1 for left, right in zip(values, values[1:], strict=False))
        if not include_bootstrap:
            bootstrap[currency] = {
                "status": "not_requested",
                "reason": "Point-metric diagnostic; baseline bootstrap is reported separately",
            }
            continue
        try:
            analysis = bootstrap_validation(
                returns,
                tuple(trade.return_value for trade in trades),
                regimes,
                iterations=bootstrap_iterations,
                block_length=min(20, len(returns)),
                seed=seed,
            )
            bootstrap[currency] = {
                "status": "available",
                "iterations": analysis.iterations,
                "seed": analysis.seed,
                "block_length": analysis.block_length,
                "daily": {
                    "cagr": _quantiles(analysis.daily.cagr),
                    "sharpe": _quantiles(analysis.daily.sharpe_ratio),
                    "maximum_drawdown": _quantiles(analysis.daily.maximum_drawdown),
                    "one_year_return": _quantiles(analysis.daily.one_year_return),
                    "three_year_return": _quantiles(analysis.daily.three_year_return),
                },
                "regime": {
                    "cagr": _quantiles(analysis.regime_blocks.cagr),
                    "sharpe": _quantiles(analysis.regime_blocks.sharpe_ratio),
                    "maximum_drawdown": _quantiles(analysis.regime_blocks.maximum_drawdown),
                    "one_year_return": _quantiles(analysis.regime_blocks.one_year_return),
                    "three_year_return": _quantiles(analysis.regime_blocks.three_year_return),
                },
                "mean_trade_return": _quantiles(analysis.mean_trade_return),
            }
        except ValueError as error:
            bootstrap[currency] = {"status": "unavailable", "reason": str(error)}
    halted = [index for index, point in enumerate(points) if point["hard_halted"]]
    soft = [index for index, point in enumerate(points) if point["soft_active"]]
    first_hard = halted[0] if halted else None
    pre_halt = {
        currency: asdict(
            performance_metrics(
                metric_dates[: first_hard + 1],
                (_number(payload[f"initial_capital_{currency}"]),) + values[:first_hard],
            )
        )
        if first_hard is not None and first_hard > 0
        else None
        for currency, values in navs.items()
    }
    durations = [
        (date.fromisoformat(item["exit"]) - date.fromisoformat(item["entry"])).days
        for item in episodes
    ]
    return {
        "evidence_class": "development",
        "admissible_for_qualification": False,
        "ready_for_paper_trading": False,
        "qualification_blocker": "Previously inspected development history cannot qualify V2",
        "initial_capital_gbp": payload["initial_capital_gbp"],
        "start": dates[0].isoformat(),
        "end": dates[-1].isoformat(),
        "sessions": len(dates),
        "currencies": results,
        "annual_returns": annual,
        "costs": costs,
        "bootstrap": bootstrap,
        "closed_fifo_lots": len(lots),
        "completed_position_episodes": len(episodes),
        "lot_minimum_met": len(lots) >= 150,
        "episode_minimum_met": len(episodes) >= 150,
        "mean_episode_holding_days": fmean(durations) if durations else None,
        "orders": len(fills),
        "corporate_dispositions": len(dispositions),
        "buy_orders": sum(str(fill["side"]).lower() == "buy" for fill in fills),
        "sell_orders": sum(str(fill["side"]).lower() == "sell" for fill in fills),
        "exit_reasons": dict(
            sorted(
                Counter(
                    str(fill["reason"]) for fill in fills if str(fill["side"]).lower() == "sell"
                ).items()
            )
        ),
        "mean_exposure": fmean(exposures),
        "all_cash_sessions": sum(value <= 1e-12 for value in exposures),
        "regime_transitions": sum(
            left != right for left, right in zip(regimes, regimes[1:], strict=False)
        ),
        "first_soft_halt": dates[soft[0]].isoformat() if soft else None,
        "first_hard_halt": dates[first_hard].isoformat() if first_hard is not None else None,
        "hard_halted_sessions": len(halted),
        "soft_active_sessions": len(soft),
        "pre_halt_metrics": pre_halt,
        "issues": payload.get("issues", []),
        "exclusion_events": len(payload.get("exclusions", [])),
        "exclusion_counts_by_reason": dict(
            sorted(Counter(str(item["reason"]) for item in payload.get("exclusions", [])).items())
        ),
        "exclusion_detail_location": "content-bound scenario ledger",
    }
