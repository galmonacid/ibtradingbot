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
