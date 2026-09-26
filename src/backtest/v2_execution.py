"""Atomic raw-share V2 research execution with explicit GBP/USD cash accounting.

This is a deterministic simulation, not a broker adapter or verified tariff.
Signals execute strictly later than their decision date. Holdings use stable IDs.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Account:
    cash_gbp: float
    cash_usd: float
    holdings: dict[str, float] = field(default_factory=dict)
    receivables_usd: float = 0.0


@dataclass(frozen=True)
class FeeModel:
    commission_per_share: float = 0.005
    commission_min_usd: float = 1.0
    slippage_bps: float = 5.0
    fx_friction_bps: float = 5.0
    conversion_bps: float = 3.0


_DEFAULT_COSTS = FeeModel()


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str
    shares: float
    reference_price: float
    execution_price: float
    commission_usd: float
    slippage_usd: float
    fx_friction_usd: float
    commission_gbp: float
    slippage_gbp: float
    fx_friction_gbp: float
    mandatory: bool
    gbp_per_usd: float

    @property
    def total_cost_usd(self) -> float:
        return self.commission_usd + self.slippage_usd + self.fx_friction_usd

    @property
    def total_cost_gbp(self) -> float:
        return self.commission_gbp + self.slippage_gbp + self.fx_friction_gbp


@dataclass(frozen=True)
class SkippedOrder:
    symbol: str
    reason: str


@dataclass(frozen=True)
class Conversion:
    direction: str
    amount_usd: float
    fee_usd: float
    fee_gbp: float


@dataclass(frozen=True)
class ExecutionResult:
    account: Account
    fills: tuple[Fill, ...]
    skips: tuple[SkippedOrder, ...]
    conversions: tuple[Conversion, ...]
    accepted_weights: dict[str, float]
    succeeded: bool
    failure: str | None = None


class _Infeasible(ValueError):
    pass


def _finite_nonnegative(value: float) -> bool:
    return not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _equity(account: Account, prices: Mapping[str, float], fx: float) -> float:
    return (
        account.cash_gbp / fx
        + account.cash_usd
        + account.receivables_usd
        + math.fsum(
            shares * prices[symbol] for symbol, shares in account.holdings.items() if shares > 0
        )
    )


def execute_plan(
    account: Account,
    target_weights: Mapping[str, float],
    raw_open: Mapping[str, float],
    gbp_per_usd: float,
    *,
    min_order_gbp: float = 150,
    fractional: bool = False,
    mandatory_ids: Iterable[str] = (),
    name_cap: float = 0.3,
    cash_buffer: float = 0.02,
    gross_ceiling: float = 0.98,
    costs: FeeModel = _DEFAULT_COSTS,
    reductions_only: bool = False,
    signal_date: date,
    execution_date: date,
) -> ExecutionResult:
    """Simulate sells before buys, returning no mutations when a plan is infeasible.

    Candidate share targets are recomputed against the estimated post-cost NAV.
    Whole-share targets always round down. Tiny required sells bypass the order
    minimum; unsupported fractional residual sells fail atomically. No skipped buy
    is redistributed. Actual accepted weights, not requested targets, are returned.
    GBP sale sweeps and GBP purchase conversions are charged independently of the
    retained conservative per-side FX friction buffer. Monthly fees are external.
    """
    original = Account(
        account.cash_gbp, account.cash_usd, dict(account.holdings), account.receivables_usd
    )
    mandatory = set(mandatory_ids)

    def reject(reason: str) -> ExecutionResult:
        return ExecutionResult(original, (), (), (), {}, False, reason)

    if execution_date <= signal_date:
        return reject("execution must be strictly after the signal date")
    if not _finite_nonnegative(gbp_per_usd) or gbp_per_usd == 0:
        return reject("invalid GBP per USD conversion rate")
    if (
        not _finite_nonnegative(account.cash_gbp)
        or not _finite_nonnegative(account.cash_usd)
        or not _finite_nonnegative(account.receivables_usd)
    ):
        return reject("invalid cash balances")
    numeric = (
        min_order_gbp,
        name_cap,
        cash_buffer,
        gross_ceiling,
        costs.commission_per_share,
        costs.commission_min_usd,
        costs.slippage_bps,
        costs.fx_friction_bps,
        costs.conversion_bps,
    )
    if not all(_finite_nonnegative(value) for value in numeric):
        return reject("invalid execution parameters")
    if (
        min_order_gbp < 150
        or name_cap > 0.3
        or name_cap == 0
        or not 0.02 <= cash_buffer < 1
        or gross_ceiling > 1
        or costs.commission_min_usd < 0.35
        or costs.slippage_bps < 5
        or costs.fx_friction_bps < 5
        or costs.conversion_bps >= 10000
    ):
        return reject("execution parameters violate risk or cost floors")
    for weights in (target_weights, account.holdings):
        if any(not s or s.strip() != s or not _finite_nonnegative(w) for s, w in weights.items()):
            return reject("invalid holding or target")
    targets = {s: w for s, w in target_weights.items() if w > 0}
    if (
        len(targets) > 5
        or any(w > name_cap + 1e-12 for w in targets.values())
        or math.fsum(targets.values()) > min(gross_ceiling, 1 - cash_buffer) + 1e-12
    ):
        return reject("requested target violates portfolio constraints")
    needed = set(targets) | {s for s, q in account.holdings.items() if q > 0}
    if any(
        s not in raw_open or not _finite_nonnegative(raw_open[s]) or raw_open[s] == 0
        for s in needed
    ):
        return reject("missing or invalid tradable open for held/target identity")
    initial_equity = _equity(account, raw_open, gbp_per_usd)
    if initial_equity <= 0:
        return reject("nonpositive account equity")
    conversion_rate = costs.conversion_bps / 10000

    def simulate(sizing_equity: float) -> ExecutionResult:
        cash_gbp, cash_usd = account.cash_gbp, account.cash_usd
        holdings = {s: q for s, q in account.holdings.items() if q > 0}
        fills: list[Fill] = []
        skips: list[SkippedOrder] = []
        conversions: list[Conversion] = []
        orders: list[tuple[str, float, bool]] = []
        for symbol in sorted(needed):
            old = holdings.get(symbol, 0.0)
            ideal = targets.get(symbol, 0.0) * sizing_equity / raw_open[symbol]
            desired = ideal if fractional else float(math.floor(ideal))
            # Risk-only events cannot increase shares after an overnight price/FX move.
            if reductions_only:
                desired = min(desired, old)
            difference = desired - old
            if math.isclose(difference, 0, abs_tol=1e-10):
                if old == 0 and targets.get(symbol, 0) > 0:
                    skips.append(SkippedOrder(symbol, "rounded_below_one_share"))
                continue
            required = difference < 0 and (symbol in mandatory or symbol not in targets)
            if not fractional and not math.isclose(
                abs(difference), round(abs(difference)), abs_tol=1e-10
            ):
                raise _Infeasible(f"unsupported fractional residual: {symbol}")
            if abs(difference) * raw_open[symbol] * gbp_per_usd < min_order_gbp and not required:
                skips.append(SkippedOrder(symbol, "below_minimum_order"))
                continue
            orders.append((symbol, difference, required))

        def funding_order(order: tuple[str, float, bool]) -> tuple[int, str]:
            symbol, difference, _ = order
            if difference > 0:
                return (2, symbol)
            quantity = -difference
            sale_price = raw_open[symbol] * (1 - costs.slippage_bps / 10000)
            notional = quantity * sale_price
            commission = max(costs.commission_min_usd, quantity * costs.commission_per_share)
            proceeds = notional - commission - notional * costs.fx_friction_bps / 10000
            # Profitable-in-cash sales fund mandatory dust-sale fees before buys.
            # Stable identity is only a tie-breaker, never a feasibility constraint.
            return (0 if proceeds >= 0 else 1, symbol)

        for symbol, difference, required in sorted(orders, key=funding_order):
            quantity = abs(difference)
            buying = difference > 0
            reference = raw_open[symbol]
            price = reference * (1 + (1 if buying else -1) * costs.slippage_bps / 10000)
            if price <= 0:
                raise _Infeasible("nonpositive modeled fill price")
            notional = quantity * price
            commission = max(costs.commission_min_usd, quantity * costs.commission_per_share)
            friction = notional * costs.fx_friction_bps / 10000
            slippage = quantity * abs(price - reference)
            if buying:
                debit = notional + commission + friction
                needed_usd = max(0.0, debit - cash_usd)
                if needed_usd:
                    fee = needed_usd * conversion_rate
                    debit_gbp = (needed_usd + fee) * gbp_per_usd
                    if debit_gbp > cash_gbp + 1e-10:
                        raise _Infeasible("insufficient GBP cash for purchase and conversion fee")
                    cash_gbp -= debit_gbp
                    cash_usd += needed_usd
                    conversions.append(Conversion("GBP_TO_USD", needed_usd, fee, fee * gbp_per_usd))
                cash_usd -= debit
            else:
                proceeds = notional - commission - friction
                cash_usd += proceeds
                if cash_usd < -1e-10:
                    # A tiny mandatory sale may cost more than its proceeds.
                    shortage = -cash_usd
                    fee = shortage * conversion_rate
                    debit_gbp = (shortage + fee) * gbp_per_usd
                    if debit_gbp > cash_gbp + 1e-10:
                        raise _Infeasible("insufficient cash for mandatory sale fees")
                    cash_gbp -= debit_gbp
                    cash_usd = 0.0
                    conversions.append(Conversion("GBP_TO_USD", shortage, fee, fee * gbp_per_usd))
                if cash_usd > 0:
                    fee = cash_usd * conversion_rate
                    cash_gbp += (cash_usd - fee) * gbp_per_usd
                    conversions.append(Conversion("USD_TO_GBP", cash_usd, fee, fee * gbp_per_usd))
                    cash_usd = 0.0
            holdings[symbol] = holdings.get(symbol, 0.0) + difference
            if holdings[symbol] <= 1e-10:
                holdings.pop(symbol)
            fills.append(
                Fill(
                    symbol,
                    "buy" if buying else "sell",
                    quantity,
                    reference,
                    price,
                    commission,
                    slippage,
                    friction,
                    commission * gbp_per_usd,
                    slippage * gbp_per_usd,
                    friction * gbp_per_usd,
                    required,
                    gbp_per_usd,
                )
            )
        updated = Account(max(0.0, cash_gbp), max(0.0, cash_usd), holdings, account.receivables_usd)
        final_equity = _equity(updated, raw_open, gbp_per_usd)
        if final_equity <= 0:
            raise _Infeasible("post-cost equity is nonpositive")
        actual_weights = {s: q * raw_open[s] / final_equity for s, q in holdings.items()}
        return ExecutionResult(
            updated, tuple(fills), tuple(skips), tuple(conversions), actual_weights, True
        )

    # Solve the fee-dependent NAV target without exposing intermediate fills.
    sizing_equity = initial_equity
    last_failure = "post-cost plan infeasible"
    for _ in range(64):
        try:
            result = simulate(sizing_equity)
        except _Infeasible as exc:
            last_failure = str(exc)
            # Never force extra sales or silently enlarge discretionary orders.
            if "insufficient GBP" in last_failure:
                sizing_equity *= 0.995
                continue
            return reject(last_failure)
        final_equity = _equity(result.account, raw_open, gbp_per_usd)
        weights = result.accepted_weights
        valid = (
            len(weights) <= 5
            and all(w <= name_cap + 1e-12 for w in weights.values())
            and math.fsum(weights.values()) <= min(gross_ceiling, 1 - cash_buffer) + 1e-12
            and (result.account.cash_gbp / gbp_per_usd + result.account.cash_usd)
            >= final_equity * cash_buffer - 1e-9
        )
        # Sizing at less than post-cost NAV is conservative; skipped trades must
        # independently satisfy caps/cash and may leave the account in cash.
        if valid and sizing_equity <= final_equity + 1e-9:
            return result
        new_sizing = min(sizing_equity, final_equity * (1 - 1e-12))
        if abs(new_sizing - sizing_equity) < 1e-10:
            return reject("post-cost plan violates cash, concentration or holding-count limits")
        sizing_equity = new_sizing
    return reject(last_failure)
