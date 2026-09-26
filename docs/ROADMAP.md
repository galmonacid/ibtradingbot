# Development Roadmap

## Current status — 2026-09-22

Phases 1–2 delivered engineering baselines. Phase 3 delivered certified historical data
and native validation, but V1 failed the performance exit gates. Remain in Phase 3.
The [V2 strategy specification](QUANT_SPEC.md) has a completed, independently reviewed
development implementation. Its inspected-history matrix failed return, drawdown,
robustness and sample-size gates, so the fixed candidate is rejected for qualification.
It does not permit paper trading. See GOAL-PHASE3-V2.md for evidence. Preserve V1 and
its reports as controls.

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

- a versioned open-source membership + Tiingo historical-data producer:
  `chinobing/historical_sp500_constituents` is the primary 1996-present membership
  source; `unliftedq/index-constitution` supplies ticker-change and delisting
  events; `riazarbi/sp500-scraper` Wikipedia snapshots and its historical iShares IVV
  holdings provide independent membership QA; Tiingo supplies raw/adjusted OHLCV,
  dividends, and splits. FMP inputs, when supplied, are optional secondary QA.
- a point-in-time S&P 500 universe and security master derived from that
  producer, using a documented 400-name minimum rather than assuming every source snapshot or
  provider has exactly 500 usable names
- provider-to-canonical Parquet lineage, quality checks, and a 50–100-event
  random constituent-change audit against an independent source
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

The version-pinned open-source membership/security-master + Tiingo dataset has passed
its completeness, identity, corporate-action, and independent-audit checks, and mandatory
deterministic deployment gates pass. Licensed CRSP/WRDS data is not a prerequisite for this
phase. A later rerun on Norgate, Sharadar, CRSP/Compustat, or another independent dataset
remains a recommended confirmation before increasing capital, not a substitute for these controls.

---

## Phase 3 redesign — deterministic V2 research

Implement the candidate in [QUANT_SPEC.md](QUANT_SPEC.md) through small, versioned changes:

- reproduce the V1 anchor and add the missing cost/exposure/halt attribution;
- add the fixed monthly momentum candidate, selection from actual fills and simple regime;
- add equal-weight risk scaling and order bands while preserving all hard account controls;
- establish GBP and £1,000/£3,000 account feasibility, including FX, fees and share rounding;
- bind the candidate and its diagnostics to native provenance and execution certification;
- publish development results, then reject it or freeze it before untouched evaluation.

Previously inspected history is development evidence. The untouched-period and fixed
sensitivity contracts are in QUANT_SPEC; the separate V2 development command and config are documented in
PHASE3_V2_IMPLEMENTATION.md. A historical rerun cannot by itself reopen Phase 4. Exit requires unchanged mandatory
gates plus V2's small-account, robustness and independent-position-episode evidence.
Do not relax thresholds, disable the account halt, or add ML to force a pass.

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

- [ ] Acquire and pin `chinobing/historical_sp500_constituents` membership snapshots
- [ ] Build versioned point-in-time intervals from the primary membership source
- [ ] Ingest `unliftedq/index-constitution` ticker-change/delisting events into the security master
- [ ] Implement Tiingo raw/adjusted daily-bar, dividend, and split ingestion
- [ ] Optionally ingest immutable FMP validation extracts for raw-price, dividend, delisting,
      and security-metadata cross-checks; never use them to backfill canonical history
- [ ] Cross-check 50–100 seeded constituent changes against `riazarbi/sp500-scraper`
      Wikipedia and iShares IVV histories; quarantine unresolved intervals
- [ ] Reconcile raw/adjusted bars with recorded corporate actions and quarantine failures
- [ ] Add data-quality suite
- [ ] Store immutable provider extracts and canonical Parquet data with manifests

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
