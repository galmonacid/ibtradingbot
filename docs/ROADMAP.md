# Execution plan

Decision date: 2026-09-26. Updated 2026-10-01. Current stage: **R3.3 implemented; development failed; stop before R3.4**. R3.1 and R3.2 were closed by explicit scope decisions while their evidence gaps remained open. R3.3 preserves those limitations and supplies no qualification evidence. Prior engineering is retained; V1/V2 investment candidates remain rejected. The objective is >10% all-in GBP return within the first year on initial £3,000: net profit >£300 and terminal wealth >£3,300.

## R3.1 — Prove account economics and explain the missed exposure

First implementation change: add an offline feasibility/attribution report using the existing evidence and raw ledger primitives. It must enumerate the funnel from PIT membership through data, liquidity, signal, regime, volatility allocation, whole-share rounding, economic floor, cash and actual fills. Attribute skipped orders and exposure by date; separate fee erosion from signal returns and halted time.

Compare the old $500m/£150 policy with the proposed capacity/cost policy without choosing parameters from future returns. Produce a £3,000 starting-account budget including tariff offsets, FX, fees, recurring data/hosting and mandatory-liquidation reserves. Resolve exact broker tariff/permissions using documented account evidence when provided; otherwise label alternatives and block qualification. No account connection or purchase is needed for the initial offline report.

**Exit:** reconciled cost/exposure attribution, executable plans for the £3,000 starting account, known all-in cost budget and no hidden funding or fractional assumption. Zero feasible trades, unaffordable data or an unresolved cost contract means stop or seek a separate scope decision. It does not authorize lowering safety limits.

### R3.1 implementation record — 2026-09-27

Implemented separately from V1/V2:

- strict `r3.1-feasibility-v1` configuration and offline CLI;
- immutable £3,000 V2 ledger validation and same-fill gross/cost reconciliation;
- per-session exposure/halt attribution plus decision-date exclusions, skips and fills;
- causal PIT/calendar recomputation of the fixed $500m/£150 funnel versus the predeclared $20m, 0.01%-capacity and <=1% round-trip-cost policy;
- flat-£3,000, next-session-open, whole-share feasibility plans with the 2% cash buffer, 12% volatility ceiling, <=30% name cap and mandatory-liquidation reserve; and
- a fail-closed budget that distinguishes a possible commission offset from the conservative full £36 annual account minimum and never double counts the alternatives.

The content-bound run used the preserved `gbp3000__baseline.json` ledger and matching V3 canonical/calendar evidence. It reconciled 1,254 sessions, 49 fills, 4.1860% mean exposure and 85 hard-halted sessions from 2026-02-27. Terminal wealth was £2,576.95 (net profit -£423.05). Same-fill gross profit was -£189.59; modeled cost drag was £233.46 and nominal recorded costs were £233.88. Thus costs materially worsened the result but did not explain away the negative same-fill outcome.

Across 55 historical decision dates, the R3 policy audit found 57 individually feasible orders but only 2 complete four-order flat-account plans (8 orders). Capacity was not the observed binding constraint. Whole-share rounding and the fixed 1% complete round-trip cost ceiling blocked most plans. These are inspected development feasibility observations, not an R3 return simulation or parameter-selection evidence.

The conservative budget includes the full £36 annual account minimum plus a £5.03 maximum observed liquidation reserve, requiring gross profit strictly above £341.03 under the current assumptions. It assumes no additional funding and no fractional shares. Exact tariff/commission-offset terms, account/instrument permissions, and incremental annual data, hosting and software costs require evidence. The retained ledger also carries known development-data limitations. Therefore the all-in budget is not known and R3.1 research acceptance is **blocked**. The separate scope decision below closes the phase without changing that evidence result.

### R3.1 assumption-only closure attempt — 2026-09-27

At the user's direction, the configuration now records these planning assumptions:

- charge the full £3 adult-ISA monthly minimum with no commission offset, for £36 per year;
- permit whole-share eligible US stocks in the intended cash-only ISA;
- do not assume fractional-share permission; and
- use £0 incremental annual data, hosting and software cost, with existing resources treated as sunk.

