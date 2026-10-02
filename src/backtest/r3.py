"""Shared causal R3 development simulator for momentum and learned scores.

This module is deliberately offline.  It has no broker transport and uses one
raw-share/account policy for every score family.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from src.config.r3 import R3Config
from src.config.r3_development import R3DevelopmentConfig
from src.data.calendar import TradingCalendar
from src.data.canonical_historical import VerifiedCanonicalInputs
from src.data.fx import FXHistory
from src.data.r3_evidence import CashActionEvidenceSet
from src.portfolio.v2 import build_v2_targets, estimate_dual_covariance


@dataclass(frozen=True)
class R3MarketBar:
    security_id: str
    session: date
    open_usd: float
    close_usd: float
    adjusted_close: float
    volume: int


@dataclass(frozen=True)
class R3MarketAction:
    security_id: str
    action_type: Literal["split", "dividend", "delisting"]
    effective_date: date
    value_per_share: float
    payment_date: date | None
    withholding_fraction: float | None


@dataclass(frozen=True)
class R3MarketData:
    sessions: tuple[date, ...]
    week_ends: frozenset[date]
    benchmark_id: str
    bars: tuple[R3MarketBar, ...]
    actions: tuple[R3MarketAction, ...]
    fx: FXHistory


@dataclass(frozen=True)
class R3Account:
    cash_gbp: float
    holdings: dict[str, int] = field(default_factory=dict)
    high_water_gbp: float = 3000.0
    soft_active: bool = False
    hard_halted: bool = False


@dataclass(frozen=True)
class R3Fill:
    session: date
    decision_date: date
    security_id: str
    side: Literal["buy", "sell"]
    shares: int
    reference_price_usd: float
    execution_price_usd: float
    commission_gbp: float
    slippage_gbp: float
    fx_friction_gbp: float
    conversion_gbp: float
    mandatory: bool

    @property
    def trading_cost_gbp(self) -> float:
        return (
            self.commission_gbp
            + self.slippage_gbp
            + self.fx_friction_gbp
            + self.conversion_gbp
        )


@dataclass(frozen=True)
class R3NavPoint:
    session: date
    nav_gbp: float
    gross_exposure: float
    drawdown: float
    hard_halted: bool


@dataclass(frozen=True)
class R3SimulationResult:
    candidate_id: str
    evaluation_kind: Literal["cohort_12m", "continuous"]
    start_session: date
    end_session: date
    initial_capital_gbp: float
    terminal_wealth_gbp: float | None
    gross_terminal_wealth_gbp: float | None
    trading_net_terminal_wealth_gbp: float | None
    net_profit_gbp: float | None
    return_12m: float | None
    return_since_inception: float | None
    maximum_drawdown: float | None
    mean_exposure: float | None
    halted_sessions: int
    target_attained: bool
    fills: tuple[R3Fill, ...]
    nav: tuple[R3NavPoint, ...]
    skip_reasons: dict[str, int]
    commission_gbp: float
    slippage_gbp: float
    fx_friction_gbp: float
    conversion_gbp: float
    account_fees_gbp: float
    operating_cost_gbp: float
    liquidation_reserve_gbp: float
    unresolved_accrual_gbp: float
    failure: str | None

    def summary(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("fills")
        value.pop("nav")
        return value


@dataclass
class _Receivable:
    security_id: str
    amount_usd: float
    payment_date: date | None


def build_r3_market_data(
    canonical: VerifiedCanonicalInputs,
    calendar: TradingCalendar,
    fx: FXHistory,
    cash_actions: CashActionEvidenceSet,
    *,
    start: date | None = None,
    end: date | None = None,
) -> R3MarketData:
    benchmark_ids = {row.security_id for row in canonical.bars if row.symbol == "SPY"}
    if len(benchmark_ids) != 1:
        raise ValueError("R3 requires exactly one stable SPY identity")
    evidence = {
        (row.security_id, row.effective_date, row.action_type): row
        for row in cash_actions.rows
    }
    actions: list[R3MarketAction] = []
    for row in canonical.actions:
        if start is not None and row.action_date < start:
            continue
        if end is not None and row.action_date > end:
            continue
        supplemental = evidence.get((row.security_id, row.action_date, row.action_type))
        if row.action_type == "split":
            actions.append(
                R3MarketAction(row.security_id, "split", row.action_date, row.value, None, None)
            )
        else:
            actions.append(
                R3MarketAction(
                    row.security_id,
                    row.action_type,  # type: ignore[arg-type]
                    row.action_date,
                    row.value if supplemental is None else supplemental.value_per_share,
                    None if supplemental is None else supplemental.payment_date,
                    None if supplemental is None else supplemental.withholding_fraction,
                )
            )
    return R3MarketData(
        tuple(
            session
            for session in calendar.sessions
            if (start is None or session >= start) and (end is None or session <= end)
        ),
        frozenset(
            session
            for session in calendar.week_ends
            if (start is None or session >= start) and (end is None or session <= end)
        ),
        benchmark_ids.pop(),
        tuple(
            R3MarketBar(
                row.security_id,
                row.date,
                row.open,
                row.close,
                row.adjusted_close,
                row.volume,
            )
            for row in canonical.bars
            if (start is None or row.date >= start) and (end is None or row.date <= end)
        ),
        tuple(actions),
        fx,
    )


def _at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, ZoneInfo("America/New_York"))


def _anniversary(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


def _select(
    ranked: Sequence[str], holdings: Mapping[str, int], config: R3Config
) -> tuple[str, ...]:
    ranks = {security_id: index + 1 for index, security_id in enumerate(ranked)}
    incumbents = sorted(
        (
            security_id
            for security_id, shares in holdings.items()
            if shares > 0
            and ranks.get(security_id, config.incumbent_rank + 1)
            <= config.incumbent_rank
        ),
        key=lambda security_id: (ranks[security_id], security_id),
    )
    selected = incumbents[: config.target_positions]
    for security_id in ranked:
        if len(selected) >= config.target_positions:
            break
        if security_id not in selected:
            selected.append(security_id)
    return tuple(selected)


def simulate_r3_account(
    *,
    candidate_id: str,
    scores_by_decision: Mapping[date, Mapping[str, float]],
    market: R3MarketData,
    config: R3Config,
    development: R3DevelopmentConfig,
    first_decision: date,
    final_session: date | None = None,
    initial_account: R3Account | None = None,
    continuous: bool = False,
) -> R3SimulationResult:
    """Run one causal account; score changes are the only candidate-specific input."""
    if first_decision not in market.sessions:
        raise ValueError("first decision must be an exchange session")
    first_index = market.sessions.index(first_decision) + 1
    if first_index >= len(market.sessions):
        raise ValueError("first decision has no following execution session")
    start = market.sessions[first_index]
    endpoint = final_session if continuous and final_session is not None else _anniversary(start)
    eligible_sessions = tuple(
        day
        for day in market.sessions[first_index:]
        if day <= endpoint and (final_session is None or day <= final_session)
    )
    if not eligible_sessions:
        raise ValueError("simulation has no sessions")
    end = eligible_sessions[-1]
    if (
        not continuous
        and final_session is None
        and end < endpoint
        and market.sessions[-1] < endpoint
    ):
        return _failed_result(candidate_id, start, end, "12_month_endpoint_not_observed", config)
    bars: dict[str, dict[date, R3MarketBar]] = defaultdict(dict)
    for row in market.bars:
        bars[row.security_id][row.session] = row
    actions_by_day: dict[date, list[R3MarketAction]] = defaultdict(list)
    for action in market.actions:
        if start <= action.effective_date <= end:
            actions_by_day[action.effective_date].append(action)
    payment_days: dict[date, list[_Receivable]] = defaultdict(list)
    account = initial_account or R3Account(config.initial_capital_gbp)
    cash = account.cash_gbp
    holdings = dict(account.holdings)
    high_water = account.high_water_gbp
    soft = account.soft_active
    hard = account.hard_halted
    fills: list[R3Fill] = []
    nav_rows: list[R3NavPoint] = []
    skips: defaultdict[str, int] = defaultdict(int)
    receivables: list[_Receivable] = []
    pending_targets: tuple[date, dict[str, float], set[str]] | None = None
    pending_soft_reduction = False
    reductions_only = False
    regime_ceiling = 0.0
    regime_valid = False
    first_fee_month: tuple[int, int] | None = None
    account_fees = 0.0
    unresolved_failure: str | None = None

    def rate(day: date, clock: time) -> float:
        return market.fx.at(_at(day, clock), max_age_days=config.max_fx_age_days).gbp_per_usd

    def price_map(day: date, field: Literal["open_usd", "close_usd"]) -> dict[str, float]:
        result: dict[str, float] = {}
        for security_id in holdings:
            row = bars.get(security_id, {}).get(day)
            if row is None:
                raise ValueError(f"missing held price:{security_id}:{day.isoformat()}")
            result[security_id] = getattr(row, field)
        return result

    def equity(day: date, field: Literal["open_usd", "close_usd"]) -> float:
        fx_rate = rate(day, time(9, 30) if field == "open_usd" else time(16))
        values: list[float] = []
        for security_id, shares in holdings.items():
            held_bar = bars.get(security_id, {}).get(day)
            if held_bar is None:
                raise ValueError(f"missing held valuation:{security_id}:{day.isoformat()}")
            values.append(shares * getattr(held_bar, field) * fx_rate)
        return cash + math.fsum(values)

    # The first registered signal exists before funding/execution; seed its
    # next-session plan without pretending it was observed on the fill date.
    initial_scores = scores_by_decision.get(first_decision)
    benchmark = bars.get(market.benchmark_id, {})
    decision_index = market.sessions.index(first_decision)
    regime_history = market.sessions[
        max(0, decision_index - config.market_sma_sessions + 1) : decision_index + 1
    ]
    if (
        len(regime_history) == config.market_sma_sessions
        and all(session in benchmark for session in regime_history)
    ):
        regime_sma = math.fsum(
            benchmark[session].adjusted_close for session in regime_history
        ) / len(regime_history)
        regime_ceiling = (
            1 - config.cash_buffer
            if benchmark[first_decision].adjusted_close > regime_sma
            else 0.0
        )
        regime_valid = True
    if initial_scores is not None and regime_valid and regime_ceiling > 0:
        ranked = tuple(
            sorted(initial_scores, key=lambda key: (-initial_scores[key], key))
        )
        selected = _select(ranked, holdings, config)
        covariance_sessions = market.sessions[
            max(0, decision_index - 63) : decision_index + 1
        ]
        histories = {
            security_id: [
                bars[security_id][session].adjusted_close
                for session in covariance_sessions
            ]
            for security_id in selected
            if all(session in bars.get(security_id, {}) for session in covariance_sessions)
        }
        if len(histories) == len(selected):
            pending_targets = (
                first_decision,
                build_v2_targets(
                    selected,
                    estimate_dual_covariance(histories),
                    regime_ceiling=regime_ceiling,
                    cash_buffer=config.cash_buffer,
                    target_annual_volatility=config.volatility_ceiling,
                    max_position_weight=config.max_position_weight,
                ),
                set(),
            )
        else:
            skips["missing_covariance_blocks_increase"] += 1
    elif initial_scores is not None and not regime_valid:
        skips["missing_regime_blocks_increase"] += 1

    def trade(
        day: date,
        decision: date,
        security_id: str,
        difference: int,
        mandatory: bool,
    ) -> bool:
        nonlocal cash
        if difference == 0:
            return True
        row = bars.get(security_id, {}).get(day)
        if row is None:
            skips["missing_tradable_open"] += 1
            return False
        buying = difference > 0
        quantity = abs(difference)
        fx_rate = rate(day, time(9, 30))
        sign = 1 if buying else -1
        execution = row.open_usd * (1 + sign * development.slippage_bps / 10_000)
        notional_usd = quantity * execution
        reference_gbp = quantity * row.open_usd * fx_rate
        commission = max(
            development.minimum_commission_usd,
            quantity * development.commission_per_share_usd,
        ) * fx_rate
        slippage = quantity * abs(execution - row.open_usd) * fx_rate
        fx_friction = notional_usd * development.fx_friction_bps / 10_000 * fx_rate
        conversion = notional_usd * development.conversion_bps / 10_000 * fx_rate
        cost = commission + slippage + fx_friction + conversion
        if buying:
            estimated_round_trip = 2 * cost
            if (
                reference_gbp <= 0
                or estimated_round_trip / reference_gbp > config.round_trip_cost_ceiling
            ):
                skips["round_trip_cost_ceiling"] += 1
                return False
            decision_index = market.sessions.index(decision)
            trailing_sessions = market.sessions[
                max(0, decision_index - 19) : decision_index + 1
            ]
            trailing = [
                bars[security_id][session].close_usd * bars[security_id][session].volume
                for session in trailing_sessions
                if session in bars[security_id]
            ]
            if (
                len(trailing) != 20
                or notional_usd
                > statistics.median(trailing) * config.capacity_fraction
            ):
                skips["capacity_or_history"] += 1
                return False
            debit = notional_usd * fx_rate + commission + fx_friction + conversion
            post_cash = cash - debit
            projected_nav = max(0.0, equity(day, "open_usd") - cost)
            required_cash = projected_nav * config.cash_buffer + development.liquidation_reserve_gbp
            if post_cash < required_cash - 1e-9:
                skips["cash_buffer_or_fee_reserve"] += 1
                return False
            cash = post_cash
        else:
            proceeds = notional_usd * fx_rate - commission - fx_friction - conversion
            if proceeds < 0 and cash + proceeds < -1e-9:
                skips["mandatory_fee_unaffordable" if mandatory else "fee_unaffordable"] += 1
                return False
            cash += proceeds
        holdings[security_id] = holdings.get(security_id, 0) + difference
        if holdings[security_id] <= 0:
            holdings.pop(security_id, None)
        fills.append(
            R3Fill(
                day,
                decision,
                security_id,
                "buy" if buying else "sell",
                quantity,
                row.open_usd,
                execution,
                commission,
                slippage,
                fx_friction,
                conversion,
                mandatory,
            )
        )
        return True

    for day in eligible_sessions:
        # Corporate actions take precedence over discretionary trading.
        for action in sorted(actions_by_day.get(day, ()), key=lambda row: row.security_id):
            shares = holdings.get(action.security_id, 0)
            if shares <= 0:
                continue
            if action.action_type == "split":
                new_shares = shares * action.value_per_share
                if not float(new_shares).is_integer():
                    unresolved_failure = "unsupported_fractional_split_residual"
                    break
                holdings[action.security_id] = int(new_shares)
            elif action.action_type == "delisting" and action.payment_date is None:
                unresolved_failure = "held_delisting_recovery_unresolved"
                break
            else:
                withholding = action.withholding_fraction
                if withholding is None:
                    withholding = 0.15  # recorded development assumption, never qualification
                item = _Receivable(
                    action.security_id,
                    shares * action.value_per_share * (1 - withholding),
                    action.payment_date,
                )
                receivables.append(item)
                if item.payment_date is not None:
                    payment_session = next(
                        (
                            session
                            for session in eligible_sessions
                            if session >= item.payment_date
                        ),
                        None,
                    )
                    if payment_session is not None:
                        payment_days[payment_session].append(item)
                if action.action_type == "delisting":
                    holdings.pop(action.security_id, None)
        if unresolved_failure:
            break
        for item in payment_days.get(day, ()):
            cash += item.amount_usd * rate(day, time(9, 30))
            receivables.remove(item)
        missing_held = next(
            (
                security_id
                for security_id, shares in holdings.items()
                if shares > 0 and day not in bars.get(security_id, {})
            ),
            None,
        )
        if missing_held is not None:
            unresolved_failure = (
                f"missing held valuation:{missing_held}:{day.isoformat()}"
            )
            break

        month = (day.year, day.month)
        if first_fee_month != month and (
            continuous
            or account_fees < 12 * development.monthly_account_fee_gbp - 1e-9
        ):
            fee = development.monthly_account_fee_gbp
            if cash < fee:
                unresolved_failure = "monthly_account_fee_unaffordable"
                break
            cash -= fee
            account_fees += fee
            first_fee_month = month

        if pending_targets is not None:
            decision, requested, mandatory = pending_targets
            open_fx = rate(day, time(9, 30))
            open_nav = equity(day, "open_usd")
            current_weights = {
                security_id: shares * bars[security_id][day].open_usd * open_fx / open_nav
                for security_id, shares in holdings.items()
            }
            if pending_soft_reduction:
                requested = {
                    security_id: min(weight, config.soft_position_weight)
                    for security_id, weight in current_weights.items()
                }
            all_ids = sorted(set(holdings) | set(requested))
            desired: dict[str, int] = {}
            for security_id in all_ids:
                target_bar = bars.get(security_id, {}).get(day)
                if target_bar is None:
                    unresolved_failure = f"missing held/target open:{security_id}"
                    break
                weight = requested.get(security_id, 0.0)
                if security_id in current_weights and security_id not in mandatory:
                    if abs(weight - current_weights[security_id]) < config.resize_band:
                        desired[security_id] = holdings.get(security_id, 0)
                        continue
                desired[security_id] = math.floor(
                    open_nav * weight / (target_bar.open_usd * open_fx)
                )
            if unresolved_failure:
                break
            for security_id in all_ids:
                difference = desired[security_id] - holdings.get(security_id, 0)
                if difference < 0:
                    trade(day, decision, security_id, difference, security_id in mandatory)
            if not hard and not reductions_only:
                for security_id in all_ids:
                    difference = desired[security_id] - holdings.get(security_id, 0)
                    if difference > 0:
                        trade(day, decision, security_id, difference, False)
            pending_targets = None
            pending_soft_reduction = False
            reductions_only = False

        if hard and holdings and pending_targets is None:
            pending_targets = (day, {}, set(holdings))
            reductions_only = True

        # Weekly risk-off observations cause reductions; re-entry remains monthly.
        if day in market.week_ends:
            benchmark = bars.get(market.benchmark_id, {})
            day_index = market.sessions.index(day)
            history = market.sessions[
                max(0, day_index - config.market_sma_sessions + 1) : day_index + 1
            ]
            if len(history) == config.market_sma_sessions and all(x in benchmark for x in history):
                sma = math.fsum(benchmark[x].adjusted_close for x in history) / len(history)
                regime_ceiling = (
                    1 - config.cash_buffer
                    if benchmark[day].adjusted_close > sma
                    else 0.0
                )
                regime_valid = True
                if regime_ceiling == 0 and holdings:
                    pending_targets = (day, {}, set(holdings))
                    reductions_only = True
            else:
                regime_valid = False

        # Month-end scoring and target construction. Missing/stale model output blocks increases.
        if day in scores_by_decision and not hard:
            scores = scores_by_decision[day]
            ranked = tuple(sorted(scores, key=lambda key: (-scores[key], key)))
            selected = _select(ranked, holdings, config)
            mandatory = set(holdings) - set(scores)
            if not regime_valid:
                skips["missing_regime_blocks_increase"] += 1
                targets = {
                    security_id: 0.0 for security_id in holdings if security_id in scores
                }
            elif regime_ceiling == 0:
                targets = {}
                mandatory = set(holdings)
            else:
                day_index = market.sessions.index(day)
                history_sessions = market.sessions[
                    max(0, day_index - 63) : day_index + 1
                ]
                histories = {
                    security_id: [bars[security_id][x].adjusted_close for x in history_sessions]
                    for security_id in selected
                    if all(x in bars.get(security_id, {}) for x in history_sessions)
                }
                if len(histories) != len(selected):
                    skips["missing_covariance_blocks_increase"] += 1
                    targets = {}
                else:
                    covariance = estimate_dual_covariance(histories)
                    targets = build_v2_targets(
                        selected,
                        covariance,
                        regime_ceiling=regime_ceiling,
                        cash_buffer=config.cash_buffer,
                        target_annual_volatility=config.volatility_ceiling,
                        max_position_weight=(
                            config.soft_position_weight if soft else config.max_position_weight
                        ),
                        previous_target_gross=(
                            sum(
                                shares * bars[security_id][day].close_usd * rate(day, time(16))
                                / equity(day, "close_usd")
                                for security_id, shares in holdings.items()
                            )
                            if soft and holdings
                            else None
                        ),
                    )
                mandatory |= set(holdings) - set(targets)
            pending_targets = (day, targets, mandatory)

        try:
            close_nav = equity(day, "close_usd")
        except ValueError as error:
            unresolved_failure = str(error)
            break
        high_water = max(high_water, close_nav)
        drawdown = close_nav / high_water - 1
        if drawdown <= -config.hard_drawdown + 1e-12:
            hard = True
            soft = True
            if holdings:
                pending_targets = (day, {}, set(holdings))
                reductions_only = True
        elif drawdown <= -config.soft_drawdown + 1e-12:
            soft = True
            pending_soft_reduction = bool(holdings)
            reductions_only = bool(holdings)
            if holdings and pending_targets is None:
                pending_targets = (day, {}, set())
        else:
            soft = False
        fx_close = rate(day, time(16))
        gross = (
            math.fsum(
                shares * bars[security_id][day].close_usd * fx_close
                for security_id, shares in holdings.items()
            )
            / close_nav
            if close_nav > 0
            else 0.0
        )
        weights = {
            security_id: shares * bars[security_id][day].close_usd * fx_close / close_nav
            for security_id, shares in holdings.items()
        }
        if len(holdings) > config.max_holdings or gross > 1 + 1e-10:
            unresolved_failure = "hard_portfolio_invariant_breached"
            break
        daily_cap = config.soft_position_weight if soft else config.max_position_weight
        allowed_gross = min(1.0 - config.cash_buffer, 1.0)
        if not hard and (
            any(weight > daily_cap + 1e-12 for weight in weights.values())
            or gross > allowed_gross + 1e-12
        ):
            reduction_targets = {
                security_id: min(weight, daily_cap)
                for security_id, weight in weights.items()
            }
            reduction_gross = math.fsum(reduction_targets.values())
            if reduction_gross > allowed_gross:
                scale = allowed_gross / reduction_gross
                reduction_targets = {
                    security_id: weight * scale
                    for security_id, weight in reduction_targets.items()
                }
            mandatory_reductions = {
                security_id
                for security_id, weight in weights.items()
                if reduction_targets[security_id] < weight - 1e-12
            }
            pending_targets = (day, reduction_targets, mandatory_reductions)
            reductions_only = True
            skips["daily_position_or_gross_reduction"] += 1
        nav_rows.append(R3NavPoint(day, close_nav, gross, drawdown, hard))

    if unresolved_failure or not nav_rows:
        return _failed_result(
            candidate_id,
            start,
            nav_rows[-1].session if nav_rows else start,
            unresolved_failure or "no_valued_sessions",
            config,
            fills=tuple(fills),
            nav=tuple(nav_rows),
            skips=dict(sorted(skips.items())),
        )
    operating = development.annual_operating_cost_gbp
    if cash < operating:
        return _failed_result(
            candidate_id,
            start,
            nav_rows[-1].session,
            "annual_operating_cost_unaffordable",
            config,
            fills=tuple(fills),
            nav=tuple(nav_rows),
            skips=dict(sorted(skips.items())),
        )
    final_nav = nav_rows[-1].nav_gbp - operating
    trade_cost = math.fsum(fill.trading_cost_gbp for fill in fills)
    unresolved_accrual = math.fsum(
        item.amount_usd * rate(nav_rows[-1].session, time(16)) for item in receivables
    )
    terminal = final_nav + unresolved_accrual - development.liquidation_reserve_gbp
    trading_net = terminal + account_fees + operating
    gross_terminal = trading_net + trade_cost
    total_return = terminal / config.initial_capital_gbp - 1
    return_12m = None if continuous else total_return
    return R3SimulationResult(
        candidate_id,
        "continuous" if continuous else "cohort_12m",
        start,
        nav_rows[-1].session,
        config.initial_capital_gbp,
        terminal,
        gross_terminal,
        trading_net,
        terminal - config.initial_capital_gbp,
        return_12m,
        total_return,
        min(row.drawdown for row in nav_rows),
        statistics.fmean(row.gross_exposure for row in nav_rows),
        sum(row.hard_halted for row in nav_rows),
        (
            not continuous
            and terminal > 3300
            and terminal - config.initial_capital_gbp > 300
            and total_return > 0.10
        ),
        tuple(fills),
        tuple(nav_rows),
        dict(sorted(skips.items())),
        math.fsum(fill.commission_gbp for fill in fills),
        math.fsum(fill.slippage_gbp for fill in fills),
        math.fsum(fill.fx_friction_gbp for fill in fills),
        math.fsum(fill.conversion_gbp for fill in fills),
        account_fees,
        operating,
        development.liquidation_reserve_gbp,
        unresolved_accrual,
        None,
    )


def _failed_result(
    candidate_id: str,
    start: date,
    end: date,
    failure: str,
    config: R3Config,
    *,
    fills: tuple[R3Fill, ...] = (),
    nav: tuple[R3NavPoint, ...] = (),
    skips: dict[str, int] | None = None,
) -> R3SimulationResult:
    return R3SimulationResult(
        candidate_id,
        "cohort_12m",
        start,
        end,
        config.initial_capital_gbp,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        sum(row.hard_halted for row in nav),
        False,
        fills,
        nav,
        skips or {},
        math.fsum(row.commission_gbp for row in fills),
        math.fsum(row.slippage_gbp for row in fills),
        math.fsum(row.fx_friction_gbp for row in fills),
        math.fsum(row.conversion_gbp for row in fills),
        0.0,
        0.0,
        0.0,
        0.0,
        failure,
    )
