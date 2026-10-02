# Data, features and labels

Status: existing V1/V2 data tooling plus an implemented R3.2 observation/label/split contract. No qualification-grade R3 dataset has passed it. Certification is a content-bound claim about specified checks, not proof that historical data is bias-free.

## Existing lineage and unresolved gaps

Preserve immutable raw sources, canonical data and report manifests separately. The existing route uses pinned `chinobing/historical_sp500_constituents` membership, `unliftedq/index-constitution` identity/delisting records, `riazarbi/sp500-scraper` Wikipedia/iShares IVV QA, and Tiingo OHLCV/actions. FMP remains optional independent QA, never a source for silently backfilling canonical prices or membership.

Pin origins, commits, licences or explicit absence of a licence, retrieval timestamps, input hashes and transform versions. The user permits available local data with unclear licensing for development research only; record access terms and do not redistribute it. The 400-member historical coverage floor does not establish complete membership or eliminate provider-availability bias. Audit 50–100 seeded constituent changes independently; report disagreements and unavailable histories. Resolve source-use permissions, including the previously missing scraper licence, before relying on them for qualification or redistribution.

Known gaps from V2: dated primary-listing/common-stock classifications; dividend payment dates and withholding; independent exchange-calendar evidence; historical FX release vintages; exact account tariff, conversions, fractional permissions and instrument eligibility. Closing these gaps is a prerequisite to qualification. Missing dividend payment dates create non-spendable receivables, not immediate purchase cash. Missing delisting recovery cannot be replaced by the last observed price or by dropping the security.

ECB reference data remains development-only until its vintage/timing limitations are resolved. Cross rate is GBP per EUR divided by USD per EUR. The old next-calendar-day availability assumption and six-day development age allowance are documented assumptions, not executable quotes. Use [ECB publication information](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) and source terms when registering a new extract; no download or purchase is performed by this reset.

## R3 observation contract

One row per eligible stable security ID and monthly decision timestamp. Store feature cutoff, source availability timestamps, membership interval, raw/adjusted series identity, exclusion reasons, label start/end, label availability, split/fold ID and transform version. Do not use ticker strings as permanent identities.

Required prices are complete on the pinned exchange calendar. Adjusted closes may support total-return signals only with causal corporate-action handling; verify prefix invariance under later actions. Fills use raw prices and actual share/cash adjustments. Never forward-fill returns, manufacture missing sessions, use future constituent lists or screen on eventual survival.

All candidate models use this initial feature set, with no automated feature search:

| Feature | Definition using information through decision close t |
| --- | --- |
| Recent return | P[t]/P[t-21]-1 |
| Medium/long momentum | P[t-21]/P[t-63]-1, P[t-21]/P[t-126]-1, P[t-21]/P[t-252]-1 |
| Volatility | Sample daily-return standard deviation over 20 and 63 sessions, annualized by sqrt(252) |
| Trend distance | P[t]/SMA200[t]-1 |
| Drawdown | P[t]/max(P[t-251:t])-1, inclusive of t |
| Liquidity | Log of positive trailing 20-session median raw close times volume |
| Market state | SPY 21-session return, SPY 20-session volatility, SPY/SMA200-1 |

P denotes total-return-consistent adjusted close. Verify exact inclusive endpoints and minimum warm-up in tests. Missing required inputs excludes the row; no outcome-conditioned imputation. Ridge scaling is fitted on training rows only. Tree models receive the same raw features. No fundamental, sector, news, sentiment or revised macroeconomic data enters the first experiment.

## Label definition and availability

For monthly signal date t, let e be the first exchange-session open after t, and x the first exchange-session open after the next monthly signal date. The label is the stock's corporate-action-consistent total holding return from e to x minus the SPY total holding return over the same interval, both measured in GBP with causal FX conventions. Execution slippage, broker fees and small-account portfolio effects belong in the event simulator, not a single universal per-row cost deduction.

A label matures only when x and all required outcome data are available. Never train on the future closing price used by an open-to-open label. Record corporate-action accrual separately from spendable cash. Use explicit terminal recovery for a delisting; if unavailable, the sample is unresolved and the dataset cannot support qualification. Do not silently delete difficult outcomes from training or evaluation.

Label horizon varies with monthly exchange sessions. Purge by actual [e,x] intervals and availability timestamps, not by a presumed fixed 20-day horizon. Same-date stocks remain in the same split. Equal date weights prevent large cross-sections dominating the loss, and thousands of correlated stock rows never count as thousands of independent years.

## Evaluation data boundary

Every period examined in V1/V2, including their training and validation histories, is R3 development data. A new model, data vendor or split does not make those dates untouched. Register accessed periods and all experiment outcomes. Historical unseen evaluation requires verifiable non-access; otherwise accumulate forward observations after freeze.

Immutable manifests bind raw input hashes, calendar, feature schema, row ordering, labels, preprocessing, model, configuration, costs, source revision/tree, environment and timestamps. Dataset/model artifacts and credentials remain in ignored local paths. CI uses synthetic fixtures only; they cannot train a performance-claiming model or establish objective success.

## R3.2 development materialization — 2026-09-27