The public [IBKR UK ISA overview](https://www.interactivebrokers.co.uk/en/accounts/isa-accounts.php) states that the adult ISA is cash-only, has a £3 monthly minimum activity fee, offers global-market access, and prices US stocks from USD 0.005 per share. The public [required-minimums schedule](https://www.interactivebrokers.co.uk/en/accounts/required-minimums.php) separately lists the £3 monthly minimum. Those pages do not establish the intended account's exact commission-offset calculation, security-by-security ISA eligibility, enabled trading permissions, or actual incremental operating costs. The config therefore separates the assumed values from three `false` verification flags; assumptions cannot satisfy the evidence gate.

The rerun retained 2 complete feasible flat-account plans and the same £41.03 fixed-cost/liquidation-reserve budget. Research acceptance remains `false`. The unresolved evidence is: exact tariff and commission offset; account permissions and instrument eligibility; support for the assumed £0 incremental data/hosting/software cost; and the previously recorded legacy-data limitations. No purchase, account connection or order occurred.

### R3.1 closure decision — 2026-09-27

The user explicitly decided to move to R3.2 despite all four open points above. This is the separate scope decision allowed by the R3.1 exit contract. The report records `phase_closed: true`, `next_stage_permitted: true` and `next_stage_started: false`, with closure basis `explicit_scope_decision_with_open_evidence`.

This decision does not make the all-in budget known, satisfy research acceptance, cure legacy data limitations, qualify a candidate, authorize paper/live execution, or permit the open points to be omitted from later readiness checks. They carry forward as explicit unresolved dependencies. No R3.2 implementation was performed while recording this decision.

Reproduction (outputs remain ignored):

```bash
python -m src.cli.r3_feasibility \
  --ledger data/local/phase3_v2/audited_full_final_v2/ledgers/gbp3000__baseline.json \
  --legacy-report data/local/phase3_v2/audited_full_final_v2/research_report.json \
  --config config.r3-feasibility.yaml \
  --canonical-manifest data/local/phase3_build_v3/canonical/canonical_manifest.json \
  --calendar data/local/phase3_v2/calendar.csv \
  --output-directory reports/r3_1_20260927 \
  --run-timestamp 2026-09-27T13:00:00+00:00
```

Evidence identities include the physical ledger `58050022095740a032031d11fae140939bc30469d0be8eb75afcc84c4d9d95fd`; its audited parent report `eff58a1d823f5814cb546f3898eddf625ff7000c079c013213db8bc6f13b6db1`; canonical manifest `a669110a7f575f8c3883dbcf7f9ab9203a21031f8f27d0789405ba80692d5dc3`; calendar `942db7fb86a85cf0c7f50a220eee39fca3fde2d5d5ce2775cb133f43d7f3ce8e`; and closure-config file `61dfb04a1c505c22797105b65155d10ea93135fe77fca7e2c08da3db16d41eea`. The ignored JSON artifact SHA-256 is `16127a4d758abec6f7e1dcd3bbe5c85dd26abf436463aeb81f361330ac9a60b3`; its internal report identity is `3056132a8ad3de1423104b317aa68fac277bc13baef43ac6102ec8dbd56189e8`. The report records implementation-tree SHA-256 `6e1cacd50b79b7c89ea6fa1eb1bc3e34bf022a21a951426e06bd535d25b54191`, the dirty working-tree status, Python/dependency versions and timestamp.

This R3.1-era next-task statement is superseded by the R3.2 implementation and materialization records below. Its unresolved dependencies remain carried forward.

## R3.2 — Data contract, objective evaluator and bounded registration

Close the data gaps listed in DATA_AND_FEATURES; preserve existing source licences and manifests. Implement exact 12-month endpoint/all-in wealth accounting before model optimization. Add causal stock-month features, matured labels, date-grouped/purged splits and a complete accessed-data/trial register. Fix the six candidate configurations and portfolio sensitivity list. Add a separate typed R3 configuration and fail-closed readiness result.

**Exit:** tests for future-data mutation invariance, split/action/FX timing, delisting outcomes, fee attribution, one-year endpoints and £3,000 account readiness. If data supports only development, record that clearly; no qualification claim. Training cannot proceed on invalid label construction.

### R3.2 implementation record — 2026-09-27

Implemented separately from the rejected V1/V2 controls:

- strict `r3.2-contract-v1` configuration containing exactly the momentum control, Ridge alphas 1/10/100, histogram-gradient-boosting leaf counts 7/15, fixed seed and eight portfolio sensitivity neighbors;
- causal monthly stock-row primitives with stable identities, availability timestamps, fixed feature schema, explicit exclusion reasons and complete 253-session inputs;
- GBP open-to-open excess labels with causal FX lookup, payment-timed after-withholding cash actions, split handling, explicit delisting recovery and unresolved-outcome blocking;
- annual-step 8-year/2-year/1-year chronological folds using matured labels, same-date assignments, actual interval purging and a 31-exchange-session boundary gap;
- exact last-session-on-or-before-12-calendar-month GBP accounting with a gross/trading-net/all-in cost bridge, liquidation reserve, external-flow rejection, unsettled/accrual disclosure and strict `>£300`, `>£3,300`, `>10%` gates; and
- a content-bound accessed-data/trial register that preserves rejected V1/V2 controls, pre-registers all six R3 configurations, and produces a separate readiness result carrying the R3.1 and data-evidence blockers forward.

No model was trained and no R3 return simulation was run. Synthetic tests establish interface and timing behavior only. The preserved R3.1 ledger, parent report, canonical manifest and calendar were rechecked at their recorded hashes. The available historical inputs still have the documented gaps in dated primary/common-stock evidence, dividend payment/withholding evidence, independent calendar evidence, FX vintages and delisting recovery completeness. Tariff, account permission and incremental operating-cost evidence also remain unverified. Therefore readiness is `development_only`, R3.2 research acceptance is **blocked**, and R3.3 training is not yet permitted.

Deterministic registration inspection:

```bash
python -m src.cli.r3_contract \
  --config config.r3.yaml \
  --run-timestamp 2026-09-27T15:00:00+00:00
```

After adding the explicit six-day retrospective FX-age assumption, the typed-config SHA-256 is `28b370314981a9e20a242c80971220037a5b92ae1be58258abac78a3de57dbdd`; the empty-access register identity containing the two rejected legacy controls and six R3 pre-registrations is `b6cc21f8e9a88f23f2fdedb1d27e1fa067e468a711f713a3619a77465ea988ed`. Generated datasets, fitted models and reports remain ignored.

### R3.2 development materialization record — 2026-09-27

The user decided that absent or unclear data licensing does not block local development research. The materializer still records source provenance, access terms and no-redistribution limitations; licensing remains a qualification/redistribution limitation rather than a reason to fabricate or omit data.

`python -m src.cli.r3_dataset` now verifies the full canonical manifest and inputs, adapts half-open stable-ID membership and raw/adjusted bars, records all ten accessed files, materializes deterministic Parquet feature/label/split tables, retains unresolved outcomes, and writes a content-bound report and experiment register. No model code or model dependency was added.

The fixed-timestamp run produced:

- 30,627 feature rows over 2021-06-30–2026-09-15: 30,133 usable and 494 excluded;
- 14,481 matured labels and 15,652 unresolved labels;
- 33,422 split assignments across five partially populated folds;
- two folds with some rows in all partitions, but zero protocol-ready folds because matured labels span only 1,765 days rather than the registered 11-year 8/2/1 protocol; and
- an explicit `r3_3_development_training_permitted: false` result.

The largest unresolved class is 13,744 labels affected by cash actions without payment dates. Other unresolved rows are 481 entry-FX gaps, 410 exit-FX gaps, 966 incomplete final horizons, 49 missing exits/recoveries and 2 missing entries. The retained canonical slice contains 9,923 dividends without payment/withholding fields and 35 delistings without payment dates. Classification for 606 retained membership intervals is assumed, not evidenced. The SPY-derived calendar matches benchmark sessions but is not independent; ECB FX is retrospective and not vintage-certified.

Reproduction (outputs remain ignored):

```bash
python -m src.cli.r3_dataset \
  --canonical-manifest data/local/phase3_build_v3/canonical/canonical_manifest.json \
  --dataset-evidence data/local/phase3_build_v3/dataset_evidence.json \
  --universe-policy data/local/phase3_build_v3/universe_policy.json \
  --calendar data/local/phase3_v2/calendar.csv \
  --fx-csv data/local/phase3_v2/fx.csv \
  --fx-manifest data/local/phase3_v2/fx_manifest.json \
  --config config.r3.yaml \
  --output-directory data/local/r3_2_20260927 \
  --run-timestamp 2026-09-27T16:00:00+00:00
```

Artifact identities are: feature table `9834cf5ac50460ed7babacdb7e49eb9932d437c1ddd8edf444c86cd802680d2d`; label table `304bf3cfbc3622a8d4b1f1436cf4f989f4c4b87b49b6222f3bc3a3104d2d372b`; split table `523343c2da171b56468e494cf71a154c4021ccd1badd3c33290b37ee5c739b4a`; accessed-data/trial register file `6ff81d0e30b32414935df0865ddaa8a9a305612203e82276f468e835ea4d3da4` with internal identity `9a2b9decd9c67e52c087829426bddc1a19a253b3e2b4cc186d96d3ad1fcbbc70`; dataset identity `92a48eaa3ecde8af70c160a9ac668fc40fba01e867d628ffec3e1b873d1ba9e4`; and report file `272fb608cff38fa6d991922677868965e3a3ca7e3a06899f36c67152005f6764`. A second fixed-timestamp run reproduced every artifact byte-for-byte. The report binds implementation tree `5a3ef881c268ed041527bf7a77f37f49d4e335a7d044c6fa0e943864a65b77b8`.

Next actionable task: remain within R3.2 and obtain or construct source-backed dividend payment/withholding fields, explicit delisting payment/recovery timing, longer causal GBP/USD history, dated primary/common-stock classification and independent calendar evidence. Re-materialize and require at least one fully covered 8/2/1 fold with no outcome-conditioned cash-action omissions before permitting R3.3 development training. Tariff, account-permission and operating-cost gaps continue to block qualification but do not affect label construction.

### R3.2 label-evidence closure record — 2026-09-28

This change remained inside R3.2. It added a separate evidence builder and extended the materializer; it did not add a learner, fit a model, simulate a strategy, connect to a broker or place an order. V1/V2 code and evidence remain controls.

Evidence added and limitations retained:

- The existing ECB archive was rebuilt in full: 7,098 GBP/USD observations from 1999-01-04 through 2026-09-22. The CSV SHA-256 is `6924938e8071341ffd09f549832409db9e60d5d5181d00b0ffe615407c036361`; manifest `8fef782ec533d00f04866acc349437b4b9300c7db69bf3b5b9dd5047bc0625e3`; source archive `c63a1996014663ba3188c7b2820646882b07276513c0b3851a69581add38cb77`. The 14:10 Europe/Berlin observation and following-day 00:00 UTC availability assumptions are preserved. Vintage certification remains false.
- Nasdaq dividend responses were stored immutably and matched on canonical ex-date and amount. State Street's official SPDR workbook supplied SPY payable dates back to 1993; its SHA-256 is `51a16a450298a663b3fa088883a17c75f4464e87c911b0e83902a0ad46877c54`. Matching never substitutes an ex-date for a payment date. Nasdaq terms are unresolved and State Street restricts reproduction, so raw/provider data is local-only and must not be redistributed.
- The cash-action CSV contains 4,376 rows including 4,374 dividends and two delistings; only 4,367 dividend actions intersect the retained materialization slice. Its SHA-256 is `653d1beb9134839a08bc728e7b7bc1a88765da3870cf90d33fb25eee7a20f850`; manifest `027844c788419da1421962622cb1808512f39fcb460f3ffdeacb83c873b92693`; unmatched audit `413e926e4e7e057896dd276ff55a899db81050a27e1de81b58b3b49a37cf82c8`. The 15% treaty rate remains a W-8BEN/US-source development assumption, not verified account withholding.
- TIF has explicit $131.50 cash and 2021-01-07 completion/payment timing from LVMH; SGEN has explicit $229 and 2023-12-14 completion timing from Pfizer. The curated file SHA-256 is `356015707b490ab93c50838d391e065ff4d221b54d3dbf24b54800b9d0fee9e7`. ABMD's contingent-value right and 107 other unavailable outcomes remain unresolved; no last price or zero recovery was invented.
- `exchange_calendars` 4.13.2 supplied an independent Apache-2.0 XNYS ruleset. Its 7,726 generated sessions exactly match the benchmark calendar. Calendar SHA-256 is `e36f6f56f9f06f02db12170bf50afb549ffa0ea5ed182fc794eb5ff022b69a20`; manifest `06cfc751a2f3ac8218397777cd17ab4c24c9b822b81f635aa177832e7a0130ed`; package-tree identity `1d631ebb71723a591228b3cca488428ba536c296236a778664d19136340f174e`.
- No dated primary/common-stock source was available. The versioned assumption covers 822 intervals, and its quantified impact is all 133,141 feature rows and all 121,291 attempted labels. Removing it leaves no materialized dataset. The assumption is therefore explicit and remains a qualification limitation.

The experiment register records 17 accesses, including every new evidence CSV, manifest, source archive, curated file and State Street workbook, plus all six preregistered trials. Newly accessed sources are marked previously uninspected. Source hashes, access periods, retrieval time, terms and no-redistribution status are bound into the ignored artifacts.

Compared with the 2026-09-27 artifact, feature rows increased from 30,627 to 133,141, usable rows from 30,133 to 121,291 and exclusions from 494 to 11,850 because the causal history is much longer. Attempted labels increased from 30,133 to 121,291; matured labels from 14,481 to 91,546; unresolved labels from 15,652 to 29,745. The absolute unresolved count rose with the fourfold broader history, while its share fell from 51.9% to 24.5%. Cash-action payment-date gaps changed from 13,743 to 28,605; old entry/exit FX gaps of 481/410 were reduced to zero, apart from one cash-action FX gap. Final-horizon gaps remain 966, missing exits/recoveries rose from 50 to 160 over the wider period, and missing entries rose from two to 13.

The new artifact has 17 nonempty folds and nine fully covered registered 8/2/1 folds (IDs 0–8), versus two nonempty and zero ready folds before. It retains 28,606 unresolved cash-action labels and drops zero cash-action rows from the label artifact based on outcome. Retention makes the missingness visible but does not make those labels trainable. The two required readiness conditions are therefore evaluated separately: temporal coverage passes; complete, non-outcome-conditioned cash-action training coverage fails. **R3.3 development-training permission remains false.** Qualification also remains false.

Reproduction (all outputs remain ignored and local-only):

```bash
python -m src.cli.r3_evidence ecb-fx \
  --archive data/local/phase3_v2/fx_ecb_archive.zip \
  --output-csv data/local/r3_2_evidence_20260928/gbp_usd_ecb.csv \
  --output-manifest data/local/r3_2_evidence_20260928/gbp_usd_ecb_manifest.json \
  --retrieved-at 2026-09-28T09:00:00+00:00

python -m src.cli.r3_evidence xnys-calendar \
  --output-csv data/local/r3_2_evidence_20260928/xnys_exchange_calendars.csv \
  --output-manifest data/local/r3_2_evidence_20260928/xnys_exchange_calendars_manifest.json \
  --start 1996-01-02 --end 2026-09-15 \
  --retrieved-at 2026-09-28T09:00:00+00:00

python -m src.cli.r3_evidence nasdaq-dividends \
  --canonical-actions data/local/phase3_build_v3/canonical/corporate_actions.parquet \
  --output-directory data/local/r3_2_evidence_20260928 \
  --start 2013-01-01 --end 2026-09-15 \
  --retrieved-at 2026-09-28T09:00:00+00:00 \
  --curated-delistings data/local/r3_2_evidence_20260928/curated_delistings.json \
  --spdr-distributions-xlsx data/local/r3_2_evidence_20260928/spdr-etf-historical-distributions.xlsx

python -m src.cli.r3_dataset \
  --canonical-manifest data/local/phase3_build_v3/canonical/canonical_manifest.json \
  --dataset-evidence data/local/phase3_build_v3/dataset_evidence.json \
  --universe-policy data/local/phase3_build_v3/universe_policy.json \
  --calendar data/local/phase3_v2/calendar.csv \
  --fx-csv data/local/r3_2_evidence_20260928/gbp_usd_ecb.csv \
  --fx-manifest data/local/r3_2_evidence_20260928/gbp_usd_ecb_manifest.json \
  --fx-source-archive data/local/phase3_v2/fx_ecb_archive.zip \
  --cash-action-evidence data/local/r3_2_evidence_20260928/cash_action_evidence.csv \
  --cash-action-manifest data/local/r3_2_evidence_20260928/cash_action_evidence_manifest.json \
  --independent-calendar data/local/r3_2_evidence_20260928/xnys_exchange_calendars.csv \
  --independent-calendar-manifest data/local/r3_2_evidence_20260928/xnys_exchange_calendars_manifest.json \
  --curated-delisting-evidence data/local/r3_2_evidence_20260928/curated_delistings.json \
  --spdr-distributions-evidence data/local/r3_2_evidence_20260928/spdr-etf-historical-distributions.xlsx \
  --config config.r3.yaml \
  --output-directory data/local/r3_2_20260928 \
  --run-timestamp 2026-09-28T09:00:00+00:00
```

Artifact identities are: features `26de5d7251a6b4a756423983d129f2cc6cc476e00fbf9a61c3b3a03ece975ce5`; labels `bd29d570900e9bb834bdcc7c8bc98e0b2577c73d9dc2e1b22ec104f55e4a183f`; splits `c8baa44423fbc7cf750f70664fb67dc33731172ec55bd89a5faa02bb3109c612`; register file `14ead1a4cb523ca44963c54525819ffd09c24fb69694442436aa65fdd9a40d9c` with internal identity `9e8bc819b0b2bee66f74449f74da5c125bbceba33f656ae448489fb6a503ae3d`; dataset `146a66c923be4eeb0ea0af6f469d997b7ec23b6476feb4002116e8f3b3b1545b`; report `9a0cb013ef5645ef89c73fd7aa69a64e88bb1cb53d0a79a675472a6a09f7f973`; implementation tree `bd9311c58892d563171a1872d261b524d0964fa15a9f6588bed09f0cbf4e104d`. A second fixed-timestamp run reproduced all five written artifacts byte-for-byte.

Verification: targeted R3 evidence/materialization tests passed; the full suite passed 399 tests; `ruff check .` and `mypy src` passed; `python -m build` produced both sdist and wheel. The isolated build required network access to install its declared Hatchling build dependency. No performance claim was evaluated.

### R3.2 explicit scope-decision closure — 2026-09-28

The user explicitly decided to close R3.2 and move on without cash-action completeness, verified withholding, dated primary/common-stock classification, complete delisting recovery or vintage certification. This is a governance override for development sequencing, not an evidence result. It preserves the seven reported evidence limitations, does not manufacture values for 28,606 unresolved cash-action labels, and does not change `qualification_permitted: false`.

The decision is versioned in `config.r3.yaml` as `proceed_with_open_label_evidence`, dated 2026-09-28, with a note that R3.3 must not start in this change. The materializer records the original limitations separately from active development gates. The scope decision may waive the named evidence limitations, but it cannot waive the registered temporal-coverage requirement or permit outcome-conditioned deletion. Those conditions pass with nine complete 8/2/1 folds and zero cash-action rows dropped from the label artifact.

The final fixed-timestamp report records:

- `r3_2_phase_closed: true` with closure basis `explicit_scope_decision_with_open_label_evidence`;
- `development_training_blockers: []` while retaining all seven entries under `evidence_limitations`;
- `r3_3_development_training_permitted: true`, `r3_3_started: false`; and
- `qualification_permitted: false`.

The closure run used the reproduction command above with `--output-directory data/local/r3_2_20260928_closed_v2` and `--run-timestamp 2026-09-28T12:00:00+00:00`. Its physical config SHA-256 is `b72f8a2e4807c56c040fa68fa2e2d5144db8f2d2bec8450e406152a79bdcd846` and typed-config identity is `67426378b51b809612b8eb8b490935a7b756e4508caf945c87c05d8e5831aefd`. Artifact identities are: features `26de5d7251a6b4a756423983d129f2cc6cc476e00fbf9a61c3b3a03ece975ce5`; labels `bd29d570900e9bb834bdcc7c8bc98e0b2577c73d9dc2e1b22ec104f55e4a183f`; splits `c8baa44423fbc7cf750f70664fb67dc33731172ec55bd89a5faa02bb3109c612`; register file `d0df419fd04442851ee641d065eed8fc048155cf0481abbb5e1c700bd3305a31` with internal identity `9bcee477db9aa409c0cc411cb873183f4934c31ebb4c17fc01cd5d21c4e0e10d`; dataset `806e8a0daf945b44a44d491d8809ebd98e78e4d1c4dcf5b0f603ae569c9b9947`; report `fc4bbd80bb7f8317a01bf9543703c02b9bca3814c8efac8a1448c68a1c2d0a41`; implementation tree `77884a1db8edcd979c4045a191d368c3f3f5e1a9415111e103a87e66a6924385`. A second fixed-timestamp closure run reproduced all five written artifacts byte-for-byte.

**R3.2 is complete under the user's explicit scope decision.** No further R3.2 task is required before development can move to R3.3. This change stops at the phase boundary: it contains no learner, model fit, simulation or R3.3 trial.

Final closure verification passed: 400 tests, `ruff check .`, `mypy src` and `python -m build`; the build produced both sdist and wheel. Local documentation links and `git diff --check` also passed.

## R3.3 — Train ML now alongside the control

Implement ridge first, then shallow histogram gradient boosting using local CPU and a tested research dependency extra. Quarterly refits use only matured history. Run all three score families through the same monthly portfolio/account engine. Keep old V1/V2 engines and artifacts unchanged.

**Exit:** reproducible training/inference and causal simulation; full six-configuration development table, cost/exposure bridge, target attainment/loss distributions and paired uplift versus R3-M. ML is not gated on deterministic profitability. If every family fails development, publish failure and stop; no new tuning round is implicit.

### R3.3 implementation and failure record — 2026-09-29

Implemented separately from V1/V2:

- a tested `research` extra using NumPy 2.5.3 and scikit-learn 1.8.0;
- deterministic momentum scoring, training-only standardized Ridge at alphas 1/10/100, and shallow `HistGradientBoostingRegressor` at 7/15 leaves with the registered parameters;
- equal-date training weights, label-availability cutoffs, quarterly expanding refits, stable-ID tie breaks, model hashes and dependency manifests;
- one shared monthly raw-share GBP simulator with next-session-open fills, whole-share sizing, capacity and complete-round-trip cost guards, fixed fees, cash reserve, causal FX, corporate actions, volatility scaling, regime control, resize band, soft control and permanently latched hard halt; and
- all six registered trials, nine non-overlapping annual development cohorts, overlapping monthly cohorts, continuous accounts, cost/exposure bridges, target/loss distributions and paired bootstrap uplift.

The fixed-timestamp run used the closed R3.2 dataset identity `806e8a0daf945b44a44d491d8809ebd98e78e4d1c4dcf5b0f603ae569c9b9947` and split SHA-256 `c8baa44423fbc7cf750f70664fb67dc33731172ec55bd89a5faa02bb3109c612`. Every date remains previously inspected development history. The seven R3.2 evidence limitations, unverified tariff/permissions/operating costs and `qualification_permitted: false` remain unchanged.

Momentum was the strongest family on the nine non-overlapping annual cohorts: median all-in return 6.834991%, 4/9 strictly above 10%, 2/9 below zero, and worst account drawdown -11.327254%. It did not meet the >10% median/repeatability objective. Its continuous development account ended at £6,424.58 over the multi-year combined test sequence; that is not a one-year result or qualification evidence.

No learned configuration earned promotion. Paired median annual uplift versus R3-M was -6.432424% (Ridge alpha 1), -7.976829% (alpha 10), -9.151379% (alpha 100), -7.142461% (tree 7 leaves) and -4.877372% (tree 15 leaves). Every 95% lower bound was negative, target attainment was no better and drawdown was worse. Validation selected alpha 10 and 7 leaves within their families; the selected tree-versus-Ridge median uplift was +1.669856%, but its 95% lower bound was -2.485295%, so it also failed promotion.

All nine non-overlapping Ridge and momentum accounts were executable under the development assumptions. Both tree trials retained an invalid annual account because a split generated an unsupported fractional residual. Some overlapping alpha-10/alpha-100 cohorts also failed on the known 2015-03-24 missing held valuation. Those failures remain in the report; no price, cash-in-lieu or recovery was fabricated. Consequently `r3_3_research_accepted: false`.

Reproduction (outputs remain ignored):

```bash
python -m src.cli.r3_development \
  --r3-dataset data/local/r3_2_20260928_closed_v2 \
  --canonical-manifest data/local/phase3_build_v3/canonical/canonical_manifest.json \
  --calendar data/local/phase3_v2/calendar.csv \
  --fx-csv data/local/r3_2_evidence_20260928/gbp_usd_ecb.csv \
  --fx-manifest data/local/r3_2_evidence_20260928/gbp_usd_ecb_manifest.json \
  --cash-action-evidence data/local/r3_2_evidence_20260928/cash_action_evidence.csv \
  --cash-action-manifest data/local/r3_2_evidence_20260928/cash_action_evidence_manifest.json \
  --config config.r3.yaml \
  --development-config config.r3-development.yaml \
  --output-directory data/local/r3_3_20260929 \
  --run-timestamp 2026-09-29T09:00:00+00:00
```

Top-level artifact SHA-256 values are: development report `01f80f4357205733a9fe6f2ac92aeff6b3e231ef68c51b93ccce6f7cc379957c`; completed experiment register `66bb3bb9dfb3d43c886d43545719b25bbd7c43a9128776776d318cfc398c350f`; and 541-entry model manifest `b83288126534369ee0f6b6d1ec4c1f98c2e60b5f701e0030f5c6dacf9e36c65b`. A second fixed-timestamp run reproduced all three top-level artifacts and every referenced model file byte-for-byte. The report binds implementation tree `33fae3039f7f344b19d3755104229d2c270e54eaa856cb2ed94d84abdf63aa0b`, Python 3.12.14, seed 20260926 and the dependency versions.

Targeted R3 tests passed, followed by 410 full-suite tests. `ruff check .` and strict `mypy src` passed. The isolated package build produced both the sdist and wheel; it required network access to install the declared Hatchling build dependency. Local documentation links, secret-pattern review and `git diff --check` passed.

R3.3 implementation acceptance passes, but research acceptance fails. Per the predeclared stop rule there is no implicit tuning round and R3.4 is not permitted. The next actionable task is a review-only closure decision: preserve the failed register and decide whether to stop active research or explicitly register a materially new research question. It must not reinterpret these results, select a sensitivity neighbor or access a purported fresh holdout.

## R3.4 — Review, freeze and evaluate unseen observations

Review the code, data and complete trial ledger. Run all registered stresses, ablations and eight sensitivity neighbors, with every failure retained. Freeze the chosen recipe only if development supports it. Register an untouched test and its endpoints. No inspected 2021–2026 period is a fresh R3 holdout; earlier inspected training periods are not fresh either.

**Exit:** all BACKTEST_AND_VALIDATION gates, including the first fixed 12-month result, retained minimum 756 fresh sessions, trade/episode minima and uncertainty checks. New forward evidence may take years. No claim that a few weeks of coding or one year of monitoring can complete the full qualification contract. Failure/inconclusive evidence blocks advancement.

## R3.5 — Paper execution only after qualification

Implement reconciliation and durable idempotent intents before any order transport. Test partial fills, rejects, timeout/restart, stale prices, action handling, settlement/cash, kill switch and independent risk controls. Run >=60 trading sessions in paper mode, with no unexplained differences between target, order, fill and portfolio.

**Exit:** operational gate passed and separately documented authorization for any live step. Paper performance is not proof of the one-year objective.

## R3.6 — Explicitly authorized small-capital live evaluation

Deploy with initial £3,000 only after that account scenario qualifies and the user gives exact live-order authorization. Preserve every invariant and audit every fill. Measure the actual first-year net outcome without counting deposits as profit. A missed target is reported as failure; no automatic restart after a halt or increase in capital to repair performance. Consider increases only after >=6 months of operational stability and review.

## Deliverable discipline

Each implementation change must state its stage, edit only the required modules/config/tests, run targeted then broader checks, and publish evidence plus unresolved limits. Generated reports/models stay ignored; update a short tracked decision record with hashes. No subscriptions, scheduled tasks, background monitoring, broker integration or model training are started by this documentation revision.

R3.3 reached its stop condition. R3.4, broker integration and execution remain out of scope and unauthorized. Any further strategy work requires an explicit new registration and scope decision; no automatic tuning or sensitivity search is permitted.
