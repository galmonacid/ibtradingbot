# Small-account equity research

## Objective and current decision

Target **more than 10% total return in GBP within one year**, after trading and recurring operating costs, from initial capital of **£3,000**. The user confirmed this horizon and starting capital on 2026-09-26. With no contributions or withdrawals, net profit must exceed £300 and terminal wealth must exceed £3,300. This is not a multi-year CAGR target, a guaranteed annual gain, or financial advice.

**Status: research only; no candidate is viable for advancement.** V1 and V2 remain rejected controls. R3.3 implemented the bounded momentum/Ridge/histogram-gradient-boosting comparison on the nine R3.2 development folds. Momentum was strongest, but its median non-overlapping one-year return was 6.83% and only 4/9 cohorts strictly exceeded 10%. Every learned configuration had negative paired median uplift versus momentum and failed the promotion rule. Some tree and overlapping-cohort accounts also failed closed on unsupported split residuals or missing held valuations. R3.3 research acceptance and qualification are false; R3.4 is not permitted without a new explicit research decision. No broker integration or deployment exists.

The controlled comparison is complete and did not support ML promotion or the product objective. No new tuning round is implicit. The next permitted step is to review and close the failed R3.3 experiment, or explicitly register a genuinely new research question without reinterpreting these inspected results.

The product must be able to conclude that active trading is unsuitable at £3,000. It must not manufacture a pass by increasing risk, changing the objective, or repeatedly tuning on the same history.

## Read in this order

1. [Strategy review](docs/STRATEGY_REVIEW.md): failure evidence, economics, alternatives and decisions.
2. [Execution plan](docs/ROADMAP.md): ordered deliverables, exit conditions and stop rules.
3. [Strategy specification](docs/QUANT_SPEC.md): proposed research candidates and portfolio policy.
4. [Data and features](docs/DATA_AND_FEATURES.md) and [validation](docs/BACKTEST_AND_VALIDATION.md): causal training and honest evaluation.
5. [Architecture](docs/ARCHITECTURE.md), [risk](docs/RISK_AND_EXECUTION.md), and [legacy evidence](docs/LEGACY_EVIDENCE.md).

## What exists today

Python 3.12+, deterministic V1/V2 engines, point-in-time data assembly, causal accounting, risk controls, provenance and validation tooling exist. Existing YAML files and CLI commands still implement those rejected historical candidates. `ml.enabled: false` remains correct; setting it true does not create a model.

The new research version is called **R3**. R3.1 implements the economics audit; R3.2 implements registration, causal feature/label materialization, purged annual-step folds and exact one-year accounting. R3.3 adds `config.r3-development.yaml`, deterministic training-only Ridge scaling, shallow scikit-learn histogram gradient boosting, quarterly causal refits, a shared raw-share GBP simulator and a six-trial development report through `python -m src.cli.r3_development`. Generated datasets, models and reports remain ignored, local, development-only evidence. Existing legacy validators cannot qualify R3. All paper/live execution remains blocked.

## Supported local commands

Install into a Python 3.12+ virtual environment:

```bash
python -m pip install -e '.[dev,historical-data,research]'
python -m src.cli.sample_pipeline --config config.example.yaml
python -m src.cli.v2_validation --help
python -m src.cli.r3_feasibility --help
python -m src.cli.r3_contract --help
python -m src.cli.r3_evidence --help
python -m src.cli.r3_dataset --help
python -m src.cli.r3_development --help
pytest
ruff check .
mypy src
python -m build
```

The sample pipeline is an engineering fixture, not investment evidence. R3 development may use available local, manifest-bound inputs with absent or unclear licences when their provenance, access terms and no-redistribution limitations are recorded. Such inputs cannot establish qualification. [Legacy evidence](docs/LEGACY_EVIDENCE.md) explains reproducing the old revision; never bind today's replacement specifications to an old report and call it an exact reproduction. R3.3 outputs are failed development evidence, not fresh or qualification results.

## Scope of this reset

All 20 original tracked Markdown files were reviewed and either rewritten or consolidated. Old phase instructions, goal logs, the duplicate V1 specification and the synthetic root performance report were retired. [The evidence register](docs/LEGACY_EVIDENCE.md) preserves the source revision, results and artifact hashes. Ignored local reports, datasets, vendor checkouts and environment files are immutable evidence or dependencies, not project instructions; they were not overwritten.

The hard constraints remain long-only, no margin/leverage/shorting/derivatives, at most five stocks, at most 30% per stock, gross exposure at most 100%, the configured cash buffer, and a permanent 15% account drawdown halt pending human review. That halt cannot guarantee a 15% loss ceiling.
