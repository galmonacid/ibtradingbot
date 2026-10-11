# Small-account equity research

Target: **more than 10% all-in GBP return within one year on £3,000**, without additional funding. This is a research objective, not a demonstrated result. V1/V2 and corrected R3.3 controls failed; no candidate is qualified and no broker/live integration exists.

Current stage: **fast, bounded offline comparisons of momentum, Ridge and XGBoost**. Imperfect data is accepted for conditional research with explicit missing-outcome and cost sensitivity. Full historical remediation does not block every experiment. Ridge is not a prerequisite gate for XGBoost.

The [first three-model diagnostic is complete](docs/NEXT_RESEARCH_CYCLE.md#result--2026-10-10): ranking associations are weak and XGBoost shows no consistent advantage. Missing selected outcomes leave paired performance inconclusive; no account return was established.

Four available SEC ratios entered a [completed sparse-data comparison](docs/NEXT_RESEARCH_CYCLE.md#completed-ablation-result--2026-10-11). Only eight manually reviewed issuer/security joins were usable; the ratios did not establish a robust ranking or account-return improvement.

## Working documents

- [Roadmap](docs/ROADMAP.md): current policy and next deliverables.
- [Current experiment](docs/NEXT_RESEARCH_CYCLE.md): exact three-model comparison and interpretation.
- [Strategy](docs/QUANT_SPEC.md), [data](docs/DATA_AND_FEATURES.md), [validation](docs/BACKTEST_AND_VALIDATION.md) and [risk](docs/RISK_AND_EXECUTION.md): technical and safety contracts.
- [Architecture](docs/ARCHITECTURE.md): implemented versus proposed capabilities.
- [Source progress](docs/R3_COMPLETION_PROGRESS.md) and [legacy evidence](docs/LEGACY_EVIDENCE.md): historical records, not sequential approval gates.

## Local research

Python 3.12+ is required. Install in a suitable virtual environment:

```bash
python -m pip install -e '.[dev,historical-data,iteration]'
python -m src.cli.r3_iteration --config config.r3-iteration.yaml --output data/local/r3_iteration_new_run
python -m src.cli.r3_fundamental_iteration --config config.r3-fundamental-iteration.yaml --output data/local/r3_fundamental_iteration_new_run
pytest
ruff check .
mypy src
python -m build
```

The iteration command requires the hash-bound local artifacts named in its configuration. It compares ranking diagnostics with one configuration per model, using the six later-period folds. It does not simulate account returns or establish the >10% target. The separate fundamental ablation is complete on the available eight-issuer sample; its missingness signal is a major interpretation limit. On macOS, XGBoost also needs a discoverable OpenMP runtime.

Existing `src.cli.r3_development`, `r3_dataset`, `r3_evidence`, `r3_feasibility`, `r3_contract`, `r3_step3_feasibility`, `r3_post_step3_decision`, `r3_identity_audit` and `v2_validation` commands retain their original contracts; use `python -m src.cli.<name> --help`. `src.cli.sample_pipeline --config config.example.yaml` is a synthetic engineering fixture.

Data, credentials, fitted models and run reports remain local/ignored. Preserve old artifact hashes. No current-only survivor selection, future information or fabricated fills. Account simulations retain long-only, <=5 stocks, <=30% per stock, no leverage, cash/fee affordability, 10% soft control and permanent 15% drawdown halt. The halt cannot guarantee a loss ceiling.

## Local Tiingo credentials

When running acquisition from the repository root, `python -m src.cli.historical_producer` automatically reads `config/credentials.local.toml` if `TIINGO_API_TOKEN` (or the variable named by `--token-environment`) is empty. Add your token locally:

```toml
[tiingo]
api_token = "YOUR_TOKEN"
```

The file is ignored by Git and stays separate from versioned research configuration and evidence manifests. An environment token takes precedence. Use `--credentials-file /absolute/path/to/credentials.local.toml` when running from another directory. This stores the token for future acquisition commands; it does not export it globally or start any downloads.
