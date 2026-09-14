# Momentum ML Trading Bot

A research-first, long-only algorithmic trading system for liquid US equities, designed for a UK retail investor starting with approximately £1,000–£3,000.

The initial goal is **not** to maximize raw return. The goal is to build a robust, automated system that can plausibly target a **10–20% annual return over a full market cycle** while keeping drawdowns, turnover, implementation risk, and trading costs under control.

> This repository is a research and engineering project, not a promise of returns or financial advice.

## Core design

- **Broker/account:** Interactive Brokers UK Stocks & Shares ISA
- **Asset class:** Highly liquid US large-cap equities
- **Direction:** Long-only
- **Style:** Medium-term cross-sectional momentum
- **Holding period:** Typically 10–40 trading days
- **Portfolio size:** 3–5 concurrent positions
- **Rebalance:** Weekly by default
- **Risk control:** Market regime filter + volatility-based position sizing
- **ML role:** Meta-model / trade filter, not direct price prediction
- **Primary ML model:** LightGBM
- **Implementation:** Python
- **Execution:** IBKR API / IB Gateway
- **Hosting:** Mac mini initially
- **Leverage:** None
- **Shorting:** None
- **Derivatives:** None

## Development philosophy

The project must prove value in stages:

1. Deterministic momentum baseline
2. Robust historical backtest
3. Walk-forward validation
4. Paper trading
5. Small-capital live trading
6. ML meta-model
7. Only then consider additional strategies

If the simple baseline cannot survive realistic costs and out-of-sample testing, ML should not be added.

## Repository layout

```text
.
├── README.md
├── config.example.yaml
├── docs/
│   ├── QUANT_SPEC.md
│   ├── DATA_AND_FEATURES.md
│   ├── BACKTEST_AND_VALIDATION.md
│   ├── RISK_AND_EXECUTION.md
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md
├── src/
│   └── ...
└── tests/
    └── ...
```

## Success criteria

The strategy is considered deployable only if it meets all mandatory gates defined in `docs/BACKTEST_AND_VALIDATION.md`.

At minimum:

- Positive out-of-sample CAGR
- Out-of-sample Sharpe >= 0.8
- Maximum drawdown <= 15%
- Net performance remains acceptable after fees/slippage assumptions
- No single stock, year, or market regime explains most of the result
- Paper-trading behavior matches simulated behavior
- Live risk controls are tested independently

## Future roadmap command shape

The following illustrates the intended later-stage module boundaries. These
commands are not implemented in Phase 0 or Phase 1; use the supported commands
below instead.

```bash
python -m src.data.download
python -m src.features.build
python -m src.backtest.run --config config.example.yaml
python -m src.validation.walk_forward --config config.example.yaml
python -m src.paper.run
```

## Phase 0 bootstrap

Phase 0 intentionally provides only safe local validation infrastructure. It
does not download data, generate signals, run a backtest, contact Interactive
Brokers, or place an order.

With Python 3.12 or newer, install the project and its development tools:

```bash
python -m pip install -e ".[dev]"
```

Run the version-controlled sample fixture pipeline:

```bash
momentum-sample-pipeline --config config.example.yaml
```

Equivalent module command:

```bash
python -m src.cli.sample_pipeline --config config.example.yaml
```

The command validates the YAML safety envelope and the local sample daily-bar
CSV, writes a JSON summary to standard output, and writes structured JSON logs
to standard error. The fixture is for engineering validation only; it cannot
be used to make performance or investment claims.

Quality checks:

```bash
pytest
ruff check .
mypy src
python -m build
```

## Phase 3 trusted historical producer

Phase 3 provides separate acquisition and offline trust boundaries. Acquire immutable Tiingo
extracts with `momentum-historical-producer`; acquire FMP extracts through the typed
`src.data.fmp` boundary; then run `momentum-historical-build --help` for the explicit pinned-source
inputs required to produce canonical Parquet and content-bound producer evidence. The offline
build command re-verifies source manifests and raw hashes, derives primary constituent changes,
performs the independent audit, checks Tiingo/FMP agreement, and runs semantic and execution
audits. It never contacts a broker or places an order.

