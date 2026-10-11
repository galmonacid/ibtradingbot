# Period-aligned fundamental feature audit

Updated 2026-10-11. Stage: four ratios now enter a separately versioned, sparse offline ablation with eight manually reviewed issuer/security joins; see [the current experiment](NEXT_RESEARCH_CYCLE.md#sparse-fundamental-ablation--2026-10-11). The historical coverage audit below predates that model run. The [completed ablation](NEXT_RESEARCH_CYCLE.md#completed-ablation-result--2026-10-11) found only 1.54% joined stock-month coverage and no established incremental value from ratio values. This extends [R3 completion progress](R3_COMPLETION_PROGRESS.md); R3 remains incomplete. These are issuer-level calculations and coverage evidence, not admitted security-level model inputs or return results.

## Implemented definitions

The [feature module](../src/features/r3_fundamentals.py) implements version `r3-sec-period-aligned-ratios-v1`. Four formulas were chosen from the proposed balance-sheet/profitability family before examining their coverage or investment outcomes. This is a bounded engineering pass, not the entire proposed richer-feature set or a model-trial registration.

| Output | Numerator tag | Period | Available issuer-months / 3,800 |
| --- | --- | --- | ---: |
| liabilities_assets | Liabilities | Instant | 2,894 |
| annual_net_income_assets | NetIncomeLoss | Reported annual | 3,430 |
| annual_operating_cash_flow_assets | NetCashProvidedByUsedInOperatingActivities | Reported annual | 3,099 |
| annual_gross_profit_assets | GrossProfit | Reported annual | 1,534 |

Every denominator is positive `Assets` with the **same fiscal period end** as its numerator, selected using only filings available at that decision cutoff. The annual ratios use year-end assets, not average assets; they are not asserted to be standardized return-on-assets measures. `Liabilities` is total tagged liabilities, not interest-bearing debt. `NetIncomeLoss` retains its parent-attributable tagged meaning; it is not substituted with consolidated profit, operating profit or earnings available to common shares.

The selector requires USD, the US-GAAP taxonomy, actual acceptance plus the inherited 24-hour processing-latency assumption, and a fiscal period no older than 550 days. At the latest eligible period it selects the latest available acceptance; conflicting values or period starts fail closed. Negative numerators are preserved; nonpositive assets and nonfinite ratios are missing. There is no quarterly annualization, YTD summation, currency conversion, cross-issuer mixing, backwards restatement or imputation. Annual means the existing audited 330–400-day duration classification; classification alone is not proof of financial comparability across industries.

The [coverage CLI](../src/cli/r3_fundamental_coverage.py) uses actual XNYS closes, including early closes. It verifies raw hashes and companyfacts CIKs, rejects competing source vintages, records source/implementation/dependency identities and refuses output overwrite. It does not read labels, prices or returns. Model fitting, historical security-join admission, full-universe coverage and qualification remain false. Missing gross profit never removes an issuer from the coverage denominator.

## Expanded evidence

The prior eleven-issuer sample was extended with eight coverage-priority candidates: EQR, BK/BNY, WY, MSI, KFT/MDLZ, GRMN, DISCA and NI. CIK candidates came from the preserved discovery queue; no current ticker association was promoted into a dated identity interval. Twenty-five bounded, sequential public SEC requests succeeded. They fetched submissions, companyfacts and referenced older submission shards without credentials or paid access.

Combined evidence contains **28,610 retained facts and 2,048 parsed filings across 19 issuers**, audited at 200 complete monthly decisions from January 2010 through August 2026: **3,800 issuer-months**. All submission shards referenced by these downloaded main responses were acquired; that does not prove the SEC extraction itself contains every historical disclosure or that the nineteen issuers represent the universe. The 793-identity coverage gap remains open.

Observed missingness includes absent USD contexts, stale annual reports and three liabilities observations without same-period assets. Gross-profit coverage is particularly sparse. Training-only imputation cannot be used to call these missing histories complete or to fill an all-missing era. Industry treatment, revenue-concept transitions, growth/valuation features, sector metadata and broader primary-filing reconciliation remain outstanding.

## Primary-filing reconciliation

A manual review of [Equity Residential's 2009 annual filing](https://www.sec.gov/Archives/edgar/data/906107/000119312510040142/d10k.htm), followed by automated accession/period/unit/value checks, reconciled four USD facts. Values shown in thousands in the filing convert to assets of $15,417,515,000, liabilities of $9,984,722,000, controlling-interest earnings of $362,273,000 and operating cash flow of $672,462,000. The earnings figure differs from both consolidated earnings and earnings available to common shares; the feature definition explicitly retains that distinction. No gross-profit substitute was invented.

This one filing supports a representative extraction/scale/semantic check, not full-universe data certification, primary-listing eligibility or continuous issuer/class identity. The original HTML and numerical reconciliation remain locally hash-bound.

## Evidence and reproduction

- New raw SEC package: `data/local/r3_priority_sec_20261007_v1`, with acquisition plan, source script, request timestamps and access manifest. The request ceiling was 32; 25 requests were used, all successful. The older eleven-issuer package remains unchanged.
- Final coverage report: `data/local/r3_fundamental_20261010_audit_v2/report.json`, SHA-256 `9f777c644185e772deb596b9a4693c9f0c612ccdc8b9f504e7e9eb2ebbd98528`. A separate repeat at the same timestamp and tree matched byte-for-byte. Exploratory v1 is preserved.
- Original filing: `data/local/r3_eqr_primary_20261010_v1/eqr_2009_10k.htm`, SHA-256 `299f0e080c707454986af231be56a42fedb392005368bd72871af1669e170326`.
- Reconciliation: `data/local/r3_eqr_primary_20261010_v1/reconciliation.json`, SHA-256 `8c5ac1988e36f5c1fbc2220da921333aeb0a33b4ed0d1b9fa2e529ffc0764d28`. It binds the reviewed source, API response, exact accession/period checks and retained review script.

```bash
python -m src.cli.r3_fundamental_coverage \
  --access-manifest data/local/r3_step3_20261002_feasibility_v7/source_access_manifest.json \
  --raw-directory data/local/r3_step3_20261002_feasibility_v2_raw \
  --access-manifest data/local/r3_priority_sec_20261007_v1/access_manifest.json \
  --raw-directory data/local/r3_priority_sec_20261007_v1 \
  --output data/local/r3_fundamental_reproduction/report.json \
  --run-timestamp 2026-10-10T16:05:43.719340+00:00
```

Run from the repository root with Python 3.12+ and the declared historical-data dependencies. Source pairs are ordered. Outputs must be new; the report includes working-tree provenance, so later implementation or documentation edits legitimately change its hash. No fitted model, canonical data or previous experiment was overwritten.

## Remaining qualification work

Expand and verify historical issuer/class joins and repair absent trading histories before qualification-grade enriched data. A separate conditional development ablation has already used the eight manually matched sample joins. Then freeze the feature/missingness policy, cost assumptions, trial budget and ablations. Retain momentum and Ridge as controls and test XGBoost on the same eligible universe and portfolio policy. These coverage results do not justify selecting any model or weakening risk/qualification requirements.

## Verification — 2026-10-10

Fifteen focused tests passed for causal amendments/processing latency, negative numerators, same-period denominators, annual versus quarterly/YTD contexts, invalid assets, conflicting contexts, taxonomy/currency separation, stale-period boundaries, issuer separation, actual early-close timing, raw-source tampering and immutable output. The real report and fixed-timestamp repeat matched byte-for-byte. The final full suite passed **491 tests**, with one non-failing joblib CPU-detection warning; Ruff and strict mypy passed (116 source files); the isolated package build produced an sdist and wheel. Old evidence hashes, local links, whitespace and ignored-output checks passed. `TIINGO_API_TOKEN` remained absent when rechecked. No model fitting, performance selection or broker action occurred.
