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

### Initial historical-data stack

Phase 3 uses `chinobing/historical_sp500_constituents` as the primary dated S&P 500 membership
source from 1996, `unliftedq/index-constitution` for ticker-change and delisting events, and
Tiingo for raw and adjusted daily OHLCV, dividends, and splits. `riazarbi/sp500-scraper` and
historical SPY holdings are independent membership-QA sources. This is the initial point-in-time
route; CRSP/WRDS is not required for initial research validation. It must nevertheless meet the
point-in-time, identity, coverage, reconciliation, and audit requirements in
`PHASE3_HISTORICAL_VALIDATION.md` before it is used as deployment evidence.

The primary membership snapshots establish membership intervals. The index-constitution event
history establishes dated security identity, ticker successor, and delisting treatment. Tiingo
establishes prices and corporate-action inputs. Store immutable, commit-pinned source snapshots
separately from canonical Parquet output, including repository URL, commit SHA, retrieval timestamp,
file hashes, transformation version, source licences, request parameters, and all failed requests.
Do not replace old snapshots or extracts in place.

FMP Basic is a supplemental validation source: use `historical-price-eod/full` for independent
raw-OHLCV/last-bar checks, `dividends` for action checks, and `delisted-companies` for delisting
checks. `profile`, `search-symbol`, `quote`, and `historical-market-capitalization` may enrich or
sanity-check the security master. These responses must never backfill Tiingo, override the pinned
membership/identity sources, or project current metadata into historical eligibility.

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
│   ├── historical_sp500_constituents/
│   │   └── membership_snapshots/
│   ├── index_constitution/
│   │   ├── ticker_changes/
│   │   └── delistings/
│   ├── membership_qa/
│   │   ├── sp500_scraper/
│   │   └── spy_holdings/
│   ├── fmp_validation/
│   │   ├── prices/
│   │   ├── dividends/
│   │   ├── delistings/
│   │   └── security_metadata/
│   └── tiingo/
│       ├── prices/
│       └── corporate_actions/
├── processed/
│   ├── daily_bars.parquet
│   ├── features.parquet
│   ├── universe.parquet
│   └── security_master.parquet
└── metadata/
    └── manifests/
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
- raw-versus-adjusted reconciliation around recorded splits and dividends
- membership-interval gaps/overlaps and ticker-to-security identity conflicts
- constituent-change audit discrepancies

Example:

```text
low <= min(open, close)
high >= max(open, close)
high >= low
```

Failures should quarantine records rather than silently correcting them.
