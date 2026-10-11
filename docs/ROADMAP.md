# R3 execution plan

Updated 2026-10-10. Stage: **bounded offline experiments with explicit data uncertainty**. Target: >10% all-in GBP return within one year on £3,000, without additional funding. No candidate is qualified; no broker integration is authorized.

## Current iteration policy — 2026-10-10

The user authorizes faster offline iteration using imperfect historical data where the limits still permit useful evaluation. Complete historical remediation is not a prerequisite to every experiment. Do not ask again for bounded offline continuation. Qualification and paper/live requirements remain separate in [validation](BACKTEST_AND_VALIDATION.md) and [risk](RISK_AND_EXECUTION.md).

Each cycle fixes a question, small candidate budget, inputs, chronological splits and sensitivity cases before fitting; then produces a result and a decision. Repair data when it changes that decision, rather than expanding infrastructure or auditing unrelated source gaps. Preserve failures and immutable evidence.

- Compare **momentum, Ridge and XGBoost together**. Ridge is a linear control, not a gate before XGBoost.
- Keep scoring independent of future outcomes; preserve actual label maturation, overlap purging and training-only transforms. No guessed identities, fabricated prices or future information.
- Supported subsets answer conditional questions. Report the historical denominator, exclusions and missing outcomes; never select today's survivors or claim subset coverage represents the full universe.
- Optional features may be deferred or use registered causal missingness rules. No fabrication of entire pre-coverage eras.
- Show paired comparisons and sensitivity to missing outcomes/costs. Scenario ranges are not confidence intervals; unsupported bounds must be described as illustrative. If a conclusion changes under credible adverse assumptions, call it inconclusive and identify the responsible defect.
- Preserve £3,000 accounting and every portfolio/risk invariant for account simulations. Ranking diagnostics do not establish net returns or the >10% objective.

## Current cycle

The first cycle completed on 2026-10-10: weak ranking diagnostics, unresolved paired outcomes and no model promotion. See [results and next hypothesis](NEXT_RESEARCH_CYCLE.md#result--2026-10-10). The sparse fundamental cycle has completed. Its eight reviewed joins cover only 1.54% of scored rows, and the models heavily favor the covered identities. See [the result](NEXT_RESEARCH_CYCLE.md#completed-ablation-result--2026-10-11). No model is promoted. A registered coverage-only control would test whether actual ratio values add anything beyond source membership; broader joins are required before representative performance claims.

The exact experiment is in [NEXT_RESEARCH_CYCLE.md](NEXT_RESEARCH_CYCLE.md) and [config.r3-iteration.yaml](../config.r3-iteration.yaml). It reuses the corrected local price-feature dataset over the six approved later-period folds, with one configuration per family. It first tests estimator effects through monthly ranking diagnostics, not a funded portfolio. Fundamentals are the next information hypothesis; their incomplete coverage does not block the first comparison.

1. Register inputs, parameters, weights, dates and sensitivity cases before fitting.
2. Execute momentum/Ridge/XGBoost on identical scoring rows, retaining unresolved selections.
3. Report conditional rank correlation, selected-label coverage and paired diagnostics; separate validation from test and preserve each annual block.
4. Use validation and data sensitivity to define the next hypothesis. Do not tune on outer-test results. Add causal fundamental features or repair the specific outcome gap only when that is the next useful question.
5. Run a shared-policy, after-cost £3,000 account comparison when inputs support it. Report unresolved accounts; never turn an unavailable valuation into a fill.

## Completed foundations and historical evidence

R3.1 economics and R3.2 data/split tooling exist. R3.3's original outcome-dependent scoring was corrected; the corrected momentum/Ridge/HGB controls failed promotion. Source audits, later-period planning, fundamental primitives and adjustment checks exist. They do not certify full coverage or establish profitability.

Detailed source work remains in [R3_COMPLETION_PROGRESS.md](R3_COMPLETION_PROGRESS.md), [SOURCE_REMEDIATION.md](SOURCE_REMEDIATION.md), [FUNDAMENTAL_FEATURE_AUDIT.md](FUNDAMENTAL_FEATURE_AUDIT.md) and [LATER_PERIOD_DESIGN.md](LATER_PERIOD_DESIGN.md). These are evidence records, not additional sequential approval gates. [Data repair requirements](DATA_REPAIR_REQUIREMENTS.md) guide targeted repairs and eventual qualification. [Legacy evidence](LEGACY_EVIDENCE.md) covers rejected controls and reproduction.

The superseded roadmap and cycle narratives were consolidated on 2026-10-10; their pre-edit working copies are preserved locally in `data/local/r3_iteration_docs_before_20261010`. Old source/run artifacts were not modified or re-signed.