The content-bound local run used the V3 canonical manifest, its four Parquet files, producer evidence, universe policy, the empirical SPY calendar and the retrospective ECB GBP/USD archive. It recorded all ten accessed artifacts and their physical hashes. Source terms include two Git snapshots with no detected licence; these are explicitly local-development/no-redistribution inputs under the user's scope decision.

The run produced 30,627 stock-month feature rows from 2021-06-30 through 2026-09-15: 30,133 usable rows and 494 exclusions. Exclusions comprised 334 incomplete 253-session histories, 107 raw prices below $10 and 82 observations below $20m median dollar volume; a row may carry multiple reasons. Stable security identity and half-open membership intervals were preserved, but all 606 retained membership intervals use an explicitly recorded primary/common-stock and retrospective-availability assumption because the source schema lacks dated classification and publication timestamps.

Of 30,133 attempted labels, 14,481 matured and 15,652 remained unresolved. The unresolved reasons were 13,744 missing cash-action payment dates, 481 unavailable/stale entry FX observations, 410 unavailable/stale exit FX observations, 966 incomplete final horizons, 49 missing exit or explicit delisting recovery and 2 unavailable entry prices. The canonical action schema has 9,923 retained dividends without payment/withholding fields and 35 retained delistings without payment dates. These rows remain in the label artifact and are not silently assigned to training splits.

The matured labels span 1,765 days. Five folds contain at least one assignment, but only two contain some train, validation and test rows; neither covers the registered 8-year training, 2-year validation and 1-year test history. Therefore there are zero protocol-ready folds. The dataset is useful for interface and exclusion auditing only. R3.3 development training remains blocked; no result is qualification or fresh evidence.

## R3.2 label-evidence closure rerun — 2026-09-28

The closure rerun reconstructed every usable GBP/USD observation in the existing ECB archive, yielding 7,098 causal observations from 1999-01-04 through 2026-09-22. It preserves the 14:10 Europe/Berlin observation-time assumption and following-calendar-day 00:00 UTC availability assumption. This is a retrospective archive, so FX vintage certification remains false.

Dividend evidence combines immutable Nasdaq response bodies with State Street's SPDR historical-distribution workbook for SPY. Matching requires the canonical ex-date and amount, but the label uses the provider's actual payment/payable date; an ex-date is never substituted for payment. The 15% US-UK portfolio-dividend rate is a development assumption sourced to the treaty and conditional on a valid W-8BEN and US-source classification. It is not account-specific withholding evidence. Nasdaq access terms remain unresolved and State Street restricts reproduction; provider material is local-only and is not redistributed.

Two delistings now have explicit cash amount and completion/payment timing: TIF at $131.50 on 2021-01-07 and SGEN at $229 on 2023-12-14. ABMD remains unresolved because its $380 fixed cash component also included a contingent-value right; recording fixed cash alone would omit a possible outcome. All other unavailable delisting recoveries remain unresolved rather than being replaced by zero or last price. An independent `exchange_calendars` 4.13.2 XNYS session set exactly matches all 7,726 benchmark sessions. The package and generated calendar are hash-bound; the calendar is still not vintage-certified.

The wider run produced 133,141 feature rows: 121,291 usable and 11,850 excluded. It produced 91,546 matured and 29,745 unresolved labels. Unresolved reasons are 28,605 missing cash-action payment dates, one unavailable/stale cash-action FX observation, 966 incomplete final horizons, 160 missing exits or explicit recovery and 13 unavailable entry prices. There are 4,367 evidenced dividends, 32,857 unresolved dividends, two evidenced delistings and 107 unresolved delistings. All 28,606 cash-action-affected unresolved labels remain in the label artifact; zero were dropped based on their outcome.

The dated primary-listing/common-stock source gap remains a versioned development assumption over 822 retained intervals. Its measured impact is total: removing the assumption excludes all 133,141 feature rows and all 121,291 attempted labels. It therefore blocks qualification and is not presented as innocuous metadata.

Matured labels span 10,045 days and populate 17 nonempty folds. Folds 0–8 have every expected monthly decision after actual-interval purging, giving nine temporally protocol-ready 8/2/1 folds. This closes the history-length condition, but not label completeness: 28,606 unresolved cash-action labels would still be omitted from training assignments. The initial closure report therefore recorded `r3_3_development_training_permitted: false`. No model was fitted or evaluated.

## R3.2 explicit closure decision — 2026-09-28

The user subsequently decided to move on without cash-action completeness, verified withholding, dated primary/common-stock classification, complete delisting recovery or vintage certification. The decision is encoded in `config.r3.yaml` and the final materialization report as `proceed_with_open_label_evidence`. It does not change any source-audit flag, fill a missing label, resolve a limitation, make unresolved rows trainable or permit qualification.

The scope decision waives those limitations only as blockers to later R3.3 development. The non-waived safety conditions still pass: nine registered 8/2/1 folds are temporally complete, and zero cash-action rows were dropped from the label artifact based on outcome. The final report therefore records `r3_2_phase_closed: true`, no remaining development-training blockers, `r3_3_development_training_permitted: true`, `r3_3_started: false` and `qualification_permitted: false`. R3.2 has no remaining required implementation tasks under this scope; the evidence limitations remain mandatory disclosures in every later experiment.
