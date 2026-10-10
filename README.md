# Small-account equity research

## Objective and current decision

Target **more than 10% total return in GBP within one year**, after trading and recurring operating costs, from initial capital of **£3,000**. The user confirmed this horizon and starting capital on 2026-09-26. With no contributions or withdrawals, net profit must exceed £300 and terminal wealth must exceed £3,300. This is not a multi-year CAGR target, a guaranteed annual gain, or financial advice.

**Status: research only; no candidate is viable for advancement.** V1 and V2 remain rejected controls. The preserved R3.3 result was found to use future-label-dependent scoring eligibility. The corrected six-control run is now complete: momentum's valid-account median non-overlapping return was -1.98%, its overall target attainment was 3/9, and one annual account was invalid. Other candidates had two to four invalid annual accounts. Every learned configuration failed promotion. These are inspected development results, not fresh evidence or proof of the objective. Qualification is false; no broker integration or deployment exists.

Steps 1–3 of the [next research cycle brief](docs/NEXT_RESEARCH_CYCLE.md) are complete. Step 3 stopped before registration: its bounded SEC audit found causal sampled facts only from 2009-07-23, so 0/9 frozen 8/2/1 folds have the required complete enriched history from 1999. The post-stop immutable decision package defines three governance options and the evidence required before a future protocol-amendment decision could even be considered. It changes no protocol, feature source contract, candidate budget, portfolio or risk rule. Stopping requires no new authority; remediation and any amendment proposal require a separate explicit user decision. No Step 4 richer-feature/XGBoost experiment is registered or authorized.

The product must be able to conclude that active trading is unsuitable at £3,000. It must not manufacture a pass by increasing risk, changing the objective, or repeatedly tuning on the same history.

On 2026-10-04 the user requested continued work. A [bounded source-remediation audit](docs/SOURCE_REMEDIATION.md) now extracts source-bound SEC cover observations and records primary evidence for three identity cases plus a possible historical SIC source. Full identity/history/cost remediation remains incomplete; Step 4 is not ready. This continuation authorizes bounded public-source remediation, superseding the earlier requirement to obtain that authority again.

On 2026-10-07 the user approved the [later-period design](docs/LATER_PERIOD_DESIGN.md). Its separate configuration and offline planner retain initial 8/2/1 windows and verify six calendar-complete folds from a 2010 start. Existing price-feature coverage is measured; full-universe enriched data readiness remains unproven. This approval supersedes the earlier pending period choice without reopening old experiments.

The user has requested completion of the remaining R3 work. The [current completion record](docs/R3_COMPLETION_PROGRESS.md) documents the full 793-identity universe audit, public-source discovery, pending acquisition needs and the unaltered forward-evidence gates. Offline continuation is authorized; R3 is not complete and no new model has been fitted.

Four issuer-level fundamental ratios and a coverage CLI are now implemented; the [feature audit](docs/FUNDAMENTAL_FEATURE_AUDIT.md) records coverage across 19 issuers and the remaining historical-join gates. These features have not entered a model experiment.

R3 continuation is currently **blocked on historical-data acquisition and dated identity evidence**. The [blocking review](docs/R3_COMPLETION_PROGRESS.md#blocking-review--2026-10-10) records the required input and all remaining roadmap gates. R3 is not complete.

## Read in this order

1. [Strategy review](docs/STRATEGY_REVIEW.md): failure evidence, economics, alternatives and decisions.
2. [Execution plan](docs/ROADMAP.md): ordered deliverables, exit conditions and stop rules.
3. [Strategy specification](docs/QUANT_SPEC.md): proposed research candidates and portfolio policy.
4. [Data and features](docs/DATA_AND_FEATURES.md) and [validation](docs/BACKTEST_AND_VALIDATION.md): causal training and honest evaluation.
5. [Architecture](docs/ARCHITECTURE.md), [risk](docs/RISK_AND_EXECUTION.md), and [legacy evidence](docs/LEGACY_EVIDENCE.md).

## What exists today

Python 3.12+, deterministic V1/V2 engines, point-in-time data assembly, causal accounting, risk controls, provenance and validation tooling exist. Existing YAML files and CLI commands still implement those rejected historical candidates. `ml.enabled: false` remains correct; setting it true does not create a model.

The new research version is called **R3**. R3.1 implements the economics audit; R3.2 implements registration, causal feature/label materialization, purged annual-step folds and exact one-year accounting. R3.3 adds `config.r3-development.yaml`, deterministic training-only Ridge scaling, shallow scikit-learn histogram gradient boosting, quarterly causal refits, a shared raw-share GBP simulator and a six-trial development report through `python -m src.cli.r3_development`. Step 3 adds source-feasibility tooling through `python -m src.cli.r3_step3_feasibility` but deliberately creates only a failure register. The post-stop governance package is produced by `python -m src.cli.r3_post_step3_decision`; it verifies evidence and writes decision records only. Generated datasets, models and reports remain ignored, local, development-only evidence. Existing legacy validators cannot qualify R3. All paper/live execution remains blocked.

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
python -m src.cli.r3_step3_feasibility --help
python -m src.cli.r3_post_step3_decision --help
python -m src.cli.r3_identity_audit --help
pytest
ruff check .
mypy src
python -m build
```

The sample pipeline is an engineering fixture, not investment evidence. R3 development may use available local, manifest-bound inputs with absent or unclear licences when their provenance, access terms and no-redistribution limitations are recorded. Such inputs cannot establish qualification. [Legacy evidence](docs/LEGACY_EVIDENCE.md) explains reproducing the old revision; never bind today's replacement specifications to an old report and call it an exact reproduction. R3.3 outputs are failed development evidence, not fresh or qualification results.

## Scope of this reset

All 20 original tracked Markdown files were reviewed and either rewritten or consolidated. Old phase instructions, goal logs, the duplicate V1 specification and the synthetic root performance report were retired. [The evidence register](docs/LEGACY_EVIDENCE.md) preserves the source revision, results and artifact hashes. Ignored local reports, datasets, vendor checkouts and environment files are immutable evidence or dependencies, not project instructions; they were not overwritten.

The hard constraints remain long-only, no margin/leverage/shorting/derivatives, at most five stocks, at most 30% per stock, gross exposure at most 100%, the configured cash buffer, and a permanent 15% account drawdown halt pending human review. That halt cannot guarantee a 15% loss ceiling.

## Local Tiingo credentials

When running acquisition from the repository root, `python -m src.cli.historical_producer` automatically reads `config/credentials.local.toml` if `TIINGO_API_TOKEN` (or the variable named by `--token-environment`) is empty. Add your token locally:

```toml
[tiingo]
api_token = "YOUR_TOKEN"
```

The file is ignored by Git and stays separate from versioned research configuration and evidence manifests. An environment token takes precedence. Use `--credentials-file /absolute/path/to/credentials.local.toml` when running from another directory. This stores the token for future acquisition commands; it does not export it globally or start any downloads.
