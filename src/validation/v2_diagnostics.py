"""Single-change V1 controls: retain V1 engine, sizing floor and target incumbency.

These development diagnostics are USD research comparisons, not small-account GBP
runs, V2 qualification evidence, or the original adaptive walk-forward V1 report.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from datetime import UTC, date, datetime, time
from typing import Any

from src.backtest.metrics import performance_metrics
from src.backtest.v2 import V2Market, run_v2_backtest
from src.backtest.v2_execution import FeeModel
from src.config.v2 import V2Config
from src.data.fx import FXHistory, FXObservation
from src.portfolio import PortfolioConstructionError, estimate_annualized_covariance
from src.portfolio.volatility import expected_annualized_volatility
from src.strategy import RankedStock
from src.validation.native_execution import build_native_market_context, run_native_backtest
from src.validation.native_inputs import NativeValidationInputs
from src.validation.native_strategy import (
    NativeStrategyContext,
    NativeStrategyParameters,
    build_native_strategy_context,
    build_native_targets,
)
from src.validation.v2_audit import audit_v2_ledger


def diagnostic_momentum_rank(
    context: NativeStrategyContext, day: date, allowed: set[str]
) -> tuple[tuple[RankedStock, ...], dict[str, str]]:
    """Exact t-21 / t-252, with V2 absolute momentum and stock trend screen."""
    index = context.session_indexes[day]
    window = context.sessions[max(0, index - 252) : index + 1]
    scores: list[tuple[str, float]] = []
    excluded: dict[str, str] = {}
    for symbol in sorted(allowed):
        prices = [context.prices.get((session, symbol)) for session in window]
        if len(prices) != 253 or any(
            value is None or not math.isfinite(value) or value <= 0 for value in prices
        ):
            excluded[symbol] = "missing_253_consecutive_sessions"
            continue
        values = [float(value) for value in prices if value is not None]
        momentum = values[-22] / values[0] - 1
        if momentum <= 0 or values[-1] <= math.fsum(values[-200:]) / 200:
            excluded[symbol] = "absolute_momentum_or_trend"
            continue
        scores.append((symbol, momentum))
    ranked = tuple(
        RankedStock(symbol, rank, score)
        for rank, (symbol, score) in enumerate(
            sorted(scores, key=lambda item: (-item[1], item[0])), 1
        )
    )
    return ranked, excluded


def diagnostic_spy_ceiling(context: NativeStrategyContext, day: date, cash_buffer: float) -> float:
    """Weekly caller uses only SPY close/SMA200; missing or equality is risk-off."""
    index = context.session_indexes[day]
    if index < 199:
        return 0.0
    values = [
        context.prices.get((session, context.benchmark_security_id))
        for session in context.sessions[index - 199 : index + 1]
    ]
    if any(value is None or not math.isfinite(value) or value <= 0 for value in values):
        return 0.0
    known = [float(value) for value in values if value is not None]
    return 1 - cash_buffer if known[-1] > math.fsum(known) / 200 else 0.0


def diagnostic_dual_scale(
    context: NativeStrategyContext, day: date, weights: dict[str, float], ceiling: float
) -> dict[str, float]:
    """Further scale V1's 20-day constrained target by its aligned 63-day risk."""
    if not weights:
        return {}
    index = context.session_indexes[day]
    window = context.sessions[max(0, index - 63) : index + 1]
    if len(window) != 64:
        raise PortfolioConstructionError("dual covariance requires 64 consecutive closes")
    histories: dict[str, list[float]] = {}
    for symbol in weights:
        values = [context.prices.get((session, symbol)) for session in window]
        if any(value is None for value in values):
            raise PortfolioConstructionError("dual covariance contains missing session")
        histories[symbol] = [float(value) for value in values if value is not None]
    covariance = estimate_annualized_covariance(histories, lookback=63)
    risk = expected_annualized_volatility(weights, covariance)
    if not math.isfinite(risk) or risk <= 0:
        raise PortfolioConstructionError("invalid long covariance risk")
    scale = min(1.0, ceiling / risk)
    return {symbol: weight * scale for symbol, weight in weights.items()}


