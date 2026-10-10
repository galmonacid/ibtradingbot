# Architecture and migration

2026-10-10: [Fundamental feature engineering](FUNDAMENTAL_FEATURE_AUDIT.md) adds four causal issuer-level ratio primitives and a coverage CLI. They are separate from the old R3 feature schema and have not entered a model or canonical dataset. Historical security joins and full-universe enriched readiness remain unverified.

## Existing implementation

`src/data` provides source/canonical/PIT/FX tooling. `src/features`, `src/strategy` and `src/portfolio` retain V1/V2 calculations. `src/backtest/v2.py` and `v2_execution.py` retain legacy accounting. R3.1 supplies the separate economics feasibility audit; R3.2 supplies typed registration, causal materialization, purged folds and exact one-year accounting. R3.3 adds the bounded local-CPU learner and common development simulator. Next-cycle Step 3 adds `src/config/r3_step3.py`, `src/research/r3_source_feasibility.py` and `src/cli/r3_step3_feasibility.py` for bounded, immutable source auditing only. The post-stop `r3_post_step3` config/research/CLI path verifies evidence and emits remediation/governance records; it imports no learning, strategy, portfolio, simulation or backtest module. Neither gate produces a learner, score or Step 4 register. Generated source responses and reports are ignored development evidence. No broker/live package or qualification wrapper exists.

Installed project requirements specify Python >=3.12 and PyYAML, with optional historical-data, development and `research` extras. The research extra bounds NumPy to 2.x and scikit-learn to 1.7–1.8; the evidence run used NumPy 2.5.3 and scikit-learn 1.8.0. Existing public-data extras remain exploratory and do not establish admissible data.

## R3 technology decision

Keep Python, the event-driven accounting approach, YAML configuration and immutable Parquet/manifests. R3.3 uses NumPy and scikit-learn [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html) plus [HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) through the separate research extra. No LightGBM dependency or broader model search was added.

Use local CPU training and files; no GPU, hosted inference, vector database, MLflow, Optuna, web service or alternate backtest engine. Complexity must earn its cost. Add a database only when a later execution-state requirement warrants one.

## Proposed boundaries, not existing interfaces

- Data layer: immutable source evidence, security identities and as-of observations.
- Feature/label layer: session-aware rows, timestamps, maturation and exclusions.
- Learning layer: training-only transforms, versioned fitting, deterministic inference and stale-model checks.
- Strategy layer: scores and ranked candidates only; no broker code.
- Portfolio layer: actual holdings, cost feasibility, selection, sizing and hard risk controls.
- Backtest layer: raw prices, actions, cash, fees, fills, continuous account state and NAV.
- Validation layer: immutable trial register, splits, one-year outcomes, paired comparisons, gates and provenance.
- Future execution layer: durable intents and actual broker reconciliation, after qualification.

Do not start implementation by creating empty module trees. Establish the smallest typed interfaces in tested changes, with candidate scores independent of the broker and a common event ledger for all candidates.

## Migration contract

Existing configs, commands and their semantics remain V1/V2 controls. The separate `r3.1-feasibility-v1` config and entry point fix initial capital at £3,000 and audit the $20m capacity screen and cost-derived order floor without changing the legacy engine. R3.2's `r3.2-contract-v1` configuration and one-year evaluator are separate additions. R3.3 owns learned scores and matured-label training, but cannot start until the R3.2 evidence blockers are resolved. Existing validators and cost guards cannot enact these changes by editing prose or flipping `ml.enabled`.

Preserve legacy tests. Reuse pure primitives after checking their assumptions; do not mutate the old engine to make the new comparison easier. Add R3 acceptance and objective gates before any path can claim R3 readiness. The legacy paper-readiness field must never authorize R3 by itself.

Old reports bind Markdown hashes. Rewriting specifications intentionally changes those identities. Reproduce at the original Git revision in an isolated checkout with original spec files and unchanged artifact manifests. Do not replace old hashes, re-sign evidence or supply the new R3 spec to the V2 command as if it described that run.

## Provenance and verification

The bounded identity-remediation utility `src/data/r3_identity.py` extracts source-bound inline SEC cover observations. `python -m src.cli.r3_identity_audit` verifies local document/acceptance hashes and writes an immutable offline audit. It neither modifies canonical security identities nor supplies features to training. See [source remediation](SOURCE_REMEDIATION.md) for its supported cases and limitations.

Every run binds Git commit and actual tree, configuration, raw/canonical/universe/calendar/FX hashes, tariff/cost budget, feature and label versions, preprocessing, split definitions, model artifact hash, dependency environment, seed and UTC timestamp. Exact row ordering and tie-breaking must be deterministic. Keep datasets, fitted models, run reports and credentials ignored.

Tests must establish prefix invariance, label maturity/purging, no random leakage, training-only preprocessing, deterministic fit/inference, whole-account cost conservation, objective endpoints, risk invariants and reproducible reports. Run targeted pytest first, then the full suite, Ruff, strict mypy and package build for implementation changes. Documentation-only checks also verify links, retired references and clean diffs. Never present earlier test counts as a current run.
