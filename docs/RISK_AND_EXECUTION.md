# Risk Management and Execution Specification

## V2 research boundary

The proposed [V2 specification](QUANT_SPEC.md) preserves the account risk limits and
10%/15% drawdown controls below. Its monthly schedule and discretionary order band never
delay mandatory risk reductions. For V2, the £150 minimum applies to entries and optional
resizes; required exits/reductions may be smaller. Rounding must not waive the configured
cash buffer: reduce the purchase or reject the plan. The single-name emergency stop
remains deferred until its data/action checks are implemented, as recorded in Phase 2.
These are explicit research requirements, not a claim that V2 or live execution exists.

## 1. Risk hierarchy

Risk controls are ordered:

1. Account safety
2. Prevent leverage
3. Prevent unintended positions
4. Limit drawdown
5. Limit concentration
6. Limit execution errors
7. Optimize return

A trading opportunity must never override a risk invariant.

---

## 2. Portfolio limits

Hard constraints:

```text
gross exposure <= 100%
net exposure >= 0%
short exposure = 0%
single position <= 30%
number of positions <= 5
cash >= configured buffer (default 2%); rounding must not waive it
```

---

## 3. Drawdown controls

Track equity high-water mark.

```text
drawdown = current_equity / high_water_mark - 1
```

### Soft drawdown

At:

```text
-10%
```

actions:

- no increase in regime exposure,
- halve maximum position size,
- disable marginal ML-approved trades,
- issue alert.

### Hard drawdown

At:

```text
-15%
```

actions:

- close positions on next safely executable session,
- block new entries,
- enter risk-review mode,
- require explicit human re-enable.

This is a **live-account circuit breaker**, not a backtest optimization parameter.

---

## 4. Single-position risk

Emergency stop:

```text
-12% from entry
```

This should trigger only after checking for:

- erroneous market data,
- split/corporate action,
- symbol mapping errors.

Ordinary exits remain ranking/trend based.

---

## 5. Order sizing

For target weight `w_i`:

```text
target_value = account_net_liquidation * w_i
target_shares = target_value / reference_price
```

Round according to fractional-share capability.

Do not submit trades below:

```text
£150 equivalent
```

unless explicitly overridden for testing.

---

## 6. Order type

Default:

```text
marketable limit order
```

Reason:

- avoids uncontrolled price execution,
- still provides high fill probability,
- suitable for liquid large-cap equities.

For a buy:

```text
limit = best_ask * (1 + max_offset_bps/10000)
```

For a sell:

```text
limit = best_bid * (1 - max_offset_bps/10000)
```

Default:

```text
max_offset_bps = 20
```

Do not trade if:

```text
spread > 15 bps
```

unless manually approved.

---

## 7. Reconciliation before trading

Before any order submission:

Compare:

```text
broker positions
broker cash
local expected positions
local open orders
```

If mismatch exists:

```text
TRADING_ENABLED = false
```

and alert.

Never auto-correct a large unknown mismatch with new trades.

---

## 8. Idempotency

Every intended order must have a deterministic client identifier.

Example:

```text
2026-09-04_AAPL_REBALANCE_BUY
```

The system must be safe if the execution process runs twice.

Duplicate intent must not create duplicate orders.

---

## 9. Partial fills

Execution state machine:

```text
CREATED
SUBMITTED
PARTIALLY_FILLED
FILLED
CANCELLED
REJECTED
```

Portfolio state must derive from actual broker fills, never solely from submitted orders.

---

## 10. Failure behavior

If:

- broker API unavailable,
- market data missing,
- time synchronization invalid,
- account cannot be reconciled,
- model artifact missing,
- configuration invalid,

then:

```text
do not open new positions
```

Existing holdings remain unchanged unless a predefined emergency rule applies.

Fail closed, not open.

---

## 11. Alerts

Alert severity:

### INFO

- rebalance completed
- model retrained
- no trades required

### WARNING

- missed data
- unusually wide spread
- one rejected order
- soft drawdown reached

### CRITICAL

- reconciliation mismatch
- hard drawdown reached
- unexpected short position
- leverage detected
- repeated broker rejection
- corrupted data/model artifact

Suggested channel:

```text
email or Telegram
```

---

## 12. Daily reconciliation report

Include:

```text
account NAV
cash
positions
weights
unrealized P&L
realized P&L
regime
drawdown
target portfolio
executed orders
failed orders
strategy version
model version
data timestamp
```

---

## 13. Kill switch

Support:

```text
TRADING_ENABLED=false
```

through:

- config,
- environment variable,
- local emergency file.

No code deployment should be required to disable trading.

---

## 14. Secrets

Never commit:

```text
broker credentials
API secrets
account numbers
alert tokens
```

Use environment variables or an OS keychain.

Provide only:

```text
.env.example
```

in Git.