def run_v1_single_change_diagnostics(
    inputs: NativeValidationInputs,
    *,
    start: date,
    end: date,
    v2_market: V2Market | None = None,
) -> dict[str, Any]:
    """Run original fixed V1 and all five controls on identical dates/costs in USD.

    This preserves the V1 lifecycle, including selection from targets; results do
    not replace V1's recorded walk-forward evidence or claim V2 execution attestation.
    """
    context = build_native_strategy_context(inputs)
    market = build_native_market_context(inputs)
    if start not in context.sessions or end not in context.sessions or start > end:
        raise ValueError("diagnostic window must use ordered native sessions")
    allowed = {day for day in context.sessions if start <= day <= end}
    result: dict[str, Any] = {}
    for change in (None, "monthly", "score", "equal_weight", "simple_regime", "dual_covariance"):
        name = "original_v1" if change is None else f"v1_only_{change}"
        targets = build_native_targets(
            inputs,
            NativeStrategyParameters(diagnostic_change=change),
            context=context,
            allowed_execution_dates=allowed,
        )
        run = run_native_backtest(
            inputs,
            scenario="baseline",
            targets=targets,
            context=market,
            window_start=start,
            window_end=end,
        )
        points = run.result.equity_curve
        metrics = performance_metrics(
            tuple(point.date for point in points),
            tuple(point.equity for point in points),
            exposures=tuple(point.gross_exposure for point in points),
        )
        result[name] = {
            "status": "executed",
            "metrics": asdict(metrics),
            "target_sha256": targets.target_sha256,
            "execution_trace_sha256": run.result.execution_trace.sha256,
            "orders": len(run.result.trades),
            "execution_issues": len(run.result.execution_issues),
            "final_risk_state": str(run.result.final_risk_state),
            "first_point": points[0].date.isoformat(),
            "last_point": points[-1].date.isoformat(),
        }
    result["fixed_v2"] = _fixed_v2_usd_comparison(
        inputs, v2_market, start=start, end=end, initial_date=points[0].date
    )
    return {
        "evidence_class": "development",
        "currency": "USD",
        "initial_cash": 100000,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "runs": result,
        "cost_model": {
            "commission": inputs.config.transaction_costs[0],
            "slippage_bps": inputs.config.transaction_costs[1],
            "fx_bps": inputs.config.transaction_costs[2],
        },
        "limitations": [
            "V1 target-based incumbency retained, not actual-fill V2 selection",
            "V1 pre-risk allocation floor, universe cap, safety and adjusted-share engine retained",
            "As in V1, risk scaling may reduce final weights below the pre-risk allocation floor",
            "Fixed continuous V1 control, not reproduction of adaptive stitched V1 report",
            "USD $100000 comparison, not GBP ISA small-account feasibility",
            "Diagnostic changes cannot provide native V2 certification",
            "Fixed V2 uses raw whole shares and actual fills; V1 uses adjusted fractional shares",
            "Unit USD numeraire is synthetic accounting, not an observed GBP/USD rate",
            "V2 economic minimum is USD150 in this adapter; account fees match V1 at zero",
        ],
    }


def _fixed_v2_usd_comparison(
    inputs: NativeValidationInputs,
    market: V2Market | None,
    *,
    start: date,
    end: date,
    initial_date: date,
) -> dict[str, Any]:
    """Run actual V2 fills in a labelled USD accounting adapter at V1 costs.

    The GBP-named engine ledger fields represent USD numerically in this adapter.
    Conversion rate one and zero conversion fee make internal sweeps neutral;
    native V1's conservative per-side FX friction is still charged identically.
    This comparison does not replace actual GBP feasibility evidence.
    """
    if market is None:
        return {
            "status": "unexecutable",
            "reason": "pinned V2Market required for same-basis comparison",
        }
    commission, slippage, friction = inputs.config.transaction_costs
    costs = FeeModel(
        commission_per_share=0,
        commission_min_usd=commission,
        slippage_bps=slippage,
        fx_friction_bps=friction,
        conversion_bps=0,
    )
    observations = tuple(
        FXObservation(datetime.combine(day, time(0), UTC), datetime.combine(day, time(0), UTC), 1.0)
        for day in market.calendar.sessions
    )
    fx_identity = hashlib.sha256(
        json.dumps([(item.available_at.isoformat(), 1.0) for item in observations]).encode()
    ).hexdigest()
    fx = FXHistory(
        observations,
        "USD unit-numeraire adapter; not market FX",
        "internal diagnostic",
        fx_identity,
        True,
    )
    config = V2Config()
    try:
        ledger = run_v2_backtest(
            market,
            fx,
            config,
            start=start,
            end=end,
            initial_capital_gbp=100000,
            fractional=False,
            costs=costs,
            monthly_fee_gbp=0,
        )
        audit = audit_v2_ledger(
            ledger,
            market,
            fx,
            config,
            costs,
            initial_capital_gbp=100000,
            start=start,
            end=end,
            monthly_fee_gbp=0,
        )
        if not audit.passed:
            raise ValueError("V2 comparison reconciliation failed: " + "; ".join(audit.findings))
        points = ledger["points"]
        point_dates = tuple(date.fromisoformat(point["date"]) for point in points)
        dates = (initial_date,) + point_dates
        values = (100000.0,) + tuple(float(point["equity_usd"]) for point in points)
        exposures = (0.0,) + tuple(float(point["gross_exposure"]) for point in points)
        if initial_date >= start:
            raise ValueError("same-basis comparison requires prior session initial capital mark")
        metrics = performance_metrics(dates, values, exposures=exposures)
        return {
            "status": "executed",
            "metrics": asdict(metrics),
            "orders": len(ledger["fills"]),
            "execution_issues": len(ledger["issues"]),
            "invalid_evidence": ledger["invalid_evidence"],
            "first_point": initial_date.isoformat(),
            "last_point": end.isoformat(),
            "final_risk_state": "hard_halted" if points[-1]["hard_halted"] else "active",
            "costs": asdict(costs),
            "monthly_fee": 0,
            "config_sha256": config.sha256,
            "calendar_sha256": market.calendar.source_sha256,
            "numeraire_adapter_sha256": fx_identity,
            "execution_audit": asdict(audit),
            "ledger_sha256": hashlib.sha256(
                json.dumps(ledger, sort_keys=True).encode()
            ).hexdigest(),
            "engine": "V2 actual-fill raw-whole-share engine; USD unit numeraire",
            "deployment_admissible": False,
        }
    except (ValueError, ArithmeticError) as error:
        return {"status": "unexecutable", "reason": str(error), "costs": asdict(costs)}
