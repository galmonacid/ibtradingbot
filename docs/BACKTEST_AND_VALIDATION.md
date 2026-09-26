# Backtest and Validation Specification

## Version scope

The existing engine conventions, V1 grids and mandatory thresholds below remain the
Phase 1–3 reference. The proposed [V2 strategy](QUANT_SPEC.md) adds a fixed candidate,
explicit sensitivity criteria, GBP small-account qualification and a freeze-before-test
protocol. Development implementation now has a separate V2 command; qualification
remains blocked (see PHASE3_V2_IMPLEMENTATION.md). All existing mandatory gates remain;
observed V1 test dates cannot become fresh V2 OOS evidence. V2's monthly timing and
sensitivity contract supersede the V1 weekly/grid examples only for that new version.

## 1. Principle

A strategy is not accepted because it has a high historical CAGR.

It is accepted only if it performs reasonably across:

- different time periods,
- different parameter choices,
- different market regimes,
- realistic costs,
- unseen data.

---

## 2. Backtest engine requirements

The engine must support:

- daily bars
- portfolio cash
- fractional shares
- transaction costs
- slippage
- delayed execution
- corporate actions
- delistings
- position limits
- weekly rebalance
- regime exposure scaling

No trade may execute using a price unavailable when the order decision was made.

Default model:

```text
signal computed after close on day t
trade executed on day t+1
```

Preferred execution price for research:

```text
next-day open + modeled slippage
```

Alternative conservative test:

```text
next-day VWAP proxy or close
```

---

## 3. Transaction cost model

Default minimum assumptions:

```text
commission = $0.35 per order
slippage = 5 bps per side
FX/currency friction buffer = 5 bps
```

Stress test:

```text
slippage = 10 bps per side
commission = 2x default
```

The strategy must remain viable under the stress scenario.

---

## 4. Historical test window

Use the longest clean point-in-time dataset reasonably available.

The Phase 3 initial dataset uses version-pinned open-source membership records plus Tiingo:
`chinobing/historical_sp500_constituents` provides primary dated S&P 500 membership;
`unliftedq/index-constitution` provides ticker-change and delisting events; and
The Wikipedia and historical iShares IVV streams in `riazarbi/sp500-scraper` provide membership
QA from one pinned repository. Tiingo
provides raw/adjusted bars and corporate actions. Its manifest and independent 50–100-event
constituent-change audit are required alongside the normal completeness checks. A licensed
CRSP/WRDS dataset is not required to begin or complete this initial validation route.

Available FMP Basic price, dividend, delisting, and security-metadata endpoints are retained as
secondary validation evidence. Disagreements must be reconciled or quarantined; FMP must not fill
missing Tiingo data or alter the pinned membership/identity history.

Preferred minimum:

```text
2007 -> present
```

This should include:

- Global Financial Crisis
- Euro-area stress
- 2015–2016 selloff
- Q4 2018
- COVID crash
- 2022 bear market
- strong bull markets
- low-volatility periods
- high-rate environments

---

## 5. Walk-forward validation

Recommended rolling structure:

```text
Train:      8 years
Validation: 2 years
Test:       1 year
Step:       6 months
```

Example:

```text
Train      2007–2014
Validate   2015–2016
Test       2017

Train      2007–2015
Validate   2016–2017
Test       2018
...
```

Expanding training windows are preferred initially.

---

## 6. ML validation

Because labels overlap, ordinary random K-fold cross-validation is prohibited.

Use:

- chronological splits,
- purging of overlapping observations,
- embargo after train/validation boundaries.

Default embargo:

```text
20 trading days
```

because the target horizon is 20 days.

---

## 7. Parameter selection

Optimize on validation data only.

Use the predeclared broad one-axis-at-a-time grid around the production baseline. Every
configured axis is evaluated, but these results are not represented as a full Cartesian
interaction search.

Example:

