"""Causal session-based momentum, actual-fill selection, and weekly SPY state.

Stable security IDs occupy the existing ``symbol`` field. Callers must apply the
certified point-in-time universe/raw-price/liquidity eligibility before ranking.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from src.config.v2 import V2Config
from src.data.calendar import TradingCalendar
from src.strategy.ranking import RankedStock, RankingExclusion, RankingResult
from src.strategy.selection import SelectionResult, select_with_rank_hysteresis


def _sessions(calendar: TradingCalendar) -> tuple[date, ...]:
    if calendar.exchange != "XNYS" or not calendar.version or not calendar.source_sha256:
        raise ValueError("V2 requires a version-pinned XNYS calendar")
    if not calendar.sessions or tuple(sorted(set(calendar.sessions))) != calendar.sessions:
        raise ValueError("calendar sessions must be unique and increasing")
    return calendar.sessions


def completed_week_dates(calendar: TradingCalendar) -> tuple[date, ...]:
    """Require a following calendar session to prove the prior week is complete."""
    sessions = _sessions(calendar)
    return tuple(
        left
        for left, right in zip(sessions, sessions[1:], strict=False)
        if left.isocalendar()[:2] != right.isocalendar()[:2]
    )


def selection_dates(calendar: TradingCalendar, config: V2Config) -> tuple[date, ...]:
    sessions = _sessions(calendar)
    if config.selection_schedule == "biweekly":
        weeks = completed_week_dates(calendar)
        if config.biweekly_anchor not in weeks:
            raise ValueError("biweekly anchor must be a completed week in the pinned calendar")
        anchor = weeks.index(config.biweekly_anchor)
        return tuple(
            day for index, day in enumerate(weeks) if index >= anchor and (index - anchor) % 2 == 0
        )
    offset = 1 if config.selection_schedule == "penultimate_monthly" else 0
    return tuple(
        sessions[index - offset]
        for index in range(len(sessions) - 1)
        if (sessions[index].year, sessions[index].month)
        != (sessions[index + 1].year, sessions[index + 1].month)
        and index >= offset
        and sessions[index - offset].month == sessions[index].month
    )


def rank_v2(
    adjusted_closes: Mapping[str, Mapping[date, float]],
    as_of: date,
    calendar: TradingCalendar,
    config: V2Config,
) -> RankingResult:
    sessions = _sessions(calendar)
    if as_of not in sessions:
        raise ValueError("decision date is not an exchange session")
    index = sessions.index(as_of)
    history = sessions[max(0, index - 252) : index + 1]
    scores: dict[str, float] = {}
    exclusions: list[RankingExclusion] = []
    for identity, prices in sorted(adjusted_closes.items()):
        if not identity:
            raise ValueError("security IDs must not be empty")
        reason = ""
        if len(history) < 253:
            reason = "insufficient_253_session_history"
        elif any(day not in prices for day in history):
            reason = "missing_exchange_session"
        elif any(not math.isfinite(prices[day]) or prices[day] <= 0 for day in history):
            reason = "invalid_adjusted_close"
        if reason:
            exclusions.append(RankingExclusion(identity, reason))
            continue
        values = [prices[day] for day in history]
        momentum = values[-1 - config.numerator_offset] / values[0] - 1
        sma = math.fsum(values[-config.stock_sma :]) / config.stock_sma
        if momentum <= 0:
            exclusions.append(RankingExclusion(identity, "nonpositive_momentum"))
        elif values[-1] <= sma:
            exclusions.append(RankingExclusion(identity, "price_not_above_stock_sma"))
        else:
            scores[identity] = momentum
    ordered = sorted(scores, key=lambda identity: (-scores[identity], identity))
    return RankingResult(
        as_of,
        tuple(
            RankedStock(identity, index + 1, scores[identity])
            for index, identity in enumerate(ordered)
        ),
        tuple(exclusions),
    )


def select_v2(
    ranked: Iterable[RankedStock],
    actual_holdings: Mapping[str, float],
    config: V2Config,
    *,
    mandatory_exclusions: Mapping[str, str] | None = None,
) -> SelectionResult:
    """Only strictly positive actual filled quantities establish incumbency."""
    if any(not math.isfinite(value) or value < 0 for value in actual_holdings.values()):
        raise ValueError("actual holdings must be finite and long-only")
    actual = tuple(sorted(key for key, value in actual_holdings.items() if value > 0))
    return select_with_rank_hysteresis(
        ranked, actual, config.target_positions, mandatory_exclusions=mandatory_exclusions
    )


@dataclass(frozen=True)
class V2Regime:
    ceiling: float = 0.0
    observed_at: date | None = None
    valid: bool = False
    reason: str = "no_completed_week_observation"


def update_weekly_regime(
    state: V2Regime,
    spy_prices: Mapping[date, float],
    as_of: date,
    calendar: TradingCalendar,
    config: V2Config,
) -> V2Regime:
    sessions = _sessions(calendar)
    if as_of not in sessions:
        raise ValueError("regime date is not an exchange session")
    if state.observed_at is not None and state.observed_at > as_of:
        raise ValueError("regime state cannot come from the future")
    if as_of not in completed_week_dates(calendar):
        return state
    index = sessions.index(as_of)
    history = sessions[max(0, index - config.spy_sma + 1) : index + 1]
    if len(history) < config.spy_sma or any(day not in spy_prices for day in history):
        return V2Regime(state.ceiling, state.observed_at, False, "missing_spy_history")
    if any(not math.isfinite(spy_prices[day]) or spy_prices[day] <= 0 for day in history):
        return V2Regime(state.ceiling, state.observed_at, False, "invalid_spy_history")
    sma = math.fsum(spy_prices[day] for day in history) / config.spy_sma
    ceiling = 1 - config.cash_buffer if spy_prices[as_of] > sma else 0.0
    return V2Regime(ceiling, as_of, True, "risk_on" if ceiling else "risk_off")
