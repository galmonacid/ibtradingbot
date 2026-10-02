"""Causal R3 stock-month features and GBP open-to-open labels."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from src.data.fx import FXHistory

R3_FEATURE_NAMES = (
    "recent_return_21",
    "momentum_63_skip21",
    "momentum_126_skip21",
    "momentum_252_skip21",
    "volatility_20",
    "volatility_63",
    "trend_distance_200",
    "drawdown_252",
    "log_median_dollar_volume_20",
    "market_return_21",
    "market_volatility_20",
    "market_trend_distance_200",
)


@dataclass(frozen=True)
class R3Price:
    security_id: str
    session: date
    open_usd: float
    close_usd: float
    adjusted_close: float
    volume: int
    open_at: datetime
    available_at: datetime
    raw_series_id: str
    adjusted_series_id: str

    def __post_init__(self) -> None:
        if not self.security_id.strip() or not self.raw_series_id or not self.adjusted_series_id:
            raise ValueError("stable security and series identities are required")
        if self.open_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("price timestamps must be timezone-aware")
        if self.available_at < self.open_at:
            raise ValueError("daily close data cannot be available before the session open")
        values = (self.open_usd, self.close_usd, self.adjusted_close)
        if any(not math.isfinite(value) or value <= 0 for value in values) or self.volume < 0:
            raise ValueError("prices must be finite positive and volume nonnegative")


@dataclass(frozen=True)
class MembershipEvidence:
    security_id: str
    member_from: date
    member_until_exclusive: date | None
    available_at: datetime
    primary_common_stock: bool
    source_id: str

    def active(self, decision: date, cutoff: datetime) -> bool:
        return (
            self.primary_common_stock
            and self.available_at <= cutoff
            and self.member_from <= decision
            and (
                self.member_until_exclusive is None
                or decision < self.member_until_exclusive
            )
        )


@dataclass(frozen=True)
class R3FeatureRow:
    security_id: str
    decision_date: date
    feature_cutoff: datetime
    source_available_at: datetime
    membership_from: date
    membership_until_exclusive: date | None
    raw_series_id: str
    adjusted_series_id: str
    values: tuple[float, ...]
    exclusion_reasons: tuple[str, ...]
    feature_version: str

    def __post_init__(self) -> None:
        if len(self.values) not in (0, len(R3_FEATURE_NAMES)):
            raise ValueError("feature vector does not match the R3 schema")
        if bool(self.values) == bool(self.exclusion_reasons):
            raise ValueError("a row must be either usable or excluded, never both/neither")


@dataclass(frozen=True)
class R3Action:
    security_id: str
    action_type: Literal["split", "dividend", "delisting"]
    effective_at: datetime
    available_at: datetime
    value_per_share: float
    payment_at: datetime | None = None
    withholding_fraction: float | None = None

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("action timestamps must be timezone-aware")
        if not math.isfinite(self.value_per_share) or self.value_per_share < 0:
            raise ValueError("action value must be finite and nonnegative")
        if self.withholding_fraction is not None and not 0 <= self.withholding_fraction <= 1:
            raise ValueError("withholding fraction must be between zero and one")
        if self.action_type == "split" and self.value_per_share <= 0:
            raise ValueError("split factor must be positive")
        if self.payment_at is not None:
            if self.payment_at.tzinfo is None:
                raise ValueError("cash-action payment timestamp must be timezone-aware")
            if self.payment_at < self.effective_at:
                raise ValueError("cash action cannot pay before its effective timestamp")


@dataclass(frozen=True)
class R3Label:
    security_id: str
    decision_date: date
    entry_at: datetime
    exit_at: datetime
    available_at: datetime | None
    excess_return_gbp: float | None
    unresolved_reason: str | None
    label_version: str

    @property
    def matured(self) -> bool:
        return self.available_at is not None and self.excess_return_gbp is not None


def monthly_decision_dates(sessions: Sequence[date]) -> tuple[date, ...]:
    ordered = tuple(sessions)
    if not ordered or tuple(sorted(set(ordered))) != ordered:
        raise ValueError("sessions must be non-empty, sorted and unique")
    result: dict[tuple[int, int], date] = {}
    for session in ordered:
        result[(session.year, session.month)] = session
    return tuple(result.values())


def _sample_volatility(prices: Sequence[float], index: int, window: int) -> float:
    returns = [prices[pos] / prices[pos - 1] - 1 for pos in range(index - window + 1, index + 1)]
    return statistics.stdev(returns) * math.sqrt(252.0)


def _vector(series: Sequence[R3Price], index: int, market: Sequence[R3Price]) -> tuple[float, ...]:
    prices = [row.adjusted_close for row in series]
    market_prices = [row.adjusted_close for row in market]
    dollar_volume = [row.close_usd * row.volume for row in series]
    sma200 = math.fsum(prices[index - 199 : index + 1]) / 200
    market_sma200 = math.fsum(market_prices[index - 199 : index + 1]) / 200
    median_volume = statistics.median(dollar_volume[index - 19 : index + 1])
    if median_volume <= 0:
        raise ValueError("nonpositive trailing dollar volume")
    return (
        prices[index] / prices[index - 21] - 1,
        prices[index - 21] / prices[index - 63] - 1,
        prices[index - 21] / prices[index - 126] - 1,
        prices[index - 21] / prices[index - 252] - 1,
        _sample_volatility(prices, index, 20),
        _sample_volatility(prices, index, 63),
        prices[index] / sma200 - 1,
        prices[index] / max(prices[index - 251 : index + 1]) - 1,
        math.log(median_volume),
        market_prices[index] / market_prices[index - 21] - 1,
        _sample_volatility(market_prices, index, 20),
        market_prices[index] / market_sma200 - 1,
    )


def build_r3_feature_rows(
    prices: Iterable[R3Price],
    memberships: Iterable[MembershipEvidence],
    sessions: Sequence[date],
    *,
    benchmark_id: str,
    feature_version: str = "r3-stock-month-v1",
) -> tuple[R3FeatureRow, ...]:
    """Build one deterministic row per evidenced member and month end.

    The function consumes only rows available by each decision cutoff and
    requires the exact trailing 253 exchange sessions. Appending future inputs
    cannot alter an existing prefix.
    """
    ordered_sessions = tuple(sessions)
    decisions = monthly_decision_dates(ordered_sessions)
    session_index = {session: index for index, session in enumerate(ordered_sessions)}
    by_security: dict[str, dict[date, R3Price]] = defaultdict(dict)
    for row in prices:
        if row.session in by_security[row.security_id]:
            raise ValueError("duplicate security/session price")
        by_security[row.security_id][row.session] = row
    evidence = sorted(memberships, key=lambda row: (row.security_id, row.member_from))
    output: list[R3FeatureRow] = []
    for decision in decisions:
        index = session_index[decision]
        if index < 252:
            continue
        needed = ordered_sessions[index - 252 : index + 1]
        benchmark_rows = by_security.get(benchmark_id, {})
        if any(day not in benchmark_rows for day in needed):
            continue
        market = tuple(benchmark_rows[day] for day in needed)
        cutoff = market[-1].available_at
        if any(row.available_at > cutoff for row in market):
            raise ValueError("benchmark contains future-available input")
        for member in evidence:
            if member.security_id == benchmark_id or not member.active(decision, cutoff):
                continue
            series_map = by_security.get(member.security_id, {})
            reasons: list[str] = []
            if any(day not in series_map for day in needed):
                reasons.append("incomplete_253_session_history")
                series: tuple[R3Price, ...] = ()
            else:
                series = tuple(series_map[day] for day in needed)
                if any(row.available_at > cutoff for row in series):
                    reasons.append("price_not_available_at_cutoff")
                if series[-1].close_usd < 10:
                    reasons.append("raw_price_below_10_usd")
                trailing_dv = statistics.median(
                    row.close_usd * row.volume for row in series[-20:]
                )
                if trailing_dv < 20_000_000:
                    reasons.append("liquidity_below_20m_usd")
            values: tuple[float, ...] = ()
            if not reasons:
                try:
                    values = _vector(series, 252, market)
                except (ValueError, ZeroDivisionError, statistics.StatisticsError):
                    reasons.append("invalid_mandatory_feature")
            last = series[-1] if series else None
            output.append(
                R3FeatureRow(
                    member.security_id,
                    decision,
                    cutoff,
                    max((row.available_at for row in series), default=member.available_at),
                    member.member_from,
                    member.member_until_exclusive,
                    "" if last is None else last.raw_series_id,
                    "" if last is None else last.adjusted_series_id,
                    values,
                    tuple(sorted(reasons)),
                    feature_version,
                )
            )
    return tuple(sorted(output, key=lambda row: (row.decision_date, row.security_id)))


def _holding_return_gbp(
    security_id: str,
    entry: R3Price,
    exit_row: R3Price | None,
    exit_at: datetime,
    actions: Sequence[R3Action],
    fx_rate: Callable[[datetime], float],
) -> tuple[float | None, datetime | None, str | None]:
    try:
        entry_fx = fx_rate(entry.open_at)
    except ValueError:
        return None, None, "entry_fx_unavailable_or_stale"
    basis_gbp = entry.open_usd * entry_fx
    shares = 1.0
    cash_gbp = 0.0
    availability = entry.available_at
    delisted = False
    for action in sorted(actions, key=lambda row: (row.effective_at, row.available_at)):
        if action.security_id != security_id:
            continue
        if not entry.open_at < action.effective_at:
            continue
        if action.effective_at >= exit_at:
            continue
        availability = max(availability, action.available_at)
        if action.action_type == "split":
            shares *= action.value_per_share
        else:
            if action.payment_at is None:
                return None, None, "cash_action_payment_date_unavailable"
            if action.withholding_fraction is None:
                return None, None, "cash_action_withholding_unavailable"
            amount = shares * action.value_per_share * (1 - action.withholding_fraction)
            try:
                payment_fx = fx_rate(action.payment_at)
            except ValueError:
                return None, None, "cash_action_fx_unavailable_or_stale"
            cash_gbp += amount * payment_fx
            availability = max(availability, action.payment_at)
            if action.action_type == "delisting":
                shares = 0.0
                delisted = True
    if exit_row is None:
        if not delisted:
            return None, None, "missing_exit_or_delisting_recovery"
        terminal_gbp = cash_gbp
    else:
        try:
            exit_fx = fx_rate(exit_row.open_at)
        except ValueError:
            return None, None, "exit_fx_unavailable_or_stale"
        terminal_gbp = cash_gbp + shares * exit_row.open_usd * exit_fx
        availability = max(availability, exit_row.available_at)
    return terminal_gbp / basis_gbp - 1, availability, None


def build_r3_labels(
    feature_rows: Iterable[R3FeatureRow],
    prices: Iterable[R3Price],
    actions: Iterable[R3Action],
    fx: FXHistory,
    sessions: Sequence[date],
    *,
    benchmark_id: str,
    label_version: str = "r3-gbp-open-to-open-excess-v1",
    max_fx_age_days: int = 6,
) -> tuple[R3Label, ...]:
    """Create labels only when both stock and benchmark outcomes are resolved."""
    decisions = monthly_decision_dates(sessions)
    decision_position = {day: index for index, day in enumerate(decisions)}
    session_position = {day: index for index, day in enumerate(sessions)}
    by_security: dict[str, dict[date, R3Price]] = defaultdict(dict)
    for row in prices:
        by_security[row.security_id][row.session] = row
    actions_by_security: dict[str, list[R3Action]] = defaultdict(list)
    for action in actions:
        actions_by_security[action.security_id].append(action)
    fx_cache: dict[datetime, float | ValueError] = {}

    def fx_rate(timestamp: datetime) -> float:
        cached = fx_cache.get(timestamp)
        if isinstance(cached, ValueError):
            raise cached
        if cached is not None:
            return cached
        try:
            value = fx.at(timestamp, max_age_days=max_fx_age_days).gbp_per_usd
        except ValueError as error:
            fx_cache[timestamp] = error
            raise
        fx_cache[timestamp] = value
        return value

    labels: list[R3Label] = []
    for feature_row in sorted(
        feature_rows, key=lambda item: (item.decision_date, item.security_id)
    ):
        if feature_row.exclusion_reasons:
            continue
        decision_index = decision_position.get(feature_row.decision_date)
        if decision_index is None or decision_index + 1 >= len(decisions):
            labels.append(
                R3Label(
                    feature_row.security_id,
                    feature_row.decision_date,
                    feature_row.feature_cutoff,
                    feature_row.feature_cutoff,
                    None,
                    None,
                    "label_horizon_not_complete",
                    label_version,
                )
            )
            continue
        entry_index = session_position[feature_row.decision_date] + 1
        next_decision = decisions[decision_index + 1]
        exit_index = session_position[next_decision] + 1
        if entry_index >= len(sessions) or exit_index >= len(sessions):
            labels.append(
                R3Label(
                    feature_row.security_id,
                    feature_row.decision_date,
                    feature_row.feature_cutoff,
                    feature_row.feature_cutoff,
                    None,
                    None,
                    "label_horizon_not_complete",
                    label_version,
                )
            )
            continue
        entry_day, exit_day = sessions[entry_index], sessions[exit_index]
        stock_entry = by_security[feature_row.security_id].get(entry_day)
        benchmark_entry = by_security[benchmark_id].get(entry_day)
        benchmark_exit = by_security[benchmark_id].get(exit_day)
        missing_reason: str | None = None
        if stock_entry is None:
            missing_reason = "stock_entry_price_unavailable"
        elif benchmark_entry is None:
            missing_reason = "benchmark_entry_price_unavailable"
        elif benchmark_exit is None:
            missing_reason = "benchmark_exit_price_unavailable"
        if missing_reason is not None:
            labels.append(
                R3Label(
                    feature_row.security_id,
                    feature_row.decision_date,
                    feature_row.feature_cutoff,
                    feature_row.feature_cutoff,
                    None,
                    None,
                    missing_reason,
                    label_version,
                )
            )
            continue
        assert stock_entry is not None
        assert benchmark_entry is not None
        assert benchmark_exit is not None
        stock_exit = by_security[feature_row.security_id].get(exit_day)
        stock_return, stock_available, reason = _holding_return_gbp(
            feature_row.security_id,
            stock_entry,
            stock_exit,
            benchmark_exit.open_at,
            actions_by_security.get(feature_row.security_id, ()),
            fx_rate,
        )
        benchmark_return, benchmark_available, benchmark_reason = _holding_return_gbp(
            benchmark_id,
            benchmark_entry,
            benchmark_exit,
            benchmark_exit.open_at,
            actions_by_security.get(benchmark_id, ()),
            fx_rate,
        )
        unresolved = reason or benchmark_reason
        available = (
            None
            if unresolved or stock_available is None or benchmark_available is None
            else max(stock_available, benchmark_available)
        )
        labels.append(
            R3Label(
                feature_row.security_id,
                feature_row.decision_date,
                stock_entry.open_at,
                benchmark_exit.open_at,
                available,
                None
                if unresolved or stock_return is None or benchmark_return is None
                else stock_return - benchmark_return,
                unresolved,
                label_version,
            )
        )
    return tuple(labels)
