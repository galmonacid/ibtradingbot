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

## Suggested initial command flow

```bash
python -m src.data.download
python -m src.features.build
python -m src.backtest.run --config config.example.yaml
python -m src.validation.walk_forward --config config.example.yaml
python -m src.paper.run
```

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
