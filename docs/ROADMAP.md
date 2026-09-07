# Development Roadmap

## Phase 0 — Repository bootstrap

Deliverables:

- repository structure
- Python environment
- configuration system
- logging
- test framework
- CI
- sample dataset

Exit condition:

```text
clean install
all tests pass
one command runs sample pipeline
```

---

## Phase 1 — Deterministic research baseline

Implement:

- price ingestion
- universe filtering
- features
- momentum ranking
- trend filter
- regime model
- equal-weight portfolio
- realistic costs
- metrics report

Do **not** implement ML yet.

Exit condition:

- reproducible backtest
- benchmark comparison
- no look-ahead detected
- costs included

---

## Phase 2 — Risk and portfolio construction

Implement:

- inverse-vol sizing
- volatility target
- exposure limits
- drawdown circuit breakers
- rank hysteresis
- stress costs

Exit condition:

Deterministic strategy meets or approaches validation gates.

If it fails badly, revisit strategy rather than adding ML.

---

## Phase 3 — Robust historical validation

Implement:

- point-in-time universe
- walk-forward engine
- sensitivity analysis
- bootstrap
- ablation testing

Produce:

```text
research_report.md
```

with all acceptance criteria.

Exit condition:

Mandatory deterministic deployment gates pass.

---

## Phase 4 — IBKR paper execution

Implement:

- broker adapter
- account reconciliation
- order state machine
- marketable limit orders
- idempotent order IDs
- daily reporting
- kill switch

Run in paper mode for at least 60 trading days.

Exit condition:

No unresolved discrepancy between:

```text
intended target
submitted orders
broker fills
final portfolio
```

---

## Phase 5 — £1,000 live deployment

Enable real orders.

Constraints:

```text
max 3–4 positions
no leverage
no manual strategy overrides
hard 15% account drawdown halt
```

Priorities:

1. operational correctness
2. risk control
3. data correctness
4. return

Do not judge alpha from a short live period.

---

## Phase 6 — ML meta-model

Only after deterministic strategy is operational.

Build dataset from historical **candidate trades**, not arbitrary daily stock rows.

Models:

1. Logistic Regression
2. Random Forest
3. LightGBM

Target:

```text
20-day benchmark-relative positive return
```

Use purged chronological validation.

ML must pass the incremental-value rule in `QUANT_SPEC.md`.

If it does not, keep deterministic system.

---

## Phase 7 — £3,000 deployment

Increase only after:

- operational stability,
- at least several months live,
- no serious reconciliation/execution defects,
- drawdown within stress expectations.

Do not increase leverage.

---

## Phase 8 — Second strategy research

Only after V1 is stable.

Potential candidates:

- BTC/ETH spot trend following
- global equity momentum
- defensive ETF rotation
- medium-term mean reversion as a diversifier

The second strategy should ideally have low correlation to V1.

---

# Suggested GitHub issues

## Epic: Data

- [ ] Define point-in-time universe source
- [ ] Implement daily bar ingestion
- [ ] Implement corporate-action handling
- [ ] Add data-quality suite
- [ ] Store processed data in Parquet

## Epic: Strategy

- [ ] Momentum features
- [ ] Trend features
- [ ] Risk penalties
- [ ] Ranking engine
- [ ] Regime classifier
- [ ] Rank-buffer exits

## Epic: Backtest

- [ ] Event timing
- [ ] Transaction cost model
- [ ] Portfolio accounting
- [ ] Metrics
- [ ] Benchmark comparison
- [ ] Sensitivity tests
- [ ] Bootstrap
- [ ] Walk-forward validation

## Epic: Risk

- [ ] Volatility sizing
- [ ] Exposure constraints
- [ ] Soft drawdown control
- [ ] Hard drawdown kill switch
- [ ] Position concentration limits

## Epic: Broker

- [ ] IBKR paper connection
- [ ] Account-state fetch
- [ ] Position fetch
- [ ] Marketable-limit orders
- [ ] Idempotent execution
- [ ] Partial-fill handling
- [ ] Daily reconciliation

## Epic: ML

- [ ] Candidate-trade dataset
- [ ] Label generation
- [ ] Logistic baseline
- [ ] LightGBM
- [ ] Probability calibration
- [ ] Purged validation
- [ ] Incremental-value report
