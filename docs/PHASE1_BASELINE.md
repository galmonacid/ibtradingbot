# Phase 1 Deterministic Baseline

## Purpose and limits

This phase proves the causal research plumbing in `docs/ROADMAP.md`. It does not
prove that the strategy has investment merit or meets deployment gates. The
checked-in long price fixture is synthetic, and the versioned seed universe is
current engineering metadata rather than historical point-in-time membership.

Phase 2 adds inverse-volatility sizing, volatility targeting, rank hysteresis,
stress costs, and drawdown controls. Phase 3 retains point-in-time
universe reconstruction, walk-forward analysis, sensitivity analysis,
bootstrap analysis, and deployment-gate evidence. ML and broker connectivity
remain disabled.

## Deterministic conventions

- Research returns and marks use adjusted close. Execution uses raw open scaled
  by that session's `adjusted_close / close` factor.
- Liquidity uses contemporaneous raw `close * volume`.
- A skip-five return is `price[t-5] / price[t-5-lookback] - 1`.
- Rolling volatility is sample standard deviation of daily returns, annualized
  by `sqrt(252)`. Cross-sectional score normalization uses population standard
  deviation after linearly interpolated 1st/99th percentile winsorization.
- A zero-variance cross-section receives zero z-scores. Score ties use ascending
  symbol order. Price equal to SMA200 fails the trend rule.
- Breadth uses only securities passing versioned instrument, history, price, and
  trailing-liquidity checks as of that session. From the 252-session eligibility
  threshold onward, every candidate must have a bar on every benchmark session
  in the growing required window, capped at 258 sessions (the endpoint plus the
  252-session lookback and five-session skip). Internal gaps are explicit
  `missing_session_history` exclusions; feature windows never silently compress
  missing market sessions into shorter elapsed periods.
- The expanding SPY volatility percentile contains prior observations only. A
  session with insufficient percentile history is neutral.
- Regimes are evaluated in this order: risk-on; risk-off; otherwise neutral.
- A weekly signal occurs only on a session explicitly marked as the week end in
  the configured, versioned XNYS calendar. Benchmark dates must exactly match
  that calendar over the research interval, so holidays and incomplete final
  weeks do not depend on future price availability.
- Equal weights are capped by regime exposure, the configured cash buffer, 30%
  per name, and five names. The engine solves fills against post-cost equity and
  preflights the complete rebalance before changing state. An account too small
  for fixed commissions fails closed instead of receiving partial legs that
  would breach concentration or cash constraints. Target and fill weights obey
  the caps; later close-marked weights may drift with market prices while the
  cash-only, long-only ledger remains below 100% gross exposure.
- The USD research ledger applies commission once per executed side, slippage
  adversely in the execution price, and FX basis points as per-side notional
  friction. It does not model GBP/USD returns.
- Split-adjusted inputs preserve research continuity and record a quality
  notice. Suspicious or unexplained discontinuities are quarantined rather than
  silently repaired. A missing held bar fails closed unless the versioned
  corporate-action input provides a delisting cash-per-share value; only that
  explicit recovery creates a `disappearance` ledger entry.

## Reporting

Reports contain the metrics required by `docs/BACKTEST_AND_VALIDATION.md`, SPY
buy-and-hold and zero-return cash references on the same sessions, and excess
CAGR, tracking error, information ratio, and up/down capture. The risk-free and
cash return are zero in Phase 1. Undefined ratios are JSON `null`, never
infinity or NaN.

Trade count, holding periods, and trade-return statistics use FIFO realized
exit lots. Entry and exit fees are included in lot cash flows, and exit fees are
allocated pro rata when one sale consumes multiple lots. Profit factor uses
lot-level monetary net profits divided by monetary net losses. The order ledger
retains the primitives needed to reconstruct those outcomes rather than mixing
in a different average-cost convention. Turnover is total executed
buy-plus-sell notional divided by average account equity.

Provenance records the Git revision and dirty state, initial USD research cash,
raw configuration/data/universe/calendar/corporate-action hashes, their
versions, the strategy version, disabled ML version, and a UTC run timestamp.
With the optional timestamp fixed, identical inputs and working-tree state
produce an identical JSON economic report.
