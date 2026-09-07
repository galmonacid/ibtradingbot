# Data and Feature Specification

## 1. Data requirements

Minimum daily OHLCV data:

```text
date
symbol
open
high
low
close
adjusted_close
volume
```

Corporate actions:

```text
splits
cash dividends
symbol changes
delistings
```

The research pipeline should use adjusted historical prices where appropriate, while the execution engine must use live/raw tradable prices.

---

## 2. Point-in-time requirements

Backtests must not use future information.

Examples of forbidden leakage:

- Current S&P 500 constituents applied unchanged to 2008
- Final adjusted fundamentals that were not known at the time
- Revised macroeconomic values
- Forward-filled delisted stocks as if still tradable
- Features calculated using future closes

For V0 engineering, a fixed universe is acceptable only for code validation.

For performance claims, a point-in-time universe is mandatory.

---

## 3. Required price-derived features

For every stock:

### Returns

```text
ret_1d
ret_5d
ret_21d
ret_63d
ret_126d
ret_252d
```

Momentum features use a 5-day skip:

```text
ret_63_skip5
ret_126_skip5
ret_252_skip5
```

### Relative returns

```text
ret_stock_63 - ret_SPY_63
ret_stock_126 - ret_SPY_126
ret_stock_252 - ret_SPY_252
```

### Trend

```text
price / SMA20 - 1
price / SMA50 - 1
price / SMA100 - 1
price / SMA200 - 1
SMA50 / SMA200 - 1
```

### Volatility

```text
vol_10d
vol_20d
vol_63d
```

Annualized:

```text
std(daily_returns, window) * sqrt(252)
```

### Drawdown

```text
drawdown_21d
drawdown_63d
drawdown_252d
```

### Volume/liquidity

```text
median_dollar_volume_20d
volume / median_volume_20d
turnover_proxy
```

### Gap/range

```text
overnight_gap
true_range
ATR14 / close
```

---

## 4. Market/regime features

From SPY:

```text
SPY_ret_5d
SPY_ret_21d
SPY_ret_63d
SPY_close / SMA50 - 1
SPY_close / SMA200 - 1
SPY_vol20
SPY_drawdown_63
SPY_drawdown_252
```

Breadth:

```text
pct_universe_above_SMA50
pct_universe_above_SMA200
pct_universe_positive_63d
pct_universe_positive_126d
```

Cross-sectional dispersion:

```text
std(stock_returns_21d)
std(stock_returns_63d)
```

---

## 5. Optional V2 features

Only add after baseline stability:

- Sector relative strength
- Beta to SPY
- Rolling correlation to SPY
- Idiosyncratic volatility
- Earnings-event proximity
- VIX level and term structure
- Interest-rate regime
- Credit-spread proxy

Do not add features simply because they improve one backtest period.

---

## 6. Feature normalization

For ranking:

```text
cross-sectional z-score by rebalance date
```

Winsorize at:

```text
1st and 99th percentile
```

For ML:

- fit scalers on training data only,
- never fit transformations on the full dataset,
- tree models may use mostly raw/engineered features.

---

## 7. Missing data

Rules:

- Do not forward-fill returns.
- Do not fabricate unavailable history.
- Exclude symbol from ranking if a mandatory feature is missing.
- Record every exclusion and reason.

---

## 8. Data storage

Recommended local format:

```text
data/
├── raw/
│   ├── prices/
│   └── corporate_actions/
├── processed/
│   ├── daily_bars.parquet
│   ├── features.parquet
│   └── universe.parquet
└── metadata/
```

Preferred analytics store:

```text
Parquet + DuckDB
```

---

## 9. Data quality checks

Every ingestion run must test:

- duplicate `(date, symbol)` rows
- non-monotonic dates
- negative prices
- zero/negative adjusted prices
- impossible OHLC relationships
- suspicious one-day moves
- missing volume
- stale prices
- split-related discontinuities

Example:

```text
low <= min(open, close)
high >= max(open, close)
high >= low
```

Failures should quarantine records rather than silently correcting them.
