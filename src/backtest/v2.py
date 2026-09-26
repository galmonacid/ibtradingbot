"""Sequential V2 development simulator: close decisions, later raw-share fills.

This module cannot authorize paper/live execution. Missing held marks abort a run;
unknown dividend payment dates remain non-spendable receivables, never cash.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from src.backtest.v2_execution import Account, FeeModel, execute_plan
from src.config.v2 import V2Config
from src.data.calendar import TradingCalendar
from src.data.canonical_historical import CanonicalCorporateAction, CanonicalDailyBar
from src.data.fx import FXHistory
from src.portfolio.v2 import (
    DualCovariance,
    V2DrawdownState,
    apply_discretionary_band,
    build_v2_targets,
    estimate_dual_covariance,
    reduce_v2_targets,
)
from src.strategy.v2 import V2Regime, rank_v2, select_v2, selection_dates, update_weekly_regime


@dataclass(frozen=True)
class V2Market:
    calendar: TradingCalendar
    benchmark_id: str
    bars: dict[str, dict[date, CanonicalDailyBar]]
    active: dict[date, frozenset[str]]
    actions: tuple[CanonicalCorporateAction, ...]


@dataclass(frozen=True)
class PendingPlan:
    signal_date: date
    execution_index: int
    weights: dict[str, float]
    mandatory: frozenset[str]
    reason: str
    name_cap: float
    ceiling: float
    covariance: DualCovariance
    amended_at: date | None = None


def _time(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), ZoneInfo("America/New_York"))


def _covariance(
    market: V2Market, symbols: set[str], index: int, config: V2Config
) -> DualCovariance:
    sessions = market.calendar.sessions
    history = sessions[max(0, index - config.long_covariance_window) : index + 1]
    if symbols and len(history) != config.long_covariance_window + 1:
        raise ValueError("insufficient aligned covariance history")
    values: dict[str, tuple[float, ...]] = {}
    for symbol in sorted(symbols):
        series = market.bars.get(symbol, {})
        if any(day not in series for day in history):
            raise ValueError(f"missing covariance session for {symbol}")
        values[symbol] = tuple(series[day].adjusted_close for day in history)
    return (
        estimate_dual_covariance(values, longer_window=config.long_covariance_window)
        if values
        else DualCovariance({}, {})
    )


def _nav(account: Account, prices: dict[str, float], fx: float) -> float:
    return account.cash_gbp + fx * (
        account.cash_usd
        + account.receivables_usd
        + math.fsum(shares * prices[symbol] for symbol, shares in account.holdings.items())
    )


def _weights(account: Account, prices: dict[str, float], fx: float) -> dict[str, float]:
    nav = _nav(account, prices, fx)
    if nav <= 0:
        raise ValueError("account equity exhausted")
    return {s: q * prices[s] * fx / nav for s, q in account.holdings.items() if q > 0}


def run_v2_backtest(
    market: V2Market,
    fx_history: FXHistory,
    config: V2Config,
    *,
    start: date,
    end: date,
    initial_capital_gbp: float = 1000,
    fractional: bool = False,
    costs: FeeModel | None = None,
    monthly_fee_gbp: float = 3.0,
) -> dict[str, Any]:
    """One continuous account; no fold resets or post-halt truncation.

    Whole-share ISA is the default. Fractional runs are explicitly diagnostics.
    Ex-date dividend entitlements are marked but not spent without payment evidence.
    """
    sessions = market.calendar.sessions
    if start not in sessions or end not in sessions or start > end:
        raise ValueError("run bounds must be ordered pinned calendar sessions")
    if not math.isfinite(initial_capital_gbp) or initial_capital_gbp <= 0:
        raise ValueError("initial GBP capital must be positive")
    if not math.isfinite(monthly_fee_gbp) or monthly_fee_gbp < 0:
        raise ValueError("monthly fee must be nonnegative")
    requested_costs = costs or FeeModel()
    costs = replace(
        requested_costs,
        commission_min_usd=max(requested_costs.commission_min_usd, config.commission_per_order_usd),
        slippage_bps=max(requested_costs.slippage_bps, config.slippage_bps),
        fx_friction_bps=max(requested_costs.fx_friction_bps, config.fx_buffer_bps),
    )
    account = Account(initial_capital_gbp, 0.0, {})
    state = V2DrawdownState(initial_capital_gbp)
    regime = V2Regime()
    pending: PendingPlan | None = None
    previous_gross = 0.0
    month_ends = set(
        selection_dates(market.calendar, replace(config, selection_schedule="monthly"))
    )
    selections = set(selection_dates(market.calendar, config))
    adjusted = {
        s: {d: row.adjusted_close for d, row in rows.items()} for s, rows in market.bars.items()
    }
    spy = adjusted[market.benchmark_id]
    actions: dict[date, list[CanonicalCorporateAction]] = defaultdict(list)
    for action in market.actions:
        actions[action.action_date].append(action)
    points: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    fees: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    closed_lots: list[dict[str, Any]] = []
    # Lot quantity, entry date, GBP/USD basis per raw share (including entry costs).
    lots: dict[str, deque[tuple[float, date, float, float]]] = defaultdict(deque)
    entries: dict[str, date] = {}
    first_fx = fx_history.at(_time(start, 9, 30), max_age_days=config.max_fx_age_days).gbp_per_usd
    invalid_evidence = False

    def book_fill(row: dict[str, Any], day: date, rate: float, reason: str) -> None:
        symbol = str(row.get("symbol", row.get("security_id", "")))
        q = float(row["shares"])
        side = str(row["side"])
        price = float(row["execution_price"])
        fee = float(row["commission_usd"]) + float(row["fx_friction_usd"])
        # Conversion charges are separately attributed and included in ledger NAV.
        row.update(date=day.isoformat(), security_id=symbol, reason=reason, gbp_per_usd=rate)
        fills.append(row)
        if side == "buy":
            if symbol not in entries:
                entries[symbol] = day
            lots[symbol].append((q, day, (price + fee / q) * rate, price + fee / q))
        else:
            remaining = q
            while remaining > 1e-8:
                if not lots[symbol]:
                    raise ValueError("sell exceeds FIFO inventory")
                quantity, opened, gbp_basis, usd_basis = lots[symbol].popleft()
                closed = min(quantity, remaining)
                closed_lots.append(
                    dict(
                        security_id=symbol,
                        entry=opened.isoformat(),
                        exit=day.isoformat(),
                        basis_gbp=closed * gbp_basis,
                        basis_usd=closed * usd_basis,
                        proceeds_gbp=closed * (price - fee / q) * rate,
                        proceeds_usd=closed * (price - fee / q),
                    )
                )
                remaining -= closed
                if quantity - closed > 1e-8:
                    lots[symbol].appendleft((quantity - closed, opened, gbp_basis, usd_basis))
            if not lots[symbol]:
                episodes.append(
                    dict(
                        security_id=symbol,
                        entry=entries.pop(symbol).isoformat(),
                        exit=day.isoformat(),
                    )
                )

    for index, day in enumerate(sessions):
        if day > end:
            break
        if day < start:
            regime = update_weekly_regime(regime, spy, day, market.calendar, config)
            continue
        rate_open = fx_history.at(
            _time(day, 9, 30), max_age_days=config.max_fx_age_days
        ).gbp_per_usd
        # Only today's published corporate actions affect today's raw share inventory.
        for action in sorted(
            actions.get(day, ()), key=lambda a: (a.action_type != "split", a.security_id)
        ):
            symbol = action.security_id
            quantity = account.holdings.get(symbol, 0.0)
            if quantity <= 0:
                continue
            if action.action_type == "split":
                account.holdings[symbol] = quantity * action.value
                lots[symbol] = deque(
                    (q * action.value, d, g / action.value, u / action.value)
                    for q, d, g, u in lots[symbol]
                )
            elif action.action_type == "dividend":
                account = replace(
                    account, receivables_usd=account.receivables_usd + quantity * action.value
                )
                issues.append(
                    dict(
                        date=day.isoformat(),
                        security_id=symbol,
                        reason="dividend_payment_date_unavailable_receivable_only",
                    )
                )
                invalid_evidence = True
            elif action.action_type == "delisting":
                # Explicit canonical cash recovery, including zero, never invented last price.
                value = quantity * action.value
                account = replace(
                    account,
                    cash_usd=account.cash_usd + value,
                    holdings={s: q for s, q in account.holdings.items() if s != symbol},
                )
                book_fill(
                    dict(
                        symbol=symbol,
                        side="sell",
                        shares=quantity,
                        reference_price=action.value,
                        execution_price=action.value,
                        commission_usd=0.0,
                        slippage_usd=0.0,
                        fx_friction_usd=0.0,
                        commission_gbp=0.0,
                        slippage_gbp=0.0,
                        fx_friction_gbp=0.0,
                        signal_date=day.isoformat(),
                    ),
                    day,
                    rate_open,
                    "delisting_recovery",
                )
        opens: dict[str, float] = {}
        for symbol in account.holdings:
            row = market.bars.get(symbol, {}).get(day)
            if row is None:
                raise ValueError(f"missing held raw price: {symbol} {day}; run invalid")
            opens[symbol] = row.open
        if pending is not None and pending.execution_index <= index:
            target = dict(pending.weights)
            for symbol in tuple(target):
                row = market.bars.get(symbol, {}).get(day)
                if row is None or symbol not in market.active.get(day, frozenset()):
                    target.pop(symbol)
                    exclusions.append(
                        dict(
                            date=day.isoformat(),
                            security_id=symbol,
                            reason="entry_unavailable_at_execution",
                        )
                    )
                else:
                    opens[symbol] = row.open
            before = account
            execution = execute_plan(
                account,
                target,
                opens,
                rate_open,
                costs=costs,
                fractional=fractional,
                mandatory_ids=pending.mandatory | (set(account.holdings) - set(target)),
                min_order_gbp=config.min_order_value_gbp,
                name_cap=pending.name_cap,
                cash_buffer=config.cash_buffer,
                gross_ceiling=pending.ceiling,
                signal_date=pending.signal_date,
                execution_date=day,
                reductions_only=pending.reason != "monthly_selection",
            )
            accepted = execution.succeeded
            if accepted:
                try:
                    accepted = (
                        pending.covariance.volatility(execution.accepted_weights)
                        <= config.volatility_ceiling + 1e-9
                    )
                except ValueError:
                    accepted = pending.reason != "monthly_selection" and all(
                        q <= before.holdings.get(s, 0) + 1e-10
                        for s, q in execution.account.holdings.items()
                    )
            if accepted:
                account = execution.account
                previous_gross = math.fsum(execution.accepted_weights.values())
                for fill in execution.fills:
                    fill_record = asdict(fill)
                    fill_record["signal_date"] = pending.signal_date.isoformat()
                    fill_record["amended_at"] = (
                        pending.amended_at.isoformat() if pending.amended_at else None
                    )
                    book_fill(fill_record, day, rate_open, pending.reason)
                conversions.extend(
                    dict(asdict(c), date=day.isoformat()) for c in execution.conversions
                )
            else:
                account = before
                invalid_evidence = True
                issues.append(
                    dict(
                        date=day.isoformat(),
                        reason=execution.failure or "post_rounding_volatility",
                        signal_date=pending.signal_date.isoformat(),
                    )
                )
            decisions.append(
                dict(
                    signal_date=pending.signal_date.isoformat(),
                    amended_at=pending.amended_at.isoformat() if pending.amended_at else None,
                    execution_date=day.isoformat(),
                    reason=pending.reason,
                    target_weights=target,
                    status="applied" if accepted else "rejected",
                    skips=[asdict(s) for s in execution.skips],
                )
            )
            pending = None
        closes = {s: market.bars[s][day].close for s in account.holdings}
        rate = fx_history.at(_time(day, 16), max_age_days=config.max_fx_age_days).gbp_per_usd
        if day in month_ends and monthly_fee_gbp:
            # Full fee is conservative versus any monthly commission offset.
            if account.cash_gbp < monthly_fee_gbp:
                raise ValueError("insufficient GBP cash for monthly fee; margin prohibited")
            account = replace(account, cash_gbp=account.cash_gbp - monthly_fee_gbp)
            fees.append(
                dict(date=day.isoformat(), amount_gbp=monthly_fee_gbp, kind="monthly_activity")
            )
        nav = _nav(account, closes, rate)
        state = state.observe(nav)
        actual = _weights(account, closes, rate)
        regime = update_weekly_regime(regime, spy, day, market.calendar, config)
        if day not in spy:
            regime = replace(regime, valid=False, reason="missing_daily_spy")
        if not regime.valid:
            invalid_evidence = True
            issues.append(dict(date=day.isoformat(), reason=regime.reason))
            if pending is not None and pending.reason == "monthly_selection":
                # A previously valid monthly intent cannot introduce risk after a
                # later missing benchmark observation. Keep only reductions of
                # actual filled holdings and preserve the original safety deadline.
                safer = {
                    symbol: min(pending.weights.get(symbol, 0.0), weight)
                    for symbol, weight in actual.items()
                    if pending.weights.get(symbol, 0.0) > 0
                }
                if any(
                    safer.get(symbol, 0.0) < weight - 1e-10 for symbol, weight in actual.items()
                ):
                    pending = replace(
                        pending,
                        weights=safer,
                        reason="invalid_spy_reductions_only",
                        amended_at=day,
                    )
                else:
                    decisions.append(
                        dict(
                            signal_date=pending.signal_date.isoformat(),
                            execution_date=None,
                            reason="invalid_spy_blocks_pending_increase",
                            status="cancelled",
                            amended_at=day.isoformat(),
                        )
                    )
                    pending = None
        mandatory = set(actual) - set(market.active.get(day, frozenset()))
        name_cap = config.soft_position_weight if state.soft_active else config.max_position_weight
        ceiling = min(regime.ceiling, previous_gross) if state.soft_active else regime.ceiling
        reason = "risk_reduction"
        try:
            covariance = _covariance(market, set(actual) - mandatory, index, config)
            limits: dict[str, Any] = dict(
                regime_ceiling=ceiling,
                cash_buffer=config.cash_buffer,
                target_annual_volatility=config.volatility_ceiling,
                max_position_weight=name_cap,
                hard_halted=state.hard_halted,
            )
            reduced = reduce_v2_targets(
                actual, covariance, mandatory_exits=tuple(mandatory), **limits
            )
            breach = any(reduced.get(s, 0) < w - 1e-10 for s, w in actual.items())
            target = reduced
            monthly = day in selections and regime.valid and not state.hard_halted
            # Monthly exits remain mandatory even when a same-close safety
            # reduction blocks discretionary additions and redistribution.
            if monthly:
                eligible: dict[str, dict[date, float]] = {}
                history = sessions[max(0, index - 19) : index + 1]
                for symbol in sorted(market.active.get(day, frozenset()) - {market.benchmark_id}):
                    rows = market.bars.get(symbol, {})
                    why = None
                    if any(d not in rows for d in history) or len(history) < 20:
                        why = "missing_liquidity_history"
                    elif rows[day].close < config.minimum_price_usd:
                        why = "raw_price_below_minimum"
                    elif (
                        median(rows[d].close * rows[d].volume for d in history)
                        < config.minimum_median_dollar_volume_20d
                    ):
                        why = "liquidity_below_minimum"
                    if why:
                        exclusions.append(
                            dict(date=day.isoformat(), security_id=symbol, reason=why)
                        )
                    else:
                        eligible[symbol] = adjusted[symbol]
                ranking = rank_v2(eligible, day, market.calendar, config)
                exclusions.extend(
                    dict(date=day.isoformat(), security_id=e.symbol, reason=e.reason)
                    for e in ranking.exclusions
                )
                selection = select_v2(ranking.ranked, account.holdings, config)
                selected = tuple(row.symbol for row in selection.selected)
                if breach:
                    # Merge selection exits into the downward-only risk vector.
                    # Do not fill vacancies or redistribute released capital.
                    target = {
                        symbol: weight for symbol, weight in reduced.items() if symbol in selected
                    }
                else:
                    covariance = _covariance(market, set(selected) | set(actual), index, config)
                    target = build_v2_targets(selected, covariance, **limits)
                    target = apply_discretionary_band(
                        actual, target, covariance, band=config.discretionary_band, **limits
                    )
                    reason = "monthly_selection"
                mandatory |= set(actual) - set(target)
            if state.hard_halted:
                target = {}
                reason = "hard_halt"
                mandatory = set(actual)
            if breach:
                mandatory |= {s for s in actual if target.get(s, 0) < actual[s] - 1e-10}
            needed = any(
                abs(target.get(s, 0) - actual.get(s, 0)) > 1e-10 for s in set(target) | set(actual)
            )
            if pending is not None and (breach or state.hard_halted):
                # Merge new safety information into the already scheduled opportunity.
                # Preserve the original deadline and record the later knowledge timestamp.
                safer = {
                    s: min(pending.weights.get(s, 0), w)
                    for s, w in target.items()
                    if s in actual and pending.weights.get(s, 0) > 0
                }
                pending = replace(
                    pending,
                    weights=safer,
                    mandatory=frozenset(actual),
                    reason="hard_halt" if state.hard_halted else "risk_reduction",
                    name_cap=min(pending.name_cap, name_cap),
                    ceiling=min(pending.ceiling, ceiling),
                    covariance=covariance,
                    amended_at=day,
                )
            if (
                needed
                and (breach or monthly or state.hard_halted)
                and (pending is None or pending.reason == "monthly_selection")
            ):
                if pending is not None:
                    decisions.append(
                        dict(
                            signal_date=pending.signal_date.isoformat(),
                            execution_date=None,
                            reason=pending.reason,
                            status="superseded",
                        )
                    )
                pending = PendingPlan(
                    day,
                    index + config.execution_delay_sessions,
                    target,
                    frozenset(mandatory),
                    reason,
                    name_cap,
                    ceiling,
                    covariance,
                )
            vol = covariance.volatility(actual) if actual and not mandatory else None
        except ValueError as error:
            invalid_evidence = True
            issues.append(dict(date=day.isoformat(), reason=f"invalid_risk_inputs:{error}"))
            if pending is not None and (state.hard_halted or not regime.ceiling):
                pending = replace(
                    pending,
                    weights={},
                    mandatory=frozenset(actual),
                    reason="hard_halt" if state.hard_halted else "mandatory_exit",
                    amended_at=day,
                )
            elif pending is not None and pending.reason == "monthly_selection":
                pending = None
            # Missing risk estimates block increases; known mandatory exits still execute.
            if pending is None and (state.hard_halted or not regime.ceiling or mandatory):
                target = (
                    {}
                    if state.hard_halted or not regime.ceiling
                    else {s: w for s, w in actual.items() if s not in mandatory}
                )
                pending = PendingPlan(
                    day,
                    index + config.execution_delay_sessions,
                    target,
                    frozenset(actual),
                    "mandatory_exit",
                    name_cap,
                    ceiling,
                    DualCovariance({}, {}),
                )
            vol = None
        points.append(
            dict(
                date=day.isoformat(),
                equity_gbp=nav,
                equity_usd=nav / rate,
                cash_gbp=account.cash_gbp,
                cash_usd=account.cash_usd,
                receivables_usd=account.receivables_usd,
                gross_exposure=sum(actual.values()),
                drawdown=-state.drawdown,
                hard_halted=state.hard_halted,
                soft_active=state.soft_active,
                regime=regime.reason,
                estimated_volatility=vol,
                holdings=dict(account.holdings),
            )
        )
    if pending is not None:
        decisions.append(
            dict(
                signal_date=pending.signal_date.isoformat(),
                execution_date=None,
                reason=pending.reason,
                status="no_next_session",
            )
        )
    return dict(
        strategy_version=config.strategy_version,
        config_sha256=config.sha256,
        initial_capital_gbp=initial_capital_gbp,
        initial_capital_usd=initial_capital_gbp / first_fx,
        fractional=fractional,
        costs=asdict(costs),
        monthly_fee_gbp=monthly_fee_gbp,
        points=points,
        fills=fills,
        conversions=conversions,
        fees=fees,
        issues=issues,
        decisions=decisions,
        exclusions=exclusions,
        episodes=episodes,
        closed_lots=closed_lots,
        invalid_evidence=invalid_evidence,
        deployment_admissible=False,
        paper_execution_permitted=False,
        evidence_scope="development",
    )
