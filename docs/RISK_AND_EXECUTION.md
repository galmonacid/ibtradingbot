# Risk and execution boundaries

R3 is offline research for an initial £3,000 account. The percentage-based risk limits below remain unchanged; qualification and any future authorized launch use that starting capital. No broker adapter, account access, orders, data purchase or live deployment is authorized by the documentation reset.

## Hard limits shared by every candidate

Long-only cash equities; no leverage, margin, shorting or derivatives. At most five holdings, each <=30% of post-cost NAV, gross <=100% and at least the configured 2% cash buffer. Reserve additional known fees when necessary. Market moves can breach limits between observations; record the breach and reduce safely rather than claim continuous protection.

GBP account high-water mark never decreases or resets at month-end, refits or fold boundaries. At 10% drawdown, cap each name at 15% and prevent gross increases. Clear the soft state only below 10%, with increases deferred to scheduled selection. At 15%, latch the account in review, cancel unsafe pending entries and request liquidation at the next safely executable opportunity. Never optimize, disable or automatically reset this halt. Gaps and execution delays can make realized loss exceed 15%; the halt is not a stop-loss guarantee.

Risk reductions cannot create unrelated buys or redistribute released risk. Economic order minimums and resize bands never prevent mandatory exits. Whole-share rounding cannot increase target risk. Fractional residual handling requires verified instrument/account support; otherwise block and escalate the unresolved state.

## Event priority and failure behavior

1. Validate data, clock, session calendar and account state; mismatches disable trading.
2. Apply hard halt and cancel pending increases.
3. Resolve mandatory exits and corporate-action state.
4. Apply soft drawdown, position, cash, exposure and volatility reductions.
5. Consider scheduled candidate entries/resizes only if every prior check passes.

Merge overlapping intents into one account plan. Pending reductions retain their original deadlines when risk escalates. Missing held prices invalidate valuation; do not fabricate a liquidation price. Model failures/staleness block new risk and preserve independent risk controls. Do not silently revert to another strategy.

Backtests may preflight an atomic proposed plan; a real broker does not provide atomic multi-leg fills. Future paper execution must explicitly handle partial fills and reconcile before releasing cash for subsequent purchases. Never assume submitted sales provide cash; respect settlement and account-specific buying power. Fees must not create an unmodeled margin loan.

## Required future execution state machine

Persist durable intent identity, model/config/data versions, target, order revisions, broker identifiers, fills and reconciliation result. Derive positions from actual fills and broker records. Use stable idempotency keys across retries, and reconcile open orders before any resubmission after timeout/restart. Never automatically place corrective orders when expected and broker state disagree.

Before submission verify instrument/ISA eligibility, tradable price freshness, spreads, permissions, cash, existing orders, risk state and exchange session. Broker integration must keep selection logic separate from execution. Use explicit limit bounds, expiry and cancel/replace rules tested in paper mode; no executable broker interface is invented by this document.

## Readiness

The full [validation contract](BACKTEST_AND_VALIDATION.md) precedes broker paper work. Independent tests must cover duplicate submissions, partial fills, stale/missing data, adverse overnight moves, FX changes, action entitlements, fee-deficit dust, restarts and permanent halts. Any unexplained reconciliation defect blocks live trading. Live orders always require an explicit user request for that action after gates pass.
