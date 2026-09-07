# Quantitative Strategy Specification

## 1. Objective

Build a long-only, medium-term momentum strategy for liquid US equities that can be executed in a UK Stocks & Shares ISA without leverage.

The aspirational return target is **10–20% CAGR**, but the primary optimization target is:

> maximize robust risk-adjusted return subject to a 15% maximum drawdown constraint and realistic trading costs.

The system must prefer robustness over headline backtest return.

---

## 2. Investment universe

### 2.1 Eligible assets

Common stocks meeting all of the following:

- Primary US listing
- Price >= $10
- Median 20-day dollar volume >= $500M
- At least 252 trading days of history
- No OTC securities
- No leveraged/inverse ETFs
- No penny stocks
- No instruments that cannot be held in the selected ISA/broker setup

### 2.2 Initial implementation

Start with a **fixed seed universe of 30–50 highly liquid US large-cap names**.

This avoids survivorship-bias complexity during the first engineering phase.

Before any claim of historical performance is made, replace the fixed present-day universe with a **historically point-in-time universe**.

### 2.3 Benchmark

`SPY` is the default market benchmark for regime detection and relative strength.

---

## 3. Rebalance schedule

Default:

- Signal calculation: after Friday US market close
- Rebalance: next US trading session
- Frequency: weekly

Daily calculation is permitted, but portfolio changes occur only when:

- a scheduled rebalance occurs,
- a hard risk rule fires,
- a held asset becomes ineligible.

This intentionally reduces turnover.

---

## 4. Momentum score

For stock `i` at date `t`:

```text
R63  = total return from t-68 to t-5
R126 = total return from t-131 to t-5
R252 = total return from t-257 to t-5
```

The most recent 5 trading days are excluded to reduce short-term reversal contamination.

Standardize each signal cross-sectionally:

```text
Z63  = zscore(R63)
Z126 = zscore(R126)
Z252 = zscore(R252)
```

Base momentum:

```text
M_i = 0.35*Z63 + 0.35*Z126 + 0.30*Z252
```

---

## 5. Trend score

For each stock:

```text
T50  = (Price / SMA50)  - 1
T100 = (Price / SMA100) - 1
T200 = (Price / SMA200) - 1
```

Trend score:

```text
T_i = mean(zscore(T50), zscore(T100), zscore(T200))
```

Default eligibility requirement:

```text
Price > SMA200
```

Optional stricter V2 rule:

```text
SMA50 > SMA100 > SMA200
```

---

## 6. Risk penalties

### 6.1 Realized volatility

```text
vol20_i = stdev(daily_returns, 20) * sqrt(252)
```

Cross-sectional penalty:

```text
V_i = zscore(vol20_i)
```

Higher volatility is worse.

### 6.2 Drawdown

```text
DD63_i = Price / rolling_max(Price, 63) - 1
```

Define:

```text
D_i = zscore(abs(min(DD63_i, 0)))
```

Larger drawdown is worse.

---

## 7. Final deterministic ranking score

Default score:

```text
S_i = 0.65*M_i
    + 0.30*T_i
    - 0.20*V_i
    - 0.15*D_i
```

After calculating `S_i`, rank all eligible stocks descending.

Portfolio candidates are the top-ranked names.

The exact coefficients are **defaults, not optimized truths**.

Allowed parameter search ranges:

```text
Momentum total weight: 0.50–0.80
Trend total weight:    0.15–0.40
Volatility penalty:    0.10–0.30
Drawdown penalty:      0.05–0.25
```

No parameter may be selected solely because it produces the maximum historical CAGR.

---

## 8. Market regime filter

Define:

### 8.1 Long-term trend

```text
market_trend = SPY_close > SPY_SMA200
```

### 8.2 Breadth

For the eligible universe:

```text
breadth = count(Price > SMA200) / eligible_stock_count
```

### 8.3 Market volatility

```text
SPY_vol20 = stdev(SPY daily returns, 20) * sqrt(252)
```

Compare current volatility to the expanding historical percentile.

### 8.4 Regime definitions

#### Risk-on

All:

```text
SPY > SMA200
breadth >= 60%
SPY_vol20 < 80th historical percentile
```

Maximum equity exposure:

```text
100%
```

#### Neutral

Examples:

```text
SPY > SMA200 and breadth between 45% and 60%
```

or:

```text
SPY > SMA200 and volatility >= 80th percentile
```

Maximum equity exposure:

```text
50%
```

#### Risk-off

Either:

