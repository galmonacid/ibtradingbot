"""Small event-driven backtest with causal next-session fills."""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date as Date
from enum import StrEnum
from typing import Any, Literal, Protocol, cast

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


class RiskState(StrEnum):
    """Close-marked portfolio drawdown state."""

    NORMAL = "normal"
    SOFT = "soft"
    HARD = "hard"


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
    reason: Literal["rebalance", "risk_reduction", "drawdown_hard", "disappearance"]

    @property
    def total_cost(self) -> float:
        return self.commission + self.slippage_cost + self.fx_cost


@dataclass(frozen=True)
class EquityPoint:
    date: Date
    equity: float
    cash: float
    gross_exposure: float
    high_water_mark: float
    drawdown: float
    risk_state: RiskState


@dataclass(frozen=True)
class RiskEvent:
    """An observable risk-state transition decided after a session close."""

    date: Date
    previous_state: RiskState
    state: RiskState
    equity: float
    high_water_mark: float
    drawdown: float


@dataclass(frozen=True)
class AppliedTarget:
    """The risk-adjusted target accepted for one execution session."""

    date: Date
    signal_date: Date
    reason: Literal["rebalance", "risk_reduction", "drawdown_hard"]
    weights: dict[str, float]


@dataclass(frozen=True)
class ExecutionIssue:
    date: Date
    signal_date: Date | None
    symbol: str
    reason: Literal["missing_open"]


DecisionReason = Literal["rebalance", "risk_reduction", "drawdown_hard"]


@dataclass(frozen=True, order=True)
class TraceTargetWeight:
    """One immutable target-weight entry in an execution decision."""

    security_id: str
    weight: float


@dataclass(frozen=True, order=True)
class BacktestDecision:
    """One strategy or risk decision and its execution disposition."""

    decision_id: str
    signal_date: Date
    execution_date: Date | None
    reason: DecisionReason
    status: Literal["applied", "no_op", "superseded", "no_next_session"]
    target_weights: tuple[TraceTargetWeight, ...]


@dataclass(frozen=True, order=True)
class OrderIntent:
    """One order derived by the engine from an applied decision."""

    order_id: str
    decision_id: str
    execution_date: Date
    security_id: str
    side: Side
    requested_shares: float | None
    reference_price: float | None


@dataclass(frozen=True, order=True)
class ExecutionFill:
    """The full fill emitted for an executable order intent."""

    fill_id: str
    order_id: str
    shares: float
    execution_price: float
    gross_notional: float
    commission: float
    slippage_cost: float
    fx_cost: float


@dataclass(frozen=True, order=True)
class MissingOpenDisposition:
    """Explicit terminal disposition for an intent lacking an execution price."""

    order_id: str
    decision_id: str
    execution_date: Date
    security_id: str
    reason: Literal["missing_open"] = "missing_open"


@dataclass(frozen=True, order=True)
class CorporateActionSettlement:
    """A non-order cash settlement caused by a security disappearance."""

    settlement_id: str
    session: Date
    security_id: str
    shares: float
    cash_per_share: float
    proceeds: float