```text
positions: [3, 4, 5]
rebalance: [weekly, biweekly]
skip_recent_days: [0, 5, 10]
vol_target: [0.10, 0.12, 0.15]
risk_on_breadth: [0.55, 0.60, 0.65]
```

Select **stable plateaus**, not isolated maxima.

Bad:

```text
parameter=17 gives 21.3%
parameter=16 gives 9.2%
parameter=18 gives 8.7%
```

Good:

```text
parameters 14–20 all give 11–14%
```

---

## 8. Required metrics

Calculate at least:

```text
CAGR
annualized volatility
Sharpe ratio
Sortino ratio
maximum drawdown
Calmar ratio
win rate
profit factor
turnover
average holding period
exposure
number of trades
average trade return
median trade return
best/worst trade
best/worst month
best/worst year
```

Also compare with:

```text
SPY buy-and-hold
60/40-style defensive reference if useful
cash
```

The bot does not need to beat SPY every year.

---

## 9. Mandatory deployment gates

Any deterministic candidate, including V2, may proceed to paper trading only if:

### Return

```text
Out-of-sample CAGR >= 8%
```

A 10–20% CAGR is desired, but not required at the first gate.

### Sharpe

```text
Out-of-sample Sharpe >= 0.8
```

### Drawdown

```text
Out-of-sample maximum drawdown <= 15%
```

### Cost resilience

After stressed costs:

```text
CAGR remains >= 6%
Sharpe remains >= 0.6
```

### Diversification of evidence

No single calendar year contributes:

```text
> 35% of total cumulative profit
```

No single stock contributes:

```text
> 20% of total cumulative profit
```

### Trade count

At least:

```text
150 historical closed trades
```

or enough observations to establish stability.

### Parameter robustness

Nearby parameter values must remain economically viable.

---

## 10. Benchmark-relative evaluation

Calculate:

```text
excess CAGR
tracking error
information ratio
up-market capture
down-market capture
```

A strategy that earns slightly less than SPY with dramatically smaller drawdowns may still be valuable.

---

## 11. Monte Carlo / bootstrap tests

Perform block bootstrap on:

- daily strategy returns,
- trade returns,
- market regimes.

Minimum:

```text
2000 iterations
```

Estimate distributions for:

```text
CAGR
max drawdown
Sharpe
1-year return
3-year return
```

Reject if the strategy's favorable result depends on an implausibly narrow path.

The Phase 3 lower-confidence viability gates use the configured worst result across daily-
block and complete-regime-run bootstraps. Defaults require 5th-percentile CAGR >= 0%,
5th-percentile Sharpe >= 0, and 95th-percentile maximum drawdown <= 25%. These deliberately
looser tail thresholds supplement rather than replace the point-estimate deployment gates.

---

## 12. Sensitivity tests

Repeat backtest with:

```text
execution delayed 1 day
slippage doubled
commissions doubled
rebalance day changed
top N changed
SMA windows changed +/- 20%
momentum weights perturbed
```

A viable strategy should degrade gradually.

---

## 13. Ablation tests

Test each component independently:

```text
momentum only
momentum + trend
momentum + trend + regime
momentum + trend + regime + vol sizing
full deterministic model
full model + ML
```

Every additional component must justify itself.

---

## 14. Paper-trading gate

Minimum:

```text
60 trading days
```

Prefer:

```text
90–120 trading days
```

Paper results must match expected behavior for:

- signal timestamps
- order quantities
- fills
- transaction costs
- portfolio exposure
- cash
- corporate actions

Before live deployment, no unexplained divergence between paper and simulated behavior may remain.

---

## 15. Live capital progression

Suggested progression:

```text
Stage A: £0        paper
Stage B: £1,000    live
Stage C: £3,000    live
Stage D: larger capital only after evidence
```

Do not increase capital because of one good month.

Suggested requirement before increasing capital:

```text
>= 6 months live
and
live drawdown <= expected stress range
and
no material execution defects
```