The build output is not itself a performance claim. Phase 3 remains incomplete until the exact
licensed source snapshots are approved, the resulting real dataset is run through the native
walk-forward/backtest path, and every mandatory gate passes in `research_report.md`.

## Phase 1 deterministic research baseline

Phase 1 is a local, deterministic engineering baseline. It ingests canonical
daily OHLCV data, applies versioned fixed-universe eligibility rules, builds the
required trailing features, ranks trend-eligible stocks, classifies the market
regime, constructs equal-weight targets, and simulates the next available
session's adjusted open with commission, slippage, and FX friction.

Run the checked-in synthetic fixture:

```bash
momentum-research-pipeline \
  --config config.example.yaml \
  --data data/sample/research_daily_bars.csv \
  --universe data/sample/seed_universe.csv \
  --calendar data/sample/us_sessions.csv \
  --corporate-actions data/sample/corporate_actions.csv
```

The command prints one JSON report containing provenance, weekly decisions,
executed trades, daily equity, costs, all required performance metrics, SPY and
cash references, and benchmark-relative metrics. It performs no download,
broker connection, or order submission. Supply a timezone-aware
`--run-timestamp` to make the complete report byte-reproducible for regression
checks; without it, economic outputs are deterministic but the recorded run
time changes.

The fixture is synthetic and the seed universe is not point-in-time. Its output
is strictly for engineering validation—not a historical performance claim,
financial advice, or evidence of readiness for paper or live trading. See
`docs/PHASE1_BASELINE.md` for exact conventions and deferred scope.

## Phase 2 risk and portfolio construction

The same `momentum-research-pipeline` command now runs the Phase 2 engineering
baseline. Weekly selection uses a top-N entry / 2N exit rank buffer, then sizes
the retained candidates by inverse 20-day volatility. A trailing, strictly
as-of 20-session covariance estimate scales exposure down when necessary to
keep expected annualized portfolio volatility at or below the configured 12%
target. Regime, cash, concentration, long-only, and five-position limits remain
hard constraints.

The simulator tracks close-marked high-water equity. A 10% drawdown reduces the
position cap by half and prevents an exposure increase. A 15% drawdown schedules
liquidation for the next safely executable session and permanently latches the
research run in risk-review state; it never automatically re-enables entries.
The JSON report includes auditable selection/sizing details, risk transitions,
an equal-weight comparison, and a stressed-cost run using 10 bps slippage and
twice the normal commission.

These comparisons use the checked-in synthetic fixed-universe fixture and are
explicitly inadmissible as deployment evidence. Point-in-time data and robust
historical validation remain Phase 3 work. See `docs/PHASE2_RISK_PORTFOLIO.md`
for the exact deterministic conventions.

## Phase 3 robust historical validation

Phase 3 provides strict point-in-time membership intervals, expanding chronological
walk-forward folds, validation-only stable-plateau parameter selection, exact OOS stitching,
seeded block bootstrap, like-for-like full-minus-one ablations, mandatory deployment gates,
and deterministic JSON/Markdown reporting.

The artifact-driven command is:

```bash
momentum-validation-pipeline \
  --artifact validation-artifact.json \
  --json-output validation-report.json \
  --markdown-output research_report.md
```

The artifact must contain verified sessions and coverage horizon, explicit PIT/data
admissibility fields, configured grid/candidates, fold-specific validation scores and
selected-parameter test returns, stressed returns and regimes, dated realized trades,
dated ablation returns, complete provenance, and benchmark metrics. Mandatory gates are derived
from those observations rather than accepted as caller-supplied summaries. Missing or
inconsistent evidence fails closed. See
`docs/PHASE3_HISTORICAL_VALIDATION.md` for conventions.