@dataclass(frozen=True)
class BacktestExecutionTrace:
    """Immutable exhaustive execution events emitted by one backtest."""

    decisions: tuple[BacktestDecision, ...]
    order_intents: tuple[OrderIntent, ...]
    fills: tuple[ExecutionFill, ...]
    missing_open_dispositions: tuple[MissingOpenDisposition, ...]
    corporate_action_settlements: tuple[CorporateActionSettlement, ...]
    sha256: str

    def __post_init__(self) -> None:
        decision_ids = [row.decision_id for row in self.decisions]
        order_ids = [row.order_id for row in self.order_intents]
        fill_order_ids = [row.order_id for row in self.fills]
        missing_order_ids = [row.order_id for row in self.missing_open_dispositions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("execution trace decision IDs must be unique")
        if len(order_ids) != len(set(order_ids)):
            raise ValueError("execution trace order IDs must be unique")
        if len(fill_order_ids) != len(set(fill_order_ids)):
            raise ValueError("execution trace orders may have at most one fill")
        if len(missing_order_ids) != len(set(missing_order_ids)):
            raise ValueError("execution trace orders may have at most one missing-open disposition")
        if set(fill_order_ids) & set(missing_order_ids):
            raise ValueError("execution trace order has multiple terminal outcomes")
        if set(order_ids) != set(fill_order_ids) | set(missing_order_ids):
            raise ValueError("every execution trace order requires exactly one terminal outcome")
        known_decisions = set(decision_ids)
        if any(row.decision_id not in known_decisions for row in self.order_intents):
            raise ValueError("execution trace order references an unknown decision")
        order_ids_by_decision: dict[str, set[str]] = {
            decision_id: set() for decision_id in decision_ids
        }
        for row in self.order_intents:
            order_ids_by_decision[row.decision_id].add(row.order_id)
        for decision in self.decisions:
            has_orders = bool(order_ids_by_decision[decision.decision_id])
            if decision.status == "no_op" and has_orders:
                raise ValueError("execution trace no-op disposition conflicts with its orders")
            if decision.status == "applied" and not has_orders:
                raise ValueError("execution trace applied decision must own an order")
            if decision.status in ("superseded", "no_next_session") and has_orders:
                raise ValueError("unexecuted decision cannot own an order")
        intents_by_id = {row.order_id: row for row in self.order_intents}
        for fill in self.fills:
            intent = intents_by_id[fill.order_id]
            if intent.requested_shares is None or intent.reference_price is None:
                raise ValueError("filled execution trace order lacks executable terms")
            if fill.shares != intent.requested_shares:
                raise ValueError("execution trace fill does not match requested shares")
        for disposition in self.missing_open_dispositions:
            intent = intents_by_id[disposition.order_id]
            if intent.requested_shares is not None or intent.reference_price is not None:
                raise ValueError("missing-open execution trace order contains executable terms")
        settlement_ids = [row.settlement_id for row in self.corporate_action_settlements]
        if len(settlement_ids) != len(set(settlement_ids)):
            raise ValueError("execution trace settlement IDs must be unique")
        expected = _digest(
            (
                self.decisions,
                self.order_intents,
                self.fills,
                self.missing_open_dispositions,
                self.corporate_action_settlements,
            )
        )
        if self.sha256 != expected:
            raise ValueError("execution trace digest does not match its immutable events")


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[Trade, ...]
    execution_issues: tuple[ExecutionIssue, ...]
    risk_events: tuple[RiskEvent, ...]
    applied_targets: tuple[AppliedTarget, ...]
    final_cash: float
    final_positions: dict[str, float]
    final_risk_state: RiskState
    execution_trace: BacktestExecutionTrace


def _canonical_value(value: object) -> object:
    if isinstance(value, Date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(cast(Any, value)))
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in sorted(value.items())}
    return value


def _digest(value: object) -> str:
    payload = _canonical_value(value)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _target_weights(targets: Mapping[str, float]) -> tuple[TraceTargetWeight, ...]:
    return tuple(TraceTargetWeight(symbol, targets[symbol]) for symbol in sorted(targets))


def _decision_id(
    signal_date: Date,
    execution_date: Date | None,
    reason: DecisionReason,
    targets: Mapping[str, float],
) -> str:
    return _digest(
        {
            "signal_date": signal_date,
            "execution_date": execution_date,
            "reason": reason,
            "target_weights": _target_weights(targets),
        }
    )