```text
SPY <= SMA200 and breadth < 45%
```

or a hard portfolio risk rule has fired.

Maximum equity exposure:

```text
0%
```

The exact regime thresholds must be tested for stability, not optimized narrowly.

---

## 9. Position selection

Default target:

```text
4 positions
```

Maximum:

```text
5 positions
```

Minimum:

```text
0 positions
```

Process:

1. Rank eligible stocks.
2. Apply trend eligibility.
3. If ML is disabled, take highest-ranked names.
4. If ML is enabled, require ML probability threshold.
5. Size positions using volatility-based sizing.
6. Apply concentration caps.
7. Scale portfolio to regime exposure limit.

---

## 10. Position sizing

For stock `i`:

```text
inverse_vol_i = 1 / vol20_i
raw_weight_i = inverse_vol_i / sum(inverse_vol)
```

Then constrain:

```text
10% <= position_weight <= 30%
```

Scale all weights so:

```text
expected portfolio annualized volatility <= 12%
```

and:

```text
sum(weights) <= regime_exposure_limit
```

Any unallocated amount remains cash.

### Small-account simplification

For capital below £3,000, equal-weighting is acceptable if fractional shares are unavailable:

```text
weight = regime_exposure / number_of_positions
```

The backtest must compare equal-weighting against volatility sizing.

---

## 11. Entry rules

Open a new position only when:

- stock is in top `N` by final score,
- stock passes trend requirement,
- spread is acceptable,
- no risk freeze is active,
- portfolio exposure remains within regime limit,
- order value exceeds minimum viable order size,
- if ML enabled: model probability >= threshold.

Default ML threshold:

```text
0.55
```

---

## 12. Exit rules

Exit a position when any of these occurs:

### Ranking exit

```text
stock rank > 2 * target_positions
```

Example:

With 4 target holdings, exit if rank falls below top 8.

### Trend exit

```text
Close < SMA200
```

confirmed at rebalance.

### Replacement exit

A higher-ranked eligible candidate enters the target portfolio.

### Hard loss exit

Emergency risk rule:

```text
loss from entry <= -12%
```

This is not expected to improve ordinary momentum behavior; it exists to limit catastrophic single-name events.

It must be tested both enabled and disabled.

### Portfolio risk exit

Triggered by portfolio-level drawdown rules.

---

## 13. Turnover control

Do not replace a holding merely because rank changes slightly.

Use a rank buffer:

```text
entry_rank <= N
exit_rank > 2N
```

This hysteresis reduces unnecessary turnover.

Optional minimum holding period:

```text
5 trading days
```

except hard-risk exits.

---

## 14. Cash treatment

Cash is an intentional portfolio state.

Do not force full investment.

Expected exposure:

```text
Risk-on:  75–100%
Neutral:  25–50%
Risk-off: 0%
```

---

## 15. Machine-learning layer

ML is introduced only after the deterministic baseline passes validation.

The ML system is a **meta-model**.

It answers:

> Given that the deterministic strategy has generated a candidate trade, what is the probability that the trade will outperform the benchmark over the next 20 trading days?

It does **not** directly forecast next-day price.

### 15.1 Label

For candidate trade at date `t`:

```text
stock_forward_20d = Return(stock, t -> t+20)
benchmark_forward_20d = Return(SPY, t -> t+20)

excess_return = stock_forward_20d - benchmark_forward_20d
```

Binary label:

```text
y = 1 if excess_return > 0
y = 0 otherwise
```

Optional stricter label:

```text
y = 1 if excess_return > transaction_cost_buffer
```

### 15.2 Model

Primary:

```text
LightGBM classifier
```

Baselines:

```text
Logistic Regression
Random Forest
```

Deep learning is prohibited until the above models have been exhausted.

### 15.3 Trade decision

If:

```text
P(y=1) >= 0.55
```

candidate remains eligible.

Otherwise reject it.

Threshold search range:

```text
0.50–0.65
```

Evaluate threshold stability.

### 15.4 ML acceptance rule

ML is retained only if, across out-of-sample periods:

- net Sharpe improves by >= 0.10, or
- max drawdown falls by >= 2 percentage points without materially lowering return, or
- turnover falls materially while preserving return.

If none are true, remove ML.

---

## 16. Strategy invariants

The live system must always satisfy:

```text
gross_exposure <= 100%
short_exposure = 0%
margin_debt = 0
positions <= 5
single_position_weight <= 30%
```

If any invariant fails, trading stops and an alert is emitted.
