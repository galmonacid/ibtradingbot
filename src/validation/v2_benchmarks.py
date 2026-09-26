"""Diagnostic GBP cash and SPY references, never tradable stock-strategy targets.

SPY references explicitly bypass only the stock concentration cap. Their separate
single-asset ledger cannot relax the strategy executor's hard portfolio limits.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from src.backtest.v2 import V2Market
from src.backtest.v2_execution import Account, FeeModel
from src.config.v2 import V2Config
from src.data.fx import FXHistory
from src.portfolio.v2 import V2DrawdownState, estimate_dual_covariance
from src.strategy.v2 import V2Regime, selection_dates, update_weekly_regime


def _timestamp(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), ZoneInfo("America/New_York"))


def _nav(account: Account, symbol: str, price: float, rate: float) -> float:
    return account.cash_gbp + rate * (
        account.cash_usd + account.receivables_usd + account.holdings.get(symbol, 0.0) * price
    )


@dataclass(frozen=True)
class _ReferenceTrade:
    account: Account
    fill: dict[str, Any] | None
    conversion: dict[str, Any] | None
    issue: str | None = None


def _trade(
    account: Account,
    symbol: str,
    price: float,
    rate: float,
    target: float,
    config: V2Config,
    costs: FeeModel,
    *,
    fractional: bool,
    required: bool,
    reductions_only: bool,
) -> _ReferenceTrade:
    """One reference-only order; iterate target shares against post-cost NAV."""
    old = account.holdings.get(symbol, 0.0)
    initial = _nav(account, symbol, price, rate)
    sizing = initial
    for _ in range(64):
        desired = max(0.0, target * sizing / (price * rate))
        if not fractional:
            desired = float(math.floor(desired))
        if reductions_only:
            desired = min(desired, old)
        delta = desired - old
        if abs(delta) < 1e-10:
            return _ReferenceTrade(account, None, None)
        if not fractional and not math.isclose(abs(delta), round(abs(delta)), abs_tol=1e-10):
            return _ReferenceTrade(account, None, None, "unsupported_fractional_residual")
        if abs(delta) * price * rate < config.min_order_value_gbp and not required:
            return _ReferenceTrade(account, None, None, "below_minimum_order")
        buy = delta > 0
        quantity = abs(delta)
        fill_price = price * (1 + (1 if buy else -1) * costs.slippage_bps / 10000)
        commission = max(costs.commission_min_usd, quantity * costs.commission_per_share)
        friction = quantity * fill_price * costs.fx_friction_bps / 10000
        slippage = quantity * abs(fill_price - price)
        gbp, usd = account.cash_gbp, account.cash_usd
        conversion: dict[str, Any] | None = None
        if buy:
            debit = quantity * fill_price + commission + friction
            needed = max(0.0, debit - usd)
            fee = needed * costs.conversion_bps / 10000
            gbp -= (needed + fee) * rate
            usd += needed - debit
            if needed:
                conversion = dict(
                    direction="GBP_TO_USD", amount_usd=needed, fee_usd=fee, fee_gbp=fee * rate
                )
        else:
            proceeds = usd + quantity * fill_price - commission - friction
            fee = abs(proceeds) * costs.conversion_bps / 10000
            gbp += (proceeds - fee) * rate
            usd = 0.0
            conversion = dict(
                direction="USD_TO_GBP" if proceeds >= 0 else "GBP_TO_USD",
                amount_usd=abs(proceeds),
                fee_usd=fee,
                fee_gbp=fee * rate,
            )
        candidate = Account(
            gbp, usd, {symbol: desired} if desired > 1e-10 else {}, account.receivables_usd
        )
        equity = _nav(candidate, symbol, price, rate)
        if equity <= 0:
            return _ReferenceTrade(account, None, None, "post_cost_equity_exhausted")
        weight = desired * price * rate / equity
        cash = gbp + usd * rate
        if (
            gbp >= -1e-9
            and usd >= -1e-9
            and cash >= config.cash_buffer * equity - 1e-9
            and weight <= target + 1e-12
            and sizing <= equity + 1e-9
        ):
            fill = dict(
                symbol=symbol,
                security_id=symbol,
                side="buy" if buy else "sell",
                shares=quantity,
                reference_price=price,
                execution_price=fill_price,
                commission_usd=commission,
                commission_gbp=commission * rate,
                slippage_usd=slippage,
                slippage_gbp=slippage * rate,
                fx_friction_usd=friction,
                fx_friction_gbp=friction * rate,
                gbp_per_usd=rate,
                mandatory=required,
            )
            return _ReferenceTrade(candidate, fill, conversion)
        next_sizing = min(sizing, equity * (1 - 1e-12))
        if abs(next_sizing - sizing) <= 1e-10:
            return _ReferenceTrade(account, None, None, "post_cost_reference_infeasible")
        sizing = next_sizing
    return _ReferenceTrade(account, None, None, "post_cost_reference_nonconvergence")


def run_v2_benchmarks(
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
    modes: tuple[str, ...] = ("cash", "spy_buy_hold", "spy_risk_budget"),
) -> dict[str, dict[str, Any]]:
    """Return three engine-compatible diagnostic ledgers on exactly the run dates.

    Cash earns zero GBP return and pays no activity fee; the SPY references pay the
    configured monthly fee and modeled trade/conversion costs. Buy-and-hold first
    decides at the start close and trades at the later configured opening session.
    Risk-budget SPY uses monthly increases and daily reductions, weekly SPY regime,
    max(20,long) covariance risk, and the same permanently latched account halt.
    Its soft overlay prevents gross increases; concentration caps are inapplicable
    to this explicitly single-asset diagnostic. Unpaid dividends are receivables.
    """
    sessions = market.calendar.sessions
    if start not in sessions or end not in sessions or start > end:
        raise ValueError("benchmark bounds must be ordered calendar sessions")
    if not math.isfinite(initial_capital_gbp) or initial_capital_gbp <= 0:
        raise ValueError("initial capital must be positive")
    if not math.isfinite(monthly_fee_gbp) or monthly_fee_gbp < 0:
        raise ValueError("monthly fee must be nonnegative")
    requested = costs or FeeModel()
    model = replace(
        requested,
        commission_min_usd=max(requested.commission_min_usd, config.commission_per_order_usd),
        slippage_bps=max(requested.slippage_bps, config.slippage_bps),
        fx_friction_bps=max(requested.fx_friction_bps, config.fx_buffer_bps),
    )
    if (
        any(not math.isfinite(v) or v < 0 for v in asdict(model).values())
        or model.slippage_bps >= 10000
        or model.conversion_bps >= 10000
    ):
        raise ValueError("invalid reference cost model")
    spy_id = market.benchmark_id
    spy_bars = market.bars.get(spy_id, {})
    spy = {day: row.adjusted_close for day, row in spy_bars.items()}
    dates = tuple(day for day in sessions if start <= day <= end)
    selections = set(selection_dates(market.calendar, config))
    month_ends = set(
        selection_dates(market.calendar, replace(config, selection_schedule="monthly"))
    )
    first_rate = fx_history.at(
        _timestamp(start, 9, 30), max_age_days=config.max_fx_age_days
    ).gbp_per_usd
    actions: defaultdict[date, list[Any]] = defaultdict(list)
    for action in market.actions:
        if action.security_id == spy_id:
            actions[action.action_date].append(action)
    results: dict[str, dict[str, Any]] = {}
    if len(set(modes)) != len(modes) or set(modes) - {"cash", "spy_buy_hold", "spy_risk_budget"}:
        raise ValueError("unknown or duplicate benchmark mode")
    for mode in modes:
        account = Account(initial_capital_gbp, 0.0, {})
        state = V2DrawdownState(initial_capital_gbp)
        regime = V2Regime()
        previous_gross = 0.0
        # execution index, signal date, target, mandatory, reason
        pending: tuple[int, date, float, bool, str] | None = None
        points: list[dict[str, Any]] = []
        fills: list[dict[str, Any]] = []
        conversions: list[dict[str, Any]] = []
        fees: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        for index, day in enumerate(sessions):
            if day > end:
                break
            if day < start:
                if mode == "spy_risk_budget":
                    regime = update_weekly_regime(regime, spy, day, market.calendar, config)
                continue
            rate_open = fx_history.at(
                _timestamp(day, 9, 30), max_age_days=config.max_fx_age_days
            ).gbp_per_usd
            rate = fx_history.at(
                _timestamp(day, 16), max_age_days=config.max_fx_age_days
            ).gbp_per_usd
            row = spy_bars.get(day)
            if mode != "cash" and row is None:
                raise ValueError(f"missing SPY raw bar for reference: {day}")
            if (
                mode != "cash"
                and row is not None
                and (
                    not math.isfinite(row.open)
                    or row.open <= 0
                    or not math.isfinite(row.close)
                    or row.close <= 0
                )
            ):
                raise ValueError("invalid SPY tradable price")
            close = row.close if row is not None and mode != "cash" else 1.0
            for action in sorted(actions[day], key=lambda a: a.action_type != "split"):
                quantity = account.holdings.get(spy_id, 0.0)
                if quantity <= 0:
                    continue
                if not math.isfinite(action.value) or action.value < 0:
                    raise ValueError("invalid SPY corporate action")
                if action.action_type == "split":
                    if action.value == 0:
                        raise ValueError("zero SPY split factor")
                    account = replace(account, holdings={spy_id: quantity * action.value})
                elif action.action_type == "dividend":
                    account = replace(
                        account, receivables_usd=account.receivables_usd + quantity * action.value
                    )
                    issues.append(
                        dict(
                            date=day.isoformat(),
                            reason="dividend_payment_date_unavailable_receivable_only",
                        )
                    )
                else:
                    raise ValueError("unsupported SPY reference corporate-action disposition")
            if pending is not None and pending[0] <= index:
                _, signal, target, mandatory, reason = pending
                assert row is not None
                trade = _trade(
                    account,
                    spy_id,
                    row.open,
                    rate_open,
                    target,
                    config,
                    model,
                    fractional=fractional,
                    required=mandatory,
                    reductions_only=reason == "risk_reduction",
                )
                if trade.issue:
                    issues.append(dict(date=day.isoformat(), reason=trade.issue))
                else:
                    account = trade.account
                    nav_open = _nav(account, spy_id, row.open, rate_open)
                    previous_gross = (
                        account.holdings.get(spy_id, 0.0) * row.open * rate_open / nav_open
                    )
                    if trade.fill:
                        fills.append(
                            dict(
                                trade.fill,
                                date=day.isoformat(),
                                signal_date=signal.isoformat(),
                                reason=reason,
                            )
                        )
                    if trade.conversion:
                        conversions.append(dict(trade.conversion, date=day.isoformat()))
                decisions.append(
                    dict(
                        signal_date=signal.isoformat(),
                        execution_date=day.isoformat(),
                        reason=reason,
                        target_weights={spy_id: target} if target else {},
                        status="rejected" if trade.issue else "applied",
                    )
                )
                pending = None
            if mode != "cash" and day in month_ends and monthly_fee_gbp:
                if account.cash_gbp < monthly_fee_gbp:
                    raise ValueError("insufficient GBP cash for reference monthly fee")
                account = replace(account, cash_gbp=account.cash_gbp - monthly_fee_gbp)
                fees.append(
                    dict(date=day.isoformat(), amount_gbp=monthly_fee_gbp, kind="monthly_activity")
                )
            nav = _nav(account, spy_id, close, rate)
            state = state.observe(nav)
            gross = account.holdings.get(spy_id, 0.0) * close * rate / nav
            estimated: float | None = None
            if mode == "spy_buy_hold" and day == start:
                pending = (
                    index + config.execution_delay_sessions,
                    day,
                    1 - config.cash_buffer,
                    False,
                    "buy_hold_entry",
                )
            elif mode == "spy_risk_budget":
                regime = update_weekly_regime(regime, spy, day, market.calendar, config)
                if not regime.valid:
                    issues.append(dict(date=day.isoformat(), reason=regime.reason))
                ceiling = (
                    min(regime.ceiling, previous_gross) if state.soft_active else regime.ceiling
                )
                try:
                    history = sessions[max(0, index - config.long_covariance_window) : index + 1]
                    if len(history) != config.long_covariance_window + 1:
                        raise ValueError("insufficient covariance history")
                    covariance = estimate_dual_covariance(
                        {spy_id: tuple(spy[d] for d in history)},
                        longer_window=config.long_covariance_window,
                    )
                    unit_risk = covariance.volatility({spy_id: 1.0})
                    estimated = gross * unit_risk
                    risk_ceiling = min(ceiling, config.volatility_ceiling / unit_risk)
                except (KeyError, ValueError) as exc:
                    issues.append(dict(date=day.isoformat(), reason=f"invalid_risk_inputs:{exc}"))
                    risk_ceiling = min(gross, ceiling)
                    regime = replace(regime, valid=False)
                if state.hard_halted:
                    risk_ceiling = 0.0
                # A delayed monthly entry is risk even before any shares fill.
                # Invalid inputs/off/halt cancel discretionary pending intent;
                # valid lower capacity tightens it without postponing its deadline.
                if pending is not None and pending[4] == "monthly_selection":
                    if not regime.valid or ceiling <= 0 or state.hard_halted:
                        decisions.append(
                            dict(
                                signal_date=pending[1].isoformat(),
                                execution_date=None,
                                cancelled_at=day.isoformat(),
                                reason=pending[4],
                                status="cancelled_risk_inputs_or_regime",
                            )
                        )
                        pending = None
                    elif pending[2] > risk_ceiling:
                        pending = (pending[0], pending[1], risk_ceiling, pending[3], pending[4])
                reduce = gross > risk_ceiling + 1e-10
                monthly = day in selections and regime.valid and not state.hard_halted
                if reduce or monthly:
                    target = min(gross, risk_ceiling) if reduce else risk_ceiling
                    if pending is not None and reduce:
                        pending = (
                            pending[0],
                            pending[1],
                            min(pending[2], target),
                            True,
                            "risk_reduction",
                        )
                    elif pending is None:
                        pending = (
                            index + config.execution_delay_sessions,
                            day,
                            target,
                            reduce,
                            "risk_reduction" if reduce else "monthly_selection",
                        )
            points.append(
                dict(
                    date=day.isoformat(),
                    equity_gbp=nav,
                    equity_usd=nav / rate,
                    cash_gbp=account.cash_gbp,
                    cash_usd=account.cash_usd,
                    receivables_usd=account.receivables_usd,
                    gross_exposure=gross,
                    drawdown=-state.drawdown,
                    hard_halted=state.hard_halted if mode == "spy_risk_budget" else False,
                    soft_active=state.soft_active if mode == "spy_risk_budget" else False,
                    regime=regime.reason if mode == "spy_risk_budget" else mode,
                    estimated_volatility=estimated,
                    holdings=dict(account.holdings),
                )
            )
        if pending:
            decisions.append(
                dict(
                    signal_date=pending[1].isoformat(),
                    execution_date=None,
                    reason=pending[4],
                    status="no_next_session",
                )
            )
        assert len(points) == len(dates)
        results[mode] = dict(
            strategy_version=f"v2-reference-{mode}",
            benchmark_reference=True,
            stock_cap_exempt=mode != "cash",
            evidence_scope="development",
            config_sha256=config.sha256,
            initial_capital_gbp=initial_capital_gbp,
            initial_capital_usd=initial_capital_gbp / first_rate,
            fractional=fractional,
            costs=asdict(model),
            monthly_fee_gbp=0 if mode == "cash" else monthly_fee_gbp,
            points=points,
            fills=fills,
            conversions=conversions,
            fees=fees,
            issues=issues,
            decisions=decisions,
            exclusions=[],
            episodes=[],
            closed_lots=[],
            invalid_evidence=bool(issues),
            deployment_admissible=False,
            paper_execution_permitted=False,
            reference_notes="Reference only; no strategy certification or trade gates. "
            "SPY cap exemption; soft overlay freezes gross, hard halt at 15%. "
            "Buy-hold has no stops; cash has no activity fee.",
        )
    return results
