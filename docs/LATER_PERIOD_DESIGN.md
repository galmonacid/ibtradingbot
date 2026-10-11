# Later-period research design

Registered direction: 2026-10-07, following the user's explicit approval. Historical stage at registration: source remediation and period design. These dates now also support the completed separate diagnostic in [the current cycle](NEXT_RESEARCH_CYCLE.md). This supplements [NEXT_RESEARCH_CYCLE.md](NEXT_RESEARCH_CYCLE.md) and [SOURCE_REMEDIATION.md](SOURCE_REMEDIATION.md).

## Period and rationale

Use requested start **2010-01-01**, the first complete calendar year following the sampled SEC facts' first causal availability on 2009-07-23. This is a data-availability convention selected before new performance calculations, not a claim that all required features existed in 2010. Do not move the start again based on returns or drop difficult issuers to improve results. Changes require a new design version and an explicit rationale.

The first XNYS session is **2010-01-04**. Retain initial eight-year expanding training, two-year validation, one-year test, annual advancement and 31-session boundary purging plus actual label-overlap and maturation checks. Calendar thresholds follow anniversaries of that first session, as in the existing window builder; they are not silently snapped to January 1. Training continues expanding from the same origin.

| Fold | Training through | Validation sessions | Test sessions |
| --- | --- | --- | --- |
| 0 | 2018-01-03 | 2018-01-04–2020-01-03 | 2020-01-06–2020-12-31 |
| 1 | 2019-01-03 | 2019-01-04–2020-12-31 | 2021-01-04–2022-01-03 |
| 2 | 2020-01-03 | 2020-01-06–2022-01-03 | 2022-01-04–2023-01-03 |
| 3 | 2020-12-31 | 2021-01-04–2023-01-03 | 2023-01-04–2024-01-03 |
| 4 | 2022-01-03 | 2022-01-04–2024-01-03 | 2024-01-04–2025-01-03 |
| 5 | 2023-01-03 | 2023-01-04–2025-01-03 | 2025-01-06–2026-01-02 |

All training starts on 2010-01-04. Session coverage through 2026-09-15 supports **six complete calendar folds**, not nine. A seventh partial year is excluded. These intervals are window assignments, not proof of six executable one-year accounts; funding, execution, terminal valuation and holding-horizon completeness must still be checked by the evaluator. All historical dates remain inspected development data. Fewer annual observations further limit uncertainty estimates; monthly stock rows cannot replace independent investment years.

## Implemented coverage audit

[Configuration](../config.r3-later-period.yaml), [planner](../src/research/r3_later_period.py), [CLI](../src/cli/r3_later_period.py), and [tests](../tests/test_r3_later_period.py) implement this separate design. The CLI verifies source hashes and the cropped local calendar against `exchange-calendars` XNYS sessions. It records working-tree file hashes, revision, dependency versions, timestamp, configuration and calendar identity. It reads eligibility/exclusion fields only, without labels, prices, returns or model fitting. No stochastic operation or selection trial occurs.

The existing price-feature slice has usable rows in all **200 complete months** from January 2010 through August 2026; the minimum monthly count is 367. Each test window contains 12 monthly decisions. This does not establish complete historical membership coverage: failed provider histories remain absent. The planner separately excludes **488 rows dated 2026-09-15**, which the existing artifact treats as a terminal decision despite the month being incomplete. No old artifact was edited.

The retained SEC report is an eleven-issuer sample and contains year-end snapshots only through 2017. For 2010 it reports six complete-case issuers. These snapshots are neither monthly coverage nor evidence for the later test years; the old report's 0/9 conclusion applies to the old 1999 protocol. The new planner carries that evidence as historical context and does not reinterpret it as six enriched feasible folds.

Immutable report: `data/local/r3_later_period_20261007_design_v2/report.json`, SHA-256 `053fa6b6204fde76a94831fde54c9110ecf52027604839639f92f6bc832dfc08`. A separate fixed-timestamp repeat produced identical bytes. The exploratory v1 remains preserved. The implementation snapshot predates this documentation update; later tree changes legitimately alter report provenance.

```bash
python -m src.cli.r3_later_period \
  --config config.r3-later-period.yaml \
  --output data/local/r3_later_period_reproduction/report.json \
  --run-timestamp 2026-10-07T06:17:47+00:00
```

Use Python 3.12+ with the project's historical-data dependencies. Run from the repository root. Outputs must be new; local artifacts remain ignored. This command registers calendar/coverage evidence only and is not a dataset builder or backtest command.

## Historical remediation checklist (not a block on current diagnostics)

The [current cycle](NEXT_RESEARCH_CYCLE.md) reuses these dates for conditional price-feature diagnostics. The following list describes remaining enriched-data/qualification work, not prerequisites to every model fit.

1. Repair source histories for the identified FB/META and Berkshire aliases, retaining failed requests and independent class evidence. Reconcile prices and corporate actions before building a new canonical artifact. Measure historical membership coverage, including departures and unavailable securities.
2. Expand causal SEC availability coverage to the full historical universe and every registered monthly decision, including later years. Resolve historical revenue concepts and issuer/class joins; define stale, missing and industry-specific feature rules before inspecting predictive returns. Do not restrict the universe to the eleven sampled issuers or complete cases.
3. Admit a dated industry taxonomy only with original filing/header and release-vintage checks. Keep macro features optional until vintage access is evidenced. Freeze permissions and recurring data/compute costs against the £3,000 objective.
4. Build new features, labels and label-independent scoring assignments for these six folds. Preserve unresolved labels and action/valuation failures. Apply actual overlap purging, maturation, training-only transforms and continuous risk state; reuse no old nine-fold assignment file as a six-fold contract.
5. Freeze the separate model experiment budget and ablations, then compare momentum, Ridge and XGBoost on identical dates, universes, costs and portfolio rules. Ridge remains the linear control, not the presumed winner. XGBoost must show after-cost incremental value attributable to the new features under the validation contract. Do not open test outcomes to select models or fill the calendar gap by weakening windows.

No new model dependency, fitted model, hyperparameter search, investment result or broker action is introduced here. The >10% all-in first-year GBP objective, five-stock/30%-per-stock limits, cash affordability, soft drawdown control and permanent halt remain unchanged. Model fitting and qualification readiness are explicitly false in the report.

## Verification — 2026-10-07

Nine focused tests passed for exact expanding boundaries, partial-year exclusion, independent-calendar mismatch, explicit missing-month coverage, terminal partial-month handling, duplicate/non-month-end observations, source tampering, immutable output and configuration protection. The full suite passed **465 tests**, with one non-failing joblib CPU-detection warning. Ruff and strict mypy passed (112 source files). The isolated build produced an sdist and wheel; the initial no-isolation attempt lacked Hatchling. Source integrity checks confirmed preserved original/corrected datasets, reports and model manifests unchanged. The real coverage report reproduced byte-for-byte. No investment backtest or model training ran.
