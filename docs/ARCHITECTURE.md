# Implementation Architecture

## 1. Technology stack

Recommended:

```text
Python 3.12+
pandas or Polars
NumPy
DuckDB
PyArrow / Parquet
scikit-learn
LightGBM
vectorbt for research
IBKR API / ib_async for execution
pydantic for configuration/data validation
pytest
ruff
mypy
```

Optional:

```text
MLflow
Optuna
Plotly
FastAPI
```

Do not introduce infrastructure unless it solves a concrete problem.

---

## 2. Logical modules

```text
src/
├── config/
├── data/
│   ├── providers/
│   ├── ingest.py
│   ├── quality.py
│   └── universe.py
├── features/
│   ├── momentum.py
│   ├── trend.py
│   ├── volatility.py
│   └── regime.py
├── strategy/
│   ├── ranker.py
│   ├── selector.py
│   └── signals.py
├── portfolio/
│   ├── sizing.py
│   ├── constraints.py
│   └── rebalance.py
├── ml/
│   ├── labels.py
│   ├── train.py
│   ├── predict.py
│   └── calibration.py
├── backtest/
│   ├── engine.py
│   ├── costs.py
│   └── metrics.py
├── validation/
│   ├── walk_forward.py
│   ├── bootstrap.py
│   └── sensitivity.py
├── broker/
│   ├── base.py
│   └── ibkr.py
├── execution/
│   ├── orders.py
│   ├── reconcile.py
│   └── state_machine.py
├── monitoring/
│   ├── alerts.py
│   ├── health.py
│   └── reports.py
└── cli/
```

---

## 3. Separation of concerns

The following layers must be independent:

```text
data
features
strategy
portfolio construction
broker execution
```

A strategy should produce a target portfolio without knowing how IBKR places an order.

The broker module should execute a target change without knowing why the strategy selected AAPL.

---

## 4. Core interfaces

### Market data provider

```python
class MarketDataProvider:
    def daily_bars(self, symbols, start, end): ...
```

### Strategy

```python
class Strategy:
    def target_scores(self, as_of_date, features): ...
```

### Portfolio constructor

```python
class PortfolioConstructor:
    def build(self, scores, regime, account_state): ...
```

### Broker

```python
class Broker:
    def account_state(self): ...
    def positions(self): ...
    def open_orders(self): ...
    def submit_order(self, order): ...
    def cancel_order(self, order_id): ...
```

Research code and live code should share strategy/portfolio logic.

---

## 5. Reproducibility

Every backtest must record:

```text
git commit hash
configuration hash
data version
universe version
strategy version
ML model version
run timestamp
```

A result without provenance is not an admissible result.

---

## 6. Configuration

Use YAML for human-readable configuration.

All tunable parameters must live in config rather than being hidden in code.

Example:

```text
config/
├── baseline.yaml
├── stress.yaml
├── paper.yaml
└── live.yaml
```

Live configuration should be deliberately conservative.

---

## 7. Scheduling on Mac mini

For V1:

```text
launchd
```

Suggested jobs:

```text
17:00 ET / after market close:
    ingest data
    validate data
    build features
    calculate signals

weekly:
    produce target portfolio
    run reconciliation
    stage/execute rebalance

daily:
    broker reconciliation
    health report
```

Use exchange calendars rather than hard-coded weekdays.

---

## 8. Local persistence

Recommended:

```text
DuckDB:
    analytics / research

SQLite:
    execution state / order state

Parquet:
    immutable historical data
```

For Phase 3, preserve a three-layer historical-data lineage: immutable, commit-pinned snapshots of
`chinobing/historical_sp500_constituents` for primary S&P 500 membership,
`unliftedq/index-constitution` for ticker/delisting events, and `riazarbi/sp500-scraper` plus
historical SPY holdings for QA; immutable Tiingo extracts for bars, dividends, and splits; and
derived canonical security-master, membership-interval, and Parquet datasets. A manifest links the
layers by repository URL/commit SHA, file hashes, retrieval parameters, provider metadata,
transformation version, and data-quality/audit results. Analytics reads only canonical data; it must
not call providers directly.

FMP Basic responses form a supplemental immutable validation layer: historical EOD prices,
dividends, delistings, and security-metadata responses are compared with canonical sources during
ingestion. They may enrich provenance or trigger quarantine, but may not backfill canonical values,
override point-in-time identity, or be queried by analytics directly.

Back up:

```text
execution database
configs
model artifacts
reports
```

Do not rely solely on local logs for broker truth.

---

## 9. Logging

Use structured logs.

Example:

```json
{
  "timestamp": "2026-09-04T21:15:00Z",
  "event": "rebalance_target",
  "symbol": "AAPL",
  "old_weight": 0.0,
  "target_weight": 0.25,
  "strategy_version": "v1.0.0"
}
```

Logs should enable reconstruction of every trading decision.

---

## 10. Testing

Required:

### Unit tests

- return calculations
- moving averages
- ranking
- z-scores
- volatility sizing
- regime classification
- drawdown logic
- order sizing

### Property tests

Examples:

```text
weights never exceed 100%
no negative weights
no more than 5 positions
risk-off produces no new long exposure
```

### Integration tests

- broker sandbox/paper account
- order submission
- partial fill
- rejected order
- reconnect
- reconciliation mismatch

### Regression tests

Freeze several known historical periods and expected signal outputs.

Changes to strategy logic must intentionally update regression snapshots.

---

## 11. CI

GitHub Actions:

```text
on pull request:
    ruff
    mypy
    pytest
```

Backtests should not necessarily run on every commit if data is large.

A smaller deterministic fixture dataset should run in CI.