The repository does not yet contain its planned 1996-present point-in-time dataset. The checked-in
engineering fixture cannot make deployment gates pass, and Phase 4 must not begin from synthetic or
fixed-universe results. Phase 3's intended data producer uses
[`chinobing/historical_sp500_constituents`](https://github.com/chinobing/historical_sp500_constituents)
as primary membership, [`unliftedq/index-constitution`](https://github.com/unliftedq/index-constitution)
for ticker changes and delistings, and [`riazarbi/sp500-scraper`](https://github.com/riazarbi/sp500-scraper)
plus historical SPY holdings for QA. Tiingo raw/adjusted OHLCV, dividends, and splits then build
canonical Parquet data. Available FMP Basic price, dividend, delisting, and security-metadata
endpoints are retained as independent validation evidence only; they never backfill canonical data
or alter membership/identity history. The producer must pin source commits, retain source manifests,
reconcile corporate actions, and independently audit 50–100 constituent changes before it can be
deployment evidence. CRSP/WRDS is not required for this initial route.

The producer foundation now verifies commit-pinned source manifests, parses strict membership
and identity-event inputs, preserves stable identities across ticker changes/reuse, performs
seeded independent change audits, acquires immutable resumable Tiingo extracts, transforms
verified responses, certifies coverage/actions/delistings fail-closed, and writes explicit
canonical Parquet schemas. Install its optional dependency and inspect the acquisition command:

```bash
python -m pip install '.[historical-data]'
momentum-historical-producer --help
```

The command consumes a JSON request plan containing only `security_id`, `provider_symbol`,
`start`, and `end`; it reads the token from `TIINGO_API_TOKEN` (or a named environment variable),
never from the plan or output manifest. All outputs remain deployment-inadmissible until the
offline semantic build, independent 50–100-event audit, historical backtest, and execution/cost
audit have all passed in-process. The repository intentionally does not contain credentials or
licensed/provider extracts.

Source identity is currently unresolved: the documented
`chinobing/historical_sp500_constituents` repository could not be verified, while the described
1996-present file appears under `fja05680/sp500`. Do not substitute one silently; pin the approved
primary repository, commit, licence, and file before treating a real run as evidence. See
`docs/PHASE3_HISTORICAL_VALIDATION.md` and `docs/DATA_AND_FEATURES.md` for the full contract.

### Retired public reconstructed research mode

For exploratory research, the optional `pitindex` extra can export a reproducible public
S&P 500 membership reconstruction (available from 2005) into the canonical Phase 3 interval
format:

```bash
python -m pip install '.[public-data]'
momentum-public-reconstructed \
  --output-directory data/local/public_reconstructed \
  --start 2007-01-01 \
  --end 2026-09-11
```

This writes dated membership, heuristic security metadata, and a manifest with hashes and
known limitations. To acquire a public Yahoo daily-bar snapshot for the exported membership
union, run:

```bash
momentum-public-daily-prices \
  --membership data/local/public_reconstructed/pitindex_sp500_membership.csv \
  --membership-manifest data/local/public_reconstructed/pitindex_sp500_manifest.json \
  --output-directory data/local/public_prices \
  --start 2007-01-01 \
  --end 2026-07-13
```

It writes canonical OHLCV CSV plus a manifest of every fetched and failed symbol; a failure is
never silently omitted. Run `momentum-research-pipeline` with the exported membership,
security-master, and bars files. Set `universe.source: public_reconstructed` in a local config
copy.

This retired fallback is permanently marked `deployment_admissible: false` and
`paper_execution_permitted: false`: public membership reconstruction does not supply complete
delisting, corporate-action, ticker-identity, historical eligibility, or bar-coverage evidence.
It is useful to challenge the strategy, but is not the Phase 3 data plan and cannot authorize
Phase 4 paper orders.

## Non-goals for V1

- Intraday trading
- Options
- Futures
- CFDs
- Spread betting
- Crypto derivatives
- High-frequency trading
- Reinforcement learning
- Deep neural networks
- News/sentiment trading
- Leverage
