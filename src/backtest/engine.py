"""Small event-driven backtest with causal next-session fills."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date as Date
from typing import Literal, Protocol

from src.backtest.costs import CostModel, Side
from src.data.corporate_actions import DelistingEvent


class PriceBarLike(Protocol):
    """Structural input accepted from the ingestion layer."""

    @property
    def date(self) -> Date: ...

    @property
    def symbol(self) -> str: ...

    @property
    def open(self) -> float: ...

    @property
    def close(self) -> float: ...

    @property
    def adjusted_close(self) -> float: ...

    @property
    def adjusted_open(self) -> float: ...


@dataclass(frozen=True)
class PriceBar:
    date: Date
    symbol: str
    open: float
    close: float
    adjusted_close: float

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        prices = (self.open, self.close, self.adjusted_close)
        if not all(math.isfinite(value) and value > 0.0 for value in prices):
            raise ValueError("bar prices must be finite and positive")

    @property
    def adjusted_open(self) -> float:
        """Scale the tradable open into the adjusted research price space."""
        return self.open * self.adjusted_close / self.close


class BacktestDataError(ValueError):
    """Raised when portfolio valuation would require unavailable market data."""


@dataclass(frozen=True)
class Trade:
    date: Date
    signal_date: Date | None
    symbol: str
    side: Side
    shares: float
    reference_price: float
    execution_price: float
    gross_notional: float
    commission: float
    slippage_cost: float
    fx_cost: float
    reason: Literal["rebalance", "disappearance"]

    @property
    def total_cost(self) -> float:
        return self.commission + self.slippage_cost + self.fx_cost


@dataclass(frozen=True)
class EquityPoint:
    date: Date
    equity: float
    cash: float
    gross_exposure: float


@dataclass(frozen=True)
class ExecutionIssue:
    date: Date
    signal_date: Date | None
    symbol: str
    reason: Literal["missing_open"]


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[Trade, ...]
    execution_issues: tuple[ExecutionIssue, ...]
    final_cash: float
    final_positions: dict[str, float]


def _validate_targets(
    targets: Mapping[str, float],
    *,
    cash_buffer: float,
    max_position_weight: float,
    max_positions: int,
) -> None:
    total = 0.0
    positive_positions = 0
    for symbol, weight in targets.items():
        if not symbol.strip():
            raise ValueError("target symbol must not be blank")
        if isinstance(weight, bool) or not math.isfinite(weight) or weight < 0.0:
            raise ValueError("target weights must be finite and non-negative")
        if weight > max_position_weight + 1e-12:
            raise ValueError("target weight exceeds maximum position weight")
        positive_positions += weight > 0.0
        total += weight
    if positive_positions > max_positions:
        raise ValueError("target has too many positions")
    if total > 1.0 - cash_buffer + 1e-12:
        raise ValueError("target gross exposure violates the cash buffer")


def run_backtest(
    bars: Sequence[PriceBarLike],
    targets_by_signal_date: Mapping[Date, Mapping[str, float]],
    *,
    initial_cash: float = 100_000.0,
    costs: CostModel | None = None,
    delistings: Sequence[DelistingEvent] = (),
    cash_buffer: float = 0.02,
    max_position_weight: float = 0.30,
    max_positions: int = 5,
) -> BacktestResult:
    """Execute dated targets at the strictly following available session open.

    Prices are kept in adjusted-price space, allowing share accounting to stay
    continuous across splits represented by the close/adjusted-close factor.
    """
    if not math.isfinite(initial_cash) or initial_cash <= 0.0:
        raise ValueError("initial_cash must be finite and positive")
    if not math.isfinite(cash_buffer) or not 0.02 <= cash_buffer < 1.0:
        raise ValueError("cash_buffer must be finite and in [0.02, 1)")
    if not math.isfinite(max_position_weight) or not 0.0 <= max_position_weight <= 0.30:
        raise ValueError("max_position_weight must be finite and in [0, 0.30]")
    if (
        not isinstance(max_positions, int)
        or isinstance(max_positions, bool)
        or not 0 <= max_positions <= 5
    ):
        raise ValueError("max_positions must be an integer between 0 and 5")
    cost_model = costs or CostModel()
    delisting_by_key: dict[tuple[Date, str], DelistingEvent] = {}
    for event in delistings:
        key = (event.date, event.symbol)
        if key in delisting_by_key:
            raise ValueError(f"duplicate delisting event for {event.symbol} on {event.date}")
        delisting_by_key[key] = event
    by_date: dict[Date, dict[str, PriceBarLike]] = {}
    for bar in bars:
        day = by_date.setdefault(bar.date, {})
        if bar.symbol in day:
            raise ValueError(f"duplicate bar for {bar.symbol} on {bar.date}")
        day[bar.symbol] = bar
    sessions = sorted(by_date)
    if not sessions:
        raise ValueError("at least one price bar is required")
    for event in delistings:
        if event.date not in by_date:
            raise ValueError("delisting event date must be a market session")
        if event.symbol in by_date[event.date]:
            raise ValueError("delisting event conflicts with a price bar")

    scheduled: dict[Date, tuple[Date, Mapping[str, float]]] = {}
    for signal_date, targets in sorted(targets_by_signal_date.items()):
        _validate_targets(
            targets,
            cash_buffer=cash_buffer,
            max_position_weight=max_position_weight,
            max_positions=max_positions,
        )
        index = bisect_right(sessions, signal_date)
        if index < len(sessions):
            # The latest signal wins if multiple signals target one sparse-data session.
            scheduled[sessions[index]] = (signal_date, targets)

    cash = initial_cash
    positions: dict[str, float] = {}
    last_prices: dict[str, float] = {}
    trades: list[Trade] = []
    execution_issues: list[ExecutionIssue] = []
    curve: list[EquityPoint] = []

    def record_trade(
        *,
        trade_date: Date,
        signal_date: Date | None,
        symbol: str,
        side: Side,
        shares: float,
        reference_price: float,
        reason: Literal["rebalance", "disappearance"],
    ) -> tuple[float, Trade]:
        execution_price = cost_model.execution_price(reference_price, side)
        gross_notional = shares * execution_price
        slippage_cost = shares * abs(execution_price - reference_price)
        fx_cost = cost_model.fx_cost(gross_notional)
        cash_change = (
            -(gross_notional + cost_model.commission_per_order + fx_cost)
            if side == "buy"
            else gross_notional - cost_model.commission_per_order - fx_cost
        )
        trade = Trade(
            date=trade_date,
            signal_date=signal_date,
            symbol=symbol,
            side=side,
            shares=shares,
            reference_price=reference_price,
            execution_price=execution_price,
            gross_notional=gross_notional,
            commission=cost_model.commission_per_order,
            slippage_cost=slippage_cost,
            fx_cost=fx_cost,
            reason=reason,
        )
        trades.append(trade)
        return cash_change, trade

    for session in sessions:
        day = by_date[session]
        for symbol, bar in day.items():
            last_prices[symbol] = bar.adjusted_close

        # This reacts only when the missing session is observed. It does not
        # inspect a symbol's future rows to decide when to exit.
        for symbol in sorted(set(positions) - set(day)):
            delisting = delisting_by_key.get((session, symbol))
            if delisting is None:
                raise BacktestDataError(
                    f"held symbol {symbol} has no bar or delisting event on {session}"
                )
            shares = positions.pop(symbol)
            proceeds = shares * delisting.cash_per_share
            trades.append(
                Trade(
                    date=session,
                    signal_date=None,
                    symbol=symbol,
                    side="sell",
                    shares=shares,
                    reference_price=delisting.cash_per_share,
                    execution_price=delisting.cash_per_share,
                    gross_notional=proceeds,
                    commission=0.0,
                    slippage_cost=0.0,
                    fx_cost=0.0,
                    reason="disappearance",
                )
            )
            cash += proceeds

        if session in scheduled:
            signal_date, target_weights = scheduled[session]
            open_prices = {
                symbol: bar.open * bar.adjusted_close / bar.close
                for symbol, bar in day.items()
            }
            for symbol, weight in target_weights.items():
                if weight > 0.0 and symbol not in open_prices:
                    execution_issues.append(
                        ExecutionIssue(session, signal_date, symbol, "missing_open")
                    )
            pretrade_equity = cash + sum(
                shares * open_prices.get(symbol, last_prices[symbol])
                for symbol, shares in positions.items()
            )
            # Costs reduce post-fill equity, so solve target notionals against
            # that post-cost equity rather than the pre-cost account value.
            posttrade_equity = pretrade_equity
            desired_shares: dict[str, float] = {}
            converged = False
            for _iteration in range(50):
                desired_shares = {
                    symbol: posttrade_equity * weight / open_prices[symbol]
                    for symbol, weight in target_weights.items()
                    if weight > 0.0 and symbol in open_prices
                }
                estimated_cost = 0.0
                for symbol in set(positions) | set(desired_shares):
                    delta = desired_shares.get(symbol, 0.0) - positions.get(symbol, 0.0)
                    if abs(delta) <= 1e-12 or symbol not in open_prices:
                        continue
                    side: Side = "buy" if delta > 0.0 else "sell"
                    reference = open_prices[symbol]
                    execution = cost_model.execution_price(reference, side)
                    notional = abs(delta) * execution
                    estimated_cost += (
                        abs(delta) * abs(execution - reference)
                        + cost_model.commission_per_order
                        + cost_model.fx_cost(notional)
                    )
                updated_equity = max(0.0, pretrade_equity - estimated_cost)
                if math.isclose(updated_equity, posttrade_equity, rel_tol=1e-14, abs_tol=1e-10):
                    posttrade_equity = updated_equity
                    converged = True
                    break
                posttrade_equity = updated_equity
            if not converged:
                raise BacktestDataError(
                    f"target on {signal_date} cannot be executed safely with configured costs"
                )
            desired_shares = {
                symbol: posttrade_equity * weight / open_prices[symbol]
                for symbol, weight in target_weights.items()
                if weight > 0.0 and symbol in open_prices
            }


            # Preflight the complete rebalance before mutating portfolio state.
            # Fixed commissions make costs discontinuous, so a target can be
            # mathematically infeasible for a very small account. Never fall
            # back to a partial fill that could breach concentration limits.
            projected_cash = cash
            for symbol in set(positions) | set(desired_shares):
                current = positions.get(symbol, 0.0)
                desired = desired_shares.get(symbol, 0.0)
                delta = desired - current
                if abs(delta) <= 1e-12:
                    continue
                estimated_side: Side = "buy" if delta > 0.0 else "sell"
                execution_price = cost_model.execution_price(
                    open_prices[symbol], estimated_side
                )
                gross_notional = abs(delta) * execution_price
                fee = cost_model.commission_per_order + cost_model.fx_cost(gross_notional)
                projected_cash += (
                    -(gross_notional + fee)
                    if estimated_side == "buy"
                    else gross_notional - fee
                )
            projected_holdings = sum(
                shares * open_prices[symbol] for symbol, shares in desired_shares.items()
            )
            projected_equity = projected_cash + projected_holdings
            projected_gross = (
                projected_holdings / projected_equity if projected_equity > 0.0 else math.inf
            )
            projected_max_weight = max(
                (
                    shares * open_prices[symbol] / projected_equity
                    for symbol, shares in desired_shares.items()
                ),
                default=0.0,
            )
            if (
                projected_equity <= 0.0
                or projected_cash < projected_equity * cash_buffer - 1e-10
                or projected_gross > 1.0 - cash_buffer + 1e-12
                or projected_max_weight > max_position_weight + 1e-12
            ):
                raise BacktestDataError(
                    f"target on {signal_date} is infeasible after configured costs"
                )

            # Reductions and removals generate cash before any increases.
            for symbol in sorted(tuple(positions)):
                if symbol not in open_prices:
                    continue
                current = positions[symbol]
                desired = desired_shares.get(symbol, 0.0)
                shares = current - desired
                if shares > 1e-12:
                    cash_change, _trade = record_trade(
                        trade_date=session,
                        signal_date=signal_date,
                        symbol=symbol,
                        side="sell",
                        shares=shares,
                        reference_price=open_prices[symbol],
                        reason="rebalance",
                    )
                    cash += cash_change
                    if desired <= 1e-12:
                        positions.pop(symbol)
                    else:
                        positions[symbol] = desired

            for symbol in target_weights:
                if symbol not in open_prices:
                    continue
                current = positions.get(symbol, 0.0)
                requested = desired_shares.get(symbol, 0.0) - current
                if requested <= 1e-12:
                    continue
                cash_change, _trade = record_trade(
                    trade_date=session,
                    signal_date=signal_date,
                    symbol=symbol,
                    side="buy",
                    shares=requested,
                    reference_price=open_prices[symbol],
                    reason="rebalance",
                )
                cash += cash_change
                new_position = current + requested
                positions[symbol] = new_position
                if cash < 0.0 and cash > -1e-8:
                    cash = 0.0
                if cash < 0.0:
                    raise RuntimeError("cost reservation failed: negative cash")

        holdings_value = sum(
            shares * day[symbol].adjusted_close
            if symbol in day
            else shares * last_prices[symbol]
            for symbol, shares in positions.items()
        )
        equity = cash + holdings_value
        exposure = holdings_value / equity if equity > 0.0 else 0.0
        curve.append(EquityPoint(session, equity, cash, exposure))

    return BacktestResult(
        tuple(curve),
        tuple(trades),
        tuple(execution_issues),
        cash,
        dict(positions),
    )
