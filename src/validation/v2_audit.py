"""Independent cash/share reconciliation of issued V2 development execution ledgers.

A passing reconciliation proves ledger arithmetic and causal fill inputs. It does
not certify missing instrument metadata, FX vintages, dividend payment dates or OOS.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from src.backtest.v2 import V2Market
from src.backtest.v2_execution import FeeModel
from src.config.v2 import V2Config
from src.data.fx import FXHistory


@dataclass(frozen=True)
class V2LedgerAudit:
    passed: bool
    findings: tuple[str, ...]
    ledger_sha256: str
    reconciled_sessions: int
    trading_fills: int
    certification_scope: str = "development ledger reconciliation only"


def audit_v2_ledger(
    ledger: dict[str, Any],
    market: V2Market,
    fx: FXHistory,
    config: V2Config,
    costs: FeeModel,
    *,
    initial_capital_gbp: float,
    start: date,
    end: date,
    monthly_fee_gbp: float = 3.0,
) -> V2LedgerAudit:
    """Rebuild cash, raw holdings and receivables from canonical actions and fills."""
    findings: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            findings.append(message)

    def equal(actual: float, expected: float, label: str) -> None:
        check(
            math.isfinite(actual)
            and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-7),
            label,
        )

    payload = json.dumps(ledger, sort_keys=True, default=str, allow_nan=False).encode()
    digest = hashlib.sha256(payload).hexdigest()
    days = tuple(d for d in market.calendar.sessions if start <= d <= end)
    points = ledger.get("points", [])
    check(
        tuple(p["date"] for p in points) == tuple(d.isoformat() for d in days),
        "point population differs from required session calendar",
    )
    check(ledger.get("config_sha256") == config.sha256, "configuration binding mismatch")
    check(ledger.get("costs") == asdict(costs), "cost binding mismatch")
    equal(float(ledger["initial_capital_gbp"]), initial_capital_gbp, "initial capital mismatch")
    first_open = datetime.combine(days[0], time(9, 30), ZoneInfo("America/New_York"))
    first_fx = fx.at(first_open, max_age_days=config.max_fx_age_days).gbp_per_usd
    equal(
        float(ledger["initial_capital_usd"]),
        initial_capital_gbp / first_fx,
        "initial USD capital mismatch",
    )
    actions: dict[date, list[Any]] = defaultdict(list)
    fills: dict[date, list[dict[str, Any]]] = defaultdict(list)
    conversions: dict[date, list[dict[str, Any]]] = defaultdict(list)
    fees: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for action in market.actions:
        actions[action.action_date].append(action)
    for key, output in (("fills", fills), ("conversions", conversions), ("fees", fees)):
        for row in ledger.get(key, []):
            day = date.fromisoformat(row["date"])
            check(day in days, f"{key} outside required sessions")
            output[day].append(row)
    decisions = [d for d in ledger.get("decisions", []) if d["status"] == "applied"]
    holdings: dict[str, float] = {}
    lots: dict[str, deque[tuple[float, date, float, float]]] = defaultdict(deque)
    entries: dict[str, date] = {}
    expected_lots: list[dict[str, Any]] = []
    expected_episodes: list[dict[str, Any]] = []

    def book(
        symbol: str, side: str, q: float, price: float, fee: float, day: date, rate: float
    ) -> None:
        if side == "buy":
            entries.setdefault(symbol, day)
            basis = price + fee / q
            lots[symbol].append((q, day, basis * rate, basis))
            return
        remaining = q
        while remaining > 1e-8:
            if not lots[symbol]:
                check(False, f"FIFO inventory exhausted {day} {symbol}")
                return
            old, opened, gbp_basis, usd_basis = lots[symbol].popleft()
            closed = min(old, remaining)
            expected_lots.append(
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
            if old - closed > 1e-8:
                lots[symbol].appendleft((old - closed, opened, gbp_basis, usd_basis))
        if not lots[symbol] and symbol in entries:
            expected_episodes.append(
                dict(
                    security_id=symbol, entry=entries.pop(symbol).isoformat(), exit=day.isoformat()
                )
            )

    cash_gbp, cash_usd, receivables = initial_capital_gbp, 0.0, 0.0
    high_water, halted = initial_capital_gbp, False
    count = 0
    session_index = {d: i for i, d in enumerate(market.calendar.sessions)}
    month_ends = {
        a
        for a, b in zip(market.calendar.sessions, market.calendar.sessions[1:], strict=False)
        if (a.year, a.month) != (b.year, b.month)
    }
    for point in points:
        day = date.fromisoformat(point["date"])
        opening = datetime.combine(day, time(9, 30), ZoneInfo("America/New_York"))
        closing = datetime.combine(day, time(16), ZoneInfo("America/New_York"))
        opening_fx = fx.at(opening, max_age_days=config.max_fx_age_days).gbp_per_usd
        closing_fx = fx.at(closing, max_age_days=config.max_fx_age_days).gbp_per_usd
        dispositions: dict[str, tuple[float, float]] = {}
        for action in sorted(actions[day], key=lambda a: (a.action_type != "split", a.security_id)):
            q = holdings.get(action.security_id, 0.0)
            if q <= 0:
                continue
            if action.action_type == "split":
                holdings[action.security_id] = q * action.value
                lots[action.security_id] = deque(
                    (amount * action.value, opened, gbp / action.value, usd / action.value)
                    for amount, opened, gbp, usd in lots[action.security_id]
                )
            elif action.action_type == "dividend":
                receivables += q * action.value
            elif action.action_type == "delisting":
                cash_usd += q * action.value
                dispositions[action.security_id] = q, action.value
                del holdings[action.security_id]
        seen: set[str] = set()
        for fill in fills[day]:
            symbol = fill["security_id"]
            q, price = float(fill["shares"]), float(fill["execution_price"])
            check(q > 0 and math.isfinite(q), f"invalid fill quantity {day} {symbol}")
            equal(float(fill["gbp_per_usd"]), opening_fx, f"fill FX mismatch {day} {symbol}")
            if fill["reason"] == "delisting_recovery":
                expected = dispositions.pop(symbol, None)
                check(expected is not None, f"unbacked disposition {day} {symbol}")
                if expected:
                    equal(q, expected[0], f"disposition quantity mismatch {day} {symbol}")
                    equal(price, expected[1], f"disposition price mismatch {day} {symbol}")
                    book(symbol, "sell", expected[0], expected[1], 0, day, opening_fx)
                continue
            count += 1
            check(symbol not in seen, f"duplicate trading fill {day} {symbol}")
            seen.add(symbol)
            signal = date.fromisoformat(fill["signal_date"])
            check(
                signal in session_index
                and day in session_index
                and session_index[day] - session_index.get(signal, session_index[day])
                == config.execution_delay_sessions,
                f"noncausal execution {day} {symbol}",
            )
            amended = fill.get("amended_at")
            if amended is not None:
                amendment = date.fromisoformat(amended)
                check(signal <= amendment < day, f"noncausal risk amendment {day} {symbol}")
                check(
                    fill["reason"] != "monthly_selection" and fill["side"] == "sell",
                    f"risk amendment permits new risk {day} {symbol}",
                )
            matching = [
                d
                for d in decisions
                if d["execution_date"] == day.isoformat() and d["signal_date"] == signal.isoformat()
            ]
            check(len(matching) == 1, f"fill lacks unique applied decision {day} {symbol}")
            if len(matching) == 1:
                for field in ("reason", "amended_at"):
                    check(
                        matching[0].get(field) == fill.get(field),
                        f"fill decision {field} mismatch {day} {symbol}",
                    )
            row = market.bars.get(symbol, {}).get(day)
            check(row is not None, f"fill lacks canonical open {day} {symbol}")
            if row is None:
                continue
            side = fill["side"]
            check(side in {"buy", "sell"}, f"invalid fill side {day} {symbol}")
            equal(float(fill["reference_price"]), row.open, f"raw open mismatch {day} {symbol}")
            expected_price = row.open * (
                1 + (1 if side == "buy" else -1) * costs.slippage_bps / 10000
            )
            equal(price, expected_price, f"execution price mismatch {day} {symbol}")
            commission = max(costs.commission_min_usd, q * costs.commission_per_share)
            friction = q * price * costs.fx_friction_bps / 10000
            for name, expected_cost in (
                ("commission", commission),
                ("fx_friction", friction),
                ("slippage", q * abs(price - row.open)),
            ):
                equal(
                    float(fill[f"{name}_usd"]), expected_cost, f"{name} USD mismatch {day} {symbol}"
                )
                equal(
                    float(fill[f"{name}_gbp"]),
                    expected_cost * opening_fx,
                    f"{name} GBP mismatch {day} {symbol}",
                )
            if q > 0:
                book(symbol, side, q, price, commission + friction, day, opening_fx)
            if side == "buy":
                check(not halted, f"buy after permanent halt {day} {symbol}")
                check(symbol in market.active[day], f"buy outside PIT membership {day} {symbol}")
                check(
                    q * row.open * opening_fx >= config.min_order_value_gbp - 1e-7,
                    f"buy below economic minimum {day} {symbol}",
                )
                holdings[symbol] = holdings.get(symbol, 0) + q
                cash_usd -= q * price + commission + friction
            else:
                check(q <= holdings.get(symbol, 0) + 1e-8, f"sell exceeds inventory {day} {symbol}")
                holdings[symbol] = holdings.get(symbol, 0) - q
                cash_usd += q * price - commission - friction
                if holdings[symbol] <= 1e-10:
                    holdings.pop(symbol)
        check(not dispositions, f"missing disposition trace {day}")
        for conversion in conversions[day]:
            amount = float(conversion["amount_usd"])
            fee = amount * costs.conversion_bps / 10000
            equal(float(conversion["fee_usd"]), fee, f"conversion fee USD mismatch {day}")
            equal(
                float(conversion["fee_gbp"]), fee * opening_fx, f"conversion fee GBP mismatch {day}"
            )
            check(amount >= 0 and math.isfinite(amount), f"invalid conversion amount {day}")
            if conversion["direction"] == "GBP_TO_USD":
                cash_gbp -= (amount + fee) * opening_fx
                cash_usd += amount
            elif conversion["direction"] == "USD_TO_GBP":
                cash_usd -= amount
                cash_gbp += (amount - fee) * opening_fx
            else:
                check(False, f"invalid conversion direction {day}")
        expected_fee = monthly_fee_gbp if day in month_ends else 0.0
        equal(
            sum(float(f["amount_gbp"]) for f in fees[day]),
            expected_fee,
            f"monthly fee population mismatch {day}",
        )
        cash_gbp -= expected_fee
        check(cash_gbp >= -1e-7 and cash_usd >= -1e-7, f"negative cash {day}")
        check(set(point["holdings"]) == set(holdings), f"held identity mismatch {day}")
        for symbol, q in holdings.items():
            equal(
                float(point["holdings"].get(symbol, -1)),
                q,
                f"holding quantity mismatch {day} {symbol}",
            )
        equal(float(point["cash_gbp"]), cash_gbp, f"GBP cash mismatch {day}")
        equal(float(point["cash_usd"]), cash_usd, f"USD cash mismatch {day}")
        equal(float(point["receivables_usd"]), receivables, f"receivables mismatch {day}")
        stock_value = math.fsum(q * market.bars[s][day].close for s, q in holdings.items())
        nav = cash_gbp + closing_fx * (cash_usd + receivables + stock_value)
        equal(float(point["equity_gbp"]), nav, f"GBP NAV mismatch {day}")
        equal(float(point["equity_usd"]), nav / closing_fx, f"USD NAV mismatch {day}")
        equal(
            float(point["gross_exposure"]),
            stock_value * closing_fx / nav,
            f"gross exposure mismatch {day}",
        )
        high_water = max(high_water, nav)
        drawdown = 1 - nav / high_water
        halted = halted or drawdown >= 0.15 - 1e-12
        equal(float(point["drawdown"]), drawdown, f"drawdown mismatch {day}")
        check(point["hard_halted"] == halted, f"hard halt latch mismatch {day}")
    observed_lots = ledger.get("closed_lots", [])
    check(len(observed_lots) == len(expected_lots), "FIFO closure population mismatch")
    for observed, expected_lot in zip(observed_lots, expected_lots, strict=False):
        check(set(observed) == set(expected_lot), "FIFO closure schema mismatch")
        for key, value in expected_lot.items():
            if isinstance(value, float):
                equal(float(observed.get(key, float("nan"))), value, f"FIFO {key} mismatch")
            else:
                check(observed.get(key) == value, f"FIFO {key} mismatch")
    check(
        ledger.get("episodes", []) == expected_episodes, "independent episode population mismatch"
    )
    return V2LedgerAudit(not findings, tuple(findings), digest, len(points), count)