def _apply_soft_drawdown_limits(
    targets: Mapping[str, float],
    *,
    exposure_ceiling: float,
    max_position_weight: float,
) -> dict[str, float]:
    """Apply soft-state caps without ever increasing a requested weight."""
    capped = {
        symbol: min(weight, max_position_weight / 2.0)
        for symbol, weight in targets.items()
        if weight > 0.0
    }
    total = math.fsum(capped.values())
    if total <= exposure_ceiling or total <= 0.0:
        return capped
    scale = exposure_ceiling / total
    return {symbol: weight * scale for symbol, weight in capped.items()}


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
    soft_drawdown_threshold: float | None = None,
    hard_drawdown_threshold: float | None = None,
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
    if (soft_drawdown_threshold is None) != (hard_drawdown_threshold is None):
        raise ValueError("soft and hard drawdown thresholds must be configured together")
    if soft_drawdown_threshold is not None and hard_drawdown_threshold is not None:
        if (
            not math.isfinite(soft_drawdown_threshold)
            or not math.isfinite(hard_drawdown_threshold)
            or not 0.0 < soft_drawdown_threshold < hard_drawdown_threshold <= 1.0
        ):
            raise ValueError("drawdown thresholds must satisfy 0 < soft < hard <= 1")
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

    decisions: list[BacktestDecision] = []
    order_intents: list[OrderIntent] = []
    fills: list[ExecutionFill] = []
    missing_open_dispositions: list[MissingOpenDisposition] = []
    corporate_action_settlements: list[CorporateActionSettlement] = []
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
            execution_date = sessions[index]
            displaced = scheduled.get(execution_date)
            if displaced is not None:
                displaced_signal, displaced_targets = displaced
                decisions.append(
                    BacktestDecision(
                        _decision_id(
                            displaced_signal, execution_date, "rebalance", displaced_targets
                        ),
                        displaced_signal,
                        execution_date,
                        "rebalance",
                        "superseded",
                        _target_weights(displaced_targets),
                    )
                )
            scheduled[execution_date] = (signal_date, targets)
        else:
            decisions.append(
                BacktestDecision(
                    _decision_id(signal_date, None, "rebalance", targets),
                    signal_date,
                    None,
                    "rebalance",
                    "no_next_session",
                    _target_weights(targets),
                )
            )

    cash = initial_cash
    positions: dict[str, float] = {}
    last_prices: dict[str, float] = {}
    trades: list[Trade] = []
    execution_issues: list[ExecutionIssue] = []
    risk_events: list[RiskEvent] = []
    applied_targets: list[AppliedTarget] = []
    curve: list[EquityPoint] = []
    risk_state = RiskState.NORMAL
    high_water_mark = initial_cash
    last_target_gross = 0.0
    hard_liquidation_pending = False
    hard_signal_date: Date | None = None
    risk_reduction_pending: tuple[Date, Mapping[str, float], frozenset[str]] | None = None

    def record_trade(
        *,
        decision_id: str,
        trade_date: Date,
        signal_date: Date | None,
        symbol: str,
        side: Side,
        shares: float,
        reference_price: float,
        reason: Literal["rebalance", "risk_reduction", "drawdown_hard", "disappearance"],
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
        order_id = _digest(
            {
                "decision_id": decision_id,
                "execution_date": trade_date,
                "security_id": symbol,
                "side": side,
            }
        )
        order_intents.append(
            OrderIntent(
                order_id,
                decision_id,
                trade_date,
                symbol,
                side,
                shares,
                reference_price,
            )
        )
        fill_values = {
            "order_id": order_id,
            "shares": shares,
            "execution_price": execution_price,
            "gross_notional": gross_notional,
            "commission": cost_model.commission_per_order,
            "slippage_cost": slippage_cost,
            "fx_cost": fx_cost,
        }
        fills.append(
            ExecutionFill(
                _digest(fill_values),
                order_id,
                shares,
                execution_price,
                gross_notional,
                cost_model.commission_per_order,
                slippage_cost,
                fx_cost,
            )
        )
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
            settlement_values = {
                "session": session,
                "security_id": symbol,
                "shares": shares,
                "cash_per_share": delisting.cash_per_share,
                "proceeds": proceeds,
            }
            corporate_action_settlements.append(
                CorporateActionSettlement(
                    _digest(settlement_values),
                    session,
                    symbol,
                    shares,
                    delisting.cash_per_share,
                    proceeds,
                )
            )
            cash += proceeds

        scheduled_rebalance = scheduled.get(session)
        reduction_symbols: frozenset[str] = frozenset()
        if hard_liquidation_pending:
            if hard_signal_date is None:  # pragma: no cover - local state invariant
                raise RuntimeError("hard liquidation is missing its signal date")
            signal_date = hard_signal_date
            target_weights: Mapping[str, float] = {}
            trade_reason: Literal["rebalance", "risk_reduction", "drawdown_hard"] = "drawdown_hard"
            hard_liquidation_pending = False
            if scheduled_rebalance is not None:
                displaced_signal, displaced_targets = scheduled_rebalance
                decisions.append(
                    BacktestDecision(
                        _decision_id(displaced_signal, session, "rebalance", displaced_targets),
                        displaced_signal,
                        session,
                        "rebalance",
                        "superseded",
                        _target_weights(displaced_targets),
                    )
                )
        elif scheduled_rebalance is not None:
            signal_date, requested_targets = scheduled_rebalance
            trade_reason = "rebalance"
            # A scheduled strategy target supersedes a pending concentration
            # trim, but still receives the active drawdown overlay. This keeps
            # scheduled exits (especially risk-off liquidation) from being lost.
            if risk_reduction_pending is not None:
                reduction_signal, reduction_targets, _symbols = risk_reduction_pending
                decisions.append(
                    BacktestDecision(
                        _decision_id(
                            reduction_signal, session, "risk_reduction", reduction_targets
                        ),
                        reduction_signal,
                        session,
                        "risk_reduction",
                        "superseded",
                        _target_weights(reduction_targets),
                    )
                )
            risk_reduction_pending = None
            if risk_state is RiskState.HARD:
                target_weights = {}
            elif risk_state is RiskState.SOFT:
                target_weights = _apply_soft_drawdown_limits(
                    requested_targets,
                    exposure_ceiling=last_target_gross,
                    max_position_weight=max_position_weight,
                )
            else:
                target_weights = requested_targets
            last_target_gross = math.fsum(target_weights.values())
        elif risk_reduction_pending is not None:
            signal_date, target_weights, reduction_symbols = risk_reduction_pending
            trade_reason = "risk_reduction"
            risk_reduction_pending = None
            last_target_gross = math.fsum(target_weights.values())
        else:
            signal_date = session
            target_weights = {}
            trade_reason = "rebalance"

        if hard_liquidation_pending is False and (
            scheduled_rebalance is not None or trade_reason in ("risk_reduction", "drawdown_hard")
        ):
            decision_id = _decision_id(signal_date, session, trade_reason, target_weights)
            intent_count_before = len(order_intents)
            applied_targets.append(
                AppliedTarget(session, signal_date, trade_reason, dict(target_weights))
            )
            open_prices = {
                symbol: bar.open * bar.adjusted_close / bar.close for symbol, bar in day.items()
            }
            for symbol, weight in target_weights.items():
                if weight > 0.0 and symbol not in open_prices:
                    execution_issues.append(
                        ExecutionIssue(session, signal_date, symbol, "missing_open")
                    )
                    order_id = _digest(
                        {
                            "decision_id": decision_id,
                            "execution_date": session,
                            "security_id": symbol,
                            "side": "buy",
                        }
                    )
                    order_intents.append(
                        OrderIntent(order_id, decision_id, session, symbol, "buy", None, None)
                    )
                    missing_open_dispositions.append(
                        MissingOpenDisposition(order_id, decision_id, session, symbol)
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
                    symbol: (
                        min(
                            positions.get(symbol, 0.0),
                            posttrade_equity * weight / open_prices[symbol],
                        )
                        if trade_reason == "risk_reduction" and symbol in reduction_symbols
                        else positions.get(symbol, 0.0)
                        if trade_reason == "risk_reduction"
                        else posttrade_equity * weight / open_prices[symbol]
                    )
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
                symbol: (
                    min(
                        positions.get(symbol, 0.0),
                        posttrade_equity * weight / open_prices[symbol],
                    )
                    if trade_reason == "risk_reduction" and symbol in reduction_symbols
                    else positions.get(symbol, 0.0)
                    if trade_reason == "risk_reduction"
                    else posttrade_equity * weight / open_prices[symbol]
                )
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
                execution_price = cost_model.execution_price(open_prices[symbol], estimated_side)
                gross_notional = abs(delta) * execution_price
                fee = cost_model.commission_per_order + cost_model.fx_cost(gross_notional)
                projected_cash += (
                    -(gross_notional + fee) if estimated_side == "buy" else gross_notional - fee
                )
            projected_holdings = sum(
                shares * open_prices[symbol] for symbol, shares in desired_shares.items()
            ) + sum(
                shares * last_prices[symbol]
                for symbol, shares in positions.items()
                if symbol not in open_prices
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
            projected_max_weight = max(
                projected_max_weight,
                max(
                    (
                        shares * last_prices[symbol] / projected_equity
                        for symbol, shares in positions.items()
                        if symbol not in open_prices
                    ),
                    default=0.0,
                ),
            )
            numerical_tolerance = max(1e-10, projected_equity * 1e-12)
            if (
                projected_equity <= 0.0
                or projected_cash
                < projected_equity * cash_buffer - numerical_tolerance
                or projected_gross > 1.0 - cash_buffer + 1e-12
                or projected_max_weight > max_position_weight + 1e-12
            ):
                raise BacktestDataError(
                    f"target on {signal_date} is infeasible after configured costs "
                    f"(cash={projected_cash:.12f}, required_cash="
                    f"{projected_equity * cash_buffer:.12f}, gross={projected_gross:.12f}, "
                    f"max_weight={projected_max_weight:.12f})"
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
                        decision_id=decision_id,
                        trade_date=session,
                        signal_date=signal_date,
                        symbol=symbol,
                        side="sell",
                        shares=shares,
                        reference_price=open_prices[symbol],
                        reason=trade_reason,
                    )
                    cash += cash_change
                    if desired <= 1e-12:
                        positions.pop(symbol)
                    else:
                        positions[symbol] = desired

            for symbol in sorted(target_weights):
                if symbol not in open_prices:
                    continue
                current = positions.get(symbol, 0.0)
                requested = desired_shares.get(symbol, 0.0) - current
                if requested <= 1e-12:
                    continue
                cash_change, _trade = record_trade(
                    decision_id=decision_id,
                    trade_date=session,
                    signal_date=signal_date,
                    symbol=symbol,
                    side="buy",
                    shares=requested,
                    reference_price=open_prices[symbol],
                    reason=trade_reason,
                )
                cash += cash_change
                new_position = current + requested
                positions[symbol] = new_position
                if cash < 0.0 and cash > -1e-8:
                    cash = 0.0
                if cash < 0.0:
                    raise RuntimeError("cost reservation failed: negative cash")
            decisions.append(
                BacktestDecision(
                    decision_id,
                    signal_date,
                    session,
                    trade_reason,
                    "applied" if len(order_intents) > intent_count_before else "no_op",
                    _target_weights(target_weights),
                )
            )

        holdings_value = sum(
            shares * day[symbol].adjusted_close if symbol in day else shares * last_prices[symbol]
            for symbol, shares in positions.items()
        )
        equity = cash + holdings_value
        exposure = holdings_value / equity if equity > 0.0 else 0.0
        high_water_mark = max(high_water_mark, equity)
        drawdown = equity / high_water_mark - 1.0
        previous_risk_state = risk_state
        if soft_drawdown_threshold is not None and hard_drawdown_threshold is not None:
            if risk_state is not RiskState.HARD and drawdown <= -hard_drawdown_threshold + 1e-12:
                risk_state = RiskState.HARD
                hard_signal_date = session
                hard_liquidation_pending = bool(positions)
            elif risk_state is not RiskState.HARD:
                risk_state = (
                    RiskState.SOFT
                    if drawdown <= -soft_drawdown_threshold + 1e-12
                    else RiskState.NORMAL
                )
        if risk_state is not previous_risk_state:
            risk_events.append(
                RiskEvent(
                    session,
                    previous_risk_state,
                    risk_state,
                    equity,
                    high_water_mark,
                    drawdown,
                )
            )
        if risk_state is not RiskState.HARD and positions:
            marked_weights = {
                symbol: shares * day[symbol].adjusted_close / equity
                for symbol, shares in positions.items()
            }
            active_cap = (
                max_position_weight / 2.0 if risk_state is RiskState.SOFT else max_position_weight
            )
            breached_symbols = frozenset(
                symbol for symbol, weight in marked_weights.items() if weight > active_cap + 1e-12
            )
            if breached_symbols:
                reduction_weights = (
                    _apply_soft_drawdown_limits(
                        marked_weights,
                        exposure_ceiling=last_target_gross,
                        max_position_weight=max_position_weight,
                    )
                    if risk_state is RiskState.SOFT
                    else {
                        symbol: min(weight, active_cap) for symbol, weight in marked_weights.items()
                    }
                )
                reduction_symbols = frozenset(
                    symbol
                    for symbol, weight in marked_weights.items()
                    if reduction_weights[symbol] < weight - 1e-12
                )
                risk_reduction_pending = (
                    session,
                    reduction_weights,
                    reduction_symbols,
                )
        curve.append(
            EquityPoint(
                session,
                equity,
                cash,
                exposure,
                high_water_mark,
                drawdown,
                risk_state,
            )
        )

    if hard_liquidation_pending and hard_signal_date is not None:
        decisions.append(
            BacktestDecision(
                _decision_id(hard_signal_date, None, "drawdown_hard", {}),
                hard_signal_date,
                None,
                "drawdown_hard",
                "no_next_session",
                (),
            )
        )
    elif risk_reduction_pending is not None:
        reduction_signal, reduction_targets, _symbols = risk_reduction_pending
        decisions.append(
            BacktestDecision(
                _decision_id(reduction_signal, None, "risk_reduction", reduction_targets),
                reduction_signal,
                None,
                "risk_reduction",
                "no_next_session",
                _target_weights(reduction_targets),
            )
        )

    ordered_decisions = tuple(
        sorted(
            decisions,
            key=lambda row: (row.signal_date, row.execution_date or Date.max, row.decision_id),
        )
    )
    ordered_intents = tuple(order_intents)
    ordered_fills = tuple(fills)
    ordered_missing_opens = tuple(missing_open_dispositions)
    ordered_settlements = tuple(corporate_action_settlements)
    trace_values = (
        ordered_decisions,
        ordered_intents,
        ordered_fills,
        ordered_missing_opens,
        ordered_settlements,
    )
    execution_trace = BacktestExecutionTrace(
        ordered_decisions,
        ordered_intents,
        ordered_fills,
        ordered_missing_opens,
        ordered_settlements,
        _digest(trace_values),
    )
    return BacktestResult(
        tuple(curve),
        tuple(trades),
        tuple(execution_issues),
        tuple(risk_events),
        tuple(applied_targets),
        cash,
        dict(positions),
        risk_state,
        execution_trace,
    )
