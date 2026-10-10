# Next research cycle: causal evaluation and richer stock selection

Recorded: 2026-10-02; updated 2026-10-07. Status: **steps 1–3 complete; corrected controls rejected; source feasibility failed; bounded source remediation started; Step 4 not ready**. This brief captures the strategy review following the failed R3.3 experiment and is the controlling sequence for the next research work.

The user's 2026-10-04 continuation request authorizes bounded public-source remediation. The [source-remediation record](SOURCE_REMEDIATION.md) describes the implemented cover extractor, three-issuer evidence audit, historical SIC route, verification and remaining blockers. This supersedes the earlier requirement to ask again for that bounded work; it does not infer a protocol amendment or authorize unregistered model selection.

The user approved a separately registered later-period design on 2026-10-07. See [LATER_PERIOD_DESIGN.md](LATER_PERIOD_DESIGN.md) for the implemented calendar/coverage planner, exact six-fold boundaries and remaining source gates. Initial 8/2/1 durations and risk rules remain unchanged. This is a period-design registration; the Step 4 model-trial registration remains pending data readiness.

The user has requested completion of the remaining R3 work. The [current completion record](R3_COMPLETION_PROGRESS.md) documents the full 793-identity universe audit, public-source discovery, pending acquisition needs and the unaltered forward-evidence gates. Offline continuation is authorized; R3 is not complete and no new model has been fitted.

## Objective and scope

Investigate whether cost-aware stock selection combining momentum with point-in-time company fundamentals can improve the probability of earning **more than 10% all-in GBP return within one year on £3,000**. Net profit must exceed £300 and terminal wealth must exceed £3,300 without additional funding. This is an objective, not a forecast or guarantee.

Retain Ridge as a regularized linear control and use XGBoost as the principal proposed nonlinear challenger. First correct the evaluation issue below and re-establish the controls. Model complexity alone is not the research hypothesis.

This document supplements the [strategy review](STRATEGY_REVIEW.md) and [roadmap](ROADMAP.md). It does not reopen the completed R3.3 trial budget, authorize R3.4, replace the [validation contract](BACKTEST_AND_VALIDATION.md), or change the [risk contract](RISK_AND_EXECUTION.md). A subsequent implementation request should establish a separately versioned research registration before new model selection. No new config filename, CLI, dependency or model is implemented by this brief.

## Evidence and its limits

The reviewed local `data/local/r3_3_20260929/development_report.json` matched recorded SHA-256 `01f80f4357205733a9fe6f2ac92aeff6b3e231ef68c51b93ccce6f7cc379957c`.

| Recorded candidate | Executed fills | Cohorts strictly above 10% | Median one-year return |
| --- | ---: | ---: | ---: |
| Momentum | 288 | 4/9 | 6.83% |
| Ridge alpha 1 | 370 | 0/9 | 0.57% |
| Ridge alpha 10 | 361 | 2/9 | 0.57% |
| Ridge alpha 100 | 329 | 1/9 | -0.65% |
| HGB, 7 leaves | 384 | 2/8 valid accounts | 4.57% |
| HGB, 15 leaves | 431 | 2/8 valid accounts | 5.54% |

Each HGB trial attempted nine annual accounts; one failed on an unsupported fractional split residual. Its displayed fills and statistics cover valid accounts only. Those failures must remain visible, and the eight-account medians are not directly comparable to nine-account medians without matched-account analysis and explicit failure reporting.

Recorded mean exposure was approximately 28–33% across candidates. Momentum and Ridge alpha 10 had similar exposure (32.6% and 31.2%), but Ridge also had a weaker aggregate gross outcome. Costs alone do not explain its underperformance. Attribute idle capital and return differences before choosing portfolio changes.

All results are inspected development evidence and are additionally subject to the selection issue below. Nine annual cohorts offer limited independent evidence; overlapping monthly cohorts and correlated stock rows do not supply independent investment years. Existing data, tariff, permission and operating-cost limitations carry forward. No candidate demonstrated the objective or earned promotion.

## First priority: remove future-label dependence from scoring

Code inspection found a discrepancy with the intended causal specification:

1. [`build_r3_split_assignments`](../src/validation/r3_splits.py) constructs assignments only from matured, available labels.
2. [`_score_segment`](../src/research/r3_development.py) uses those assignments as scoring keys, including validation and test segments.
3. The [simulator](../src/backtest/r3.py) selects from the supplied scores and can treat a held stock absent from them as a mandatory exit.

Thus eventual future-label completeness influences historical eligibility and potentially exits. Retaining unresolved labels in an artifact does not eliminate the bias from excluding those securities from scoring. The direction and numerical impact are **unmeasured**; this finding is based on code inspection, not a corrected rerun. The review's attempted Parquet row-count check could not run because the local virtual environment lacked `pyarrow`.

Required correction:

- Derive decision dates and scoring universes from contemporaneous feature eligibility, membership and source availability, independently of eventual label resolution.
- Apply label maturation and interval purging to fitting and supervised evaluation; keep feature eligibility separate from label availability.
- Score all contemporaneously eligible stocks even when their eventual return label is unresolved. Keep unresolved outcomes explicit; do not invent a price, payment or recovery to complete the account.
- Distinguish an intentionally ineligible stock from missing/stale model output; apply the documented failure policy rather than accidentally generating exits through a filtered score set.
- Report missing-label coverage by date and security, and by sector/dividend status where causal metadata supports it. Incomplete training labels can still introduce coverage bias after scoring is repaired.
- Add mutation tests: changing future label values or availability must not change earlier eligibility, scores, or orders; a later refit may change only when new labels have legitimately matured. Test actual label overlap, missing scores, held valuations and action failures separately.

Preserve old artifacts and their hashes. Produce a separately identified correction run and explain differences; do not overwrite or re-sign the old evidence. Obtain explicit action evidence for split residuals/cash-in-lieu where possible; otherwise retain failed accounts and block qualification.

### Step 1 implementation record — 2026-10-02

The diagnosis above was confirmed and the evaluator contract was corrected. `splits.parquet` remains the matured-label, actual-interval-purged supervised contract. A new, separately hash-bound `scoring.parquet` contract is generated only from contemporaneously usable feature rows and chronological fold windows. The development loader now requires `r3.2-development-dataset-v2-label-independent-scoring`, exposes separate supervised and scoring keys, and refuses the old artifact contract rather than silently reusing it. Model refits still admit only targets whose recorded availability timestamp is at or before the refit cutoff.

The simulator now receives eligibility separately from predictions. A genuinely ineligible holding queues a mandatory exit; a missing or partial model score set blocks model-driven increases without manufacturing an eligibility exit; an unresolved held valuation still fails the account closed. Hard/soft drawdown controls, next-session execution, position/gross/cash limits and continuous halt state were not relaxed. The materialization report records label availability by decision date, security and dividend-affected status; sector coverage is explicitly unavailable because the current artifact has no point-in-time sector metadata.

Verification used synthetic fixtures for correctness only. The focused R3 scoring/split/loader/refit/backtest set passed 23 tests. The full suite passed 416 tests; `ruff check .` and `mypy src` passed; and the sdist/wheel package build passed using the declared Hatchling backend. A bounded end-to-end fixture produced the same eligibility, score and fills after changing an unresolved label to a value available only in the future. These checks are not investment evidence.

At the step 1 checkpoint, no original dataset, report, fitted model or experiment record had been changed or re-signed, and no corrected real-data comparison had run. Existing R3.3 outcomes remained preserved rejected evidence with then-unmeasured sensitivity to the corrected evaluator. Open data, action, tariff, permission and operating-cost limitations carried forward into step 2.

### Step 2 corrected-control record — 2026-10-02

Step 2 used dataset directory `data/local/r3_2_20261002_corrected_v2` and run directory `data/local/r3_3_20261002_corrected_v2`, both ignored. The dataset identity is `bc01ebab574bb847d46781b090b01cd58c6757e3ed3b2ef99d39f052f209259a`; physical hashes are features `26de5d7251a6b4a756423983d129f2cc6cc476e00fbf9a61c3b3a03ece975ce5`, labels `bd29d570900e9bb834bdcc7c8bc98e0b2577c73d9dc2e1b22ec104f55e4a183f`, splits `c8baa44423fbc7cf750f70664fb67dc33731172ec55bd89a5faa02bb3109c612`, scoring `8f74da29f3b94e45ab92931a6e77b328ff758b3a52561a86f802851311e9f997`, register `c7800f46c7105a5cd60947af018c5e15cf1348d9bc62bd767a6f1ced14913fcf` and report `aff78c486855a629bcfc6dfffe4a720612f5b535fc5f3fd08e2324a50268c8e6`. A fixed-timestamp repeat reproduced all six files byte-for-byte.

The audit reconciled 133,141 feature rows into 121,291 usable and 11,850 excluded rows. All usable rows have retained labels: 91,546 matured and 29,745 unresolved. The scoring contract contains 1,254,240 fold assignments versus 919,992 supervised assignments. Every scoring universe exactly matched usable contemporaneous feature rows; every supervised row had a value and availability timestamp; same-date grouping held. Folds 0–8 retained all registered 8/2/1 coverage with actual label-interval and 31-session boundary purging. Dividend-affected labels were 4,898 available and 27,027 unresolved; other labels were 86,648 available and 2,718 unresolved. Sector coverage remains unavailable because no causal point-in-time sector metadata exists.

The six candidates ran together once with identical scoring dates/universes, portfolio policy, costs, risk controls and seed. Frequencies below use all nine attempted annual accounts; medians and wealth aggregates necessarily use only accounts with resolved terminal wealth.

| Candidate | Valid annual accounts | Valid-account median R12 | Target / 9 | Loss / 9 | Worst drawdown | Mean exposure | Fills (mandatory) | Turnover / initial capital |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Momentum | 8/9 | -1.975435% | 3/9 | 5/9 | -13.709570% | 31.6748% | 210 (78) | 2.2963x |
| Ridge alpha 1 | 7/9 | 0.264122% | 0/9 | 2/9 | -14.735000% | 29.6802% | 273 (114) | 3.0403x |
| Ridge alpha 10 | 7/9 | 6.770086% | 0/9 | 2/9 | -16.019857% | 27.3850% | 277 (122) | 3.1490x |
| Ridge alpha 100 | 6/9 | 7.458705% | 3/9 | 2/9 | -15.113551% | 26.1000% | 213 (89) | 2.2629x |
| HGB, 7 leaves | 6/9 | 5.394361% | 2/9 | 2/9 | -16.174753% | 31.9062% | 327 (143) | 3.6999x |
| HGB, 15 leaves | 5/9 | 0.291698% | 1/9 | 2/9 | -15.529091% | 31.4789% | 335 (147) | 3.7845x |

Valid annual-account aggregate GBP bridges were: Momentum £25,494.06 gross, £25,287.70 trading-net and £24,999.70 all-in; Ridge 1 £21,944.21, £21,699.06 and £21,447.06; Ridge 10 £21,735.14, £21,483.00 and £21,231.00; Ridge 100 £19,153.95, £18,952.19 and £18,736.19; HGB 7 £19,286.72, £18,999.41 and £18,783.41; HGB 15 £15,597.79, £15,328.07 and £15,148.07. The report separately records commissions, slippage, FX friction, conversion costs, £3 monthly account fees, zero configured operating cost, £5.03-per-valid-account liquidation reserves and unresolved accruals. Mean cash weights were 68.09%–73.90%, confirming substantial idle capital; raw skip counts are interaction diagnostics, not causal attribution.

Every validation, annual, monthly-overlapping and continuous attempt is present in the report. Across 115 attempts per candidate, invalid counts were Momentum 16, Ridge 1 27, Ridge 10 26, Ridge 100 42, HGB 7 42 and HGB 15 50. Reasons are retained per account. They comprise unresolved held-delisting recovery; missing held valuations or target opens; and, for tree controls, unsupported fractional split residuals. There were no recorded missing-model-output, missing-covariance, missing-regime or fee-affordability failures. The only affordability skip was one Ridge-1 cash-buffer/fee-reserve skip; round-trip-cost and mandatory position/gross reductions remain separately counted. Momentum and both tree continuous accounts failed closed; the three Ridge continuous accounts completed but spent about 71% of sessions halted and ended below initial capital.

Against preserved R3.3, valid-account median changes were -8.810426 percentage points for Momentum, -0.304305 for Ridge 1, +6.201659 for Ridge 10, +8.108700 for Ridge 100, +0.826120 for HGB 7 and -5.244445 for HGB 15. Annual fills changed by -78, -97, -84, -116, -57 and -96 respectively. Exposure changes ranged from -3.8380 to +1.5482 percentage points. The preserved run did not record per-account scores, selections, mandatory fills or account identifiers, so an exact old-side account/selection pairing cannot be reconstructed without rerunning or modifying rejected evidence; no such rerun was performed. Candidate IDs, fold cohorts and all available aggregate measures were matched. Features, labels, splits, configs, sources, Python, dependencies and seed match; the added 10,087 test scoring rows and resulting selections/exits/failures are evaluator-correction effects, not an independent sample or unrelated data refresh.

The corrected run hashes are report `2f3a4f6035b915203eed5ecc1cc6a4a5d5b6129010a932f42d86791c291b0dba`, completed register `a343096d9ed3f46d6db1e361721f3aadc39d67524a5191b13b83794872fb1bee` and 541-entry model manifest `0aa01c3c497e01d35f5623895a5b6d0b6709474f8de5e5f403d11437dc6824d9`; every referenced model hash validates. The run binds implementation tree `325e9ae83853fbbfebf2c139af2b0789a3e73f7073704420fa95a1c3b9ea53dd`, Python 3.12.14, seed 20260926 and dependency versions. All 544 preserved R3.3 files remained byte-identical, including report `01f80f4357205733a9fe6f2ac92aeff6b3e231ef68c51b93ccce6f7cc379957c`, register `66bb3bb9dfb3d43c886d43545719b25bbd7c43a9128776776d318cfc398c350f` and model manifest `b83288126534369ee0f6b6d1ec4c1f98c2e60b5f701e0030f5c6dacf9e36c65b`.

Verification passed 24 focused R3 tests and all 417 repository tests. `ruff check .`, strict `mypy src` and the isolated package build passed; the build produced the sdist and wheel with Hatchling 1.32.4. The build initially confirmed that the research environment intentionally lacked the backend, then the declared isolated build fetched it. Documentation links, `git diff --check`, ignored-artifact checks and secret-pattern review were run after the final edits.

No candidate supports advancement or promotion. These dates remain inspected development data; the corrected results are not independent of R3.3, fresh evidence, qualification, deployability or proof of the investment objective. Open action, valuation, source-permission, tariff and account-permission limitations remain. At the Step 2 checkpoint the next decision was whether to authorize Step 3; the completed Step 3 decision follows.

### Step 3 source-feasibility decision — 2026-10-02

Step 3 audited a predeclared 11-issuer sample, seed `20261002`, covering stable issuers, Meta's ticker/name change, Alphabet and Berkshire share-class/symbol complications, Activision and Twitter acquisitions/delistings, amendments, different fiscal years, negative facts and duplicate contexts/units. The immutable ignored raw archive contains 46 sequential public responses: SEC submissions/companyfacts resources and historical shards, three representative primary filings, and official SEC/ALFRED access documentation. Every URL, retrieval timestamp, byte length and SHA-256 is recorded. No account, credential, purchase or paid term was used.

The transform retained 15,855 filing-specific facts across 11 concepts. Each value is bound to CIK, accession, form, actual SEC acceptance timestamp, acceptance-plus-24-hour availability, fiscal period, period end, unit, taxonomy, source hash and transform version. Quarterly, year-to-date, annual and instant facts remain distinct; negative values are retained; unmatched acceptance timestamps are excluded; amendments are later information; and same-context/unit conflicts remain explicit. Coverage applies a 550-day stale limit. The sample contained 47 amendments among 1,175 audited filings and 653 after-hours filing acceptances; the audit separately counts facts whose 24-hour latency crosses a UTC month boundary. Three recent Apple, Alphabet and GE accessions were reconciled to hash-bound primary inline-XBRL filings.

Causal sampled fact availability begins 2009-07-23, versus the frozen price-only start of 1999-01-29. Consequently **0/9** existing 8/2/1 folds support complete enriched history without fabrication. Three sampled issuer joins map one CIK to multiple local security IDs: Alphabet's two classes, Meta's overlapping/ticker history and Berkshire's `BRK-B`/`BRK.B` variants. The audit has no authoritative dated CIK-to-share-class mapping, so even the one-to-one sample joins remain manual and non-qualification-grade. No causal dated sector source was established. ALFRED documentation is public, but vintage-observation API access requires an unsupplied key; it was not attempted. SEC access was public/no-auth and incurred no observed charge during this audit; ALFRED, sector metadata and the complete recurring budget remain unknown. Existing local storage/CPU and no hosting are £0 assumptions, not vendor quotes.

The 28-feature candidate contract retains 11 price-derived definitions for future design discussion and rejects 17: three sector-relative, eight SEC-history-dependent, three valuation/share-count identity-dependent and three macro-vintage features. Each definition fixes its formula, horizon, inputs, availability, missingness, training-only transform, cross-section and source status. These are feasibility classifications, not return-selected features.

The immutable package is `data/local/r3_step3_20261002_feasibility_v7`, with package identity `71d4edd34fa74901de340b7a33080c8119f8f5cd4170d46c644db500da8dc21f`. Key SHA-256 values are source-access manifest `b228027e608053095e6ce060c4e286a60d7686365716dffcf196c39168b49dcf`, filing/fact audit `422c1c63d977f757dbb510844da6c1accae27e80ce85e599dbb387bd169ca48e`, coverage `d7e52eb0b82a5a6902c649c72c13f9383519c3c2821c8edf654b29aeca055f7a`, feature contract `77236954e6179d2cfc9615670c2798348be2a37aea1fefd14ce92fb683fea39f`, cost budget `17bd91d48ebc964a7e042b0b9c8a891c2930f846f4d60c74da73c647cdf12a6d` and failure register `eaee6bb71df9f7483ceb2cbbbad80192733f6ce2e3e812ed109634e1fc96e25d`. A fixed-input reproduction generated every artifact byte-for-byte. It contains `failure_register.json`, not a Step 4 experiment register. Step 3 is complete with an explicit stop: no model fitting, scoring, simulation, candidate selection or performance evaluation occurred. A future protocol change or identity/source remediation requires a separate explicit decision; Step 4 is not authorized.

### Post-Step-3 remediation/governance decision — 2026-10-03

The ignored immutable package `data/local/r3_post_step3_20261003_decision_v1` has identity `45ca6a6c89ecd5fd0640d58aa5e91aaec03ac5a2b6ca65d41f5c0dc224cbf394`. Its artifact-manifest SHA-256 is `7c6acf6b69edc84cf27204d7e12d5b20cb94af140bae9a06290d664d6038cf1e`; key record hashes are preserved-evidence verification `48f0d40ca0764d7dfe39149598b0253752a3d51c892a0125e984bba30c420182`, blocker traceability `4a41eea08e6e9d11fc272be487275534264b3c88cccc0c566bb04a2ea58e5c1e`, identity requirements `ebf462435b0eb1ac87c1ee155a30739cef8c2a2fbbc5d18c20caef03a3ac5e6a`, date support `5aa839392784819518f9827ba2e03984c27666c64d6ccdacbffb4f12801782e9` and governance options `bd74b09d5248850d7474514bd6c038fc8cc0caa9baede416dbff2e9a3ffd9f36`. A second ignored directory reproduced every file byte-for-byte.

The package selects the bounded disposition of defining prerequisites before any separately authorized amendment can be considered. It records exactly three unranked governance options:

- **A — stop enriched-feature research.** This may proceed without further authority because it performs no new work or access.
- **B — remediate identity, sector and macro evidence while retaining the protocol.** This requires explicit new authority and cannot solve the independent SEC-history blocker: facts still begin no earlier than the sampled 2009-07-23 date.
- **C — produce a separate future protocol-amendment decision package.** This requires explicit user authorization and complete remediation evidence; it is not an amendment and cannot inspect outcomes or register an experiment.

The 3,828-day pre-coverage gap leaves 0/9 frozen folds enriched. Training-only imputation is suitable only for sporadic missingness after real causal observations exist; it cannot manufacture a pre-2009 fundamental history. Sample-only calendar arithmetic puts the earliest prospective enriched training start at 2009-07-23, nominal eight-year training end at 2017-07-23, two-year validation end at 2019-07-23 and one-year test end at 2020-07-23. Those are lower-bound planning dates, not exact XNYS fold boundaries, evidence of full-universe coverage or approval to change the protocol.

The current local master cannot be repaired from existing evidence alone. Any remediation needs dated issuer/security/class and symbol intervals, evidenced continuity through ticker/name changes, separate simultaneous classes, predecessor/successor and delisting/action records, access timestamps, permissions and prefix-invariant fail-closed tests. Current metadata is explicitly forbidden as historical mapping evidence. Dated sector metadata remains rejected under the current protocol. Frozen official ALFRED documentation states that web-service access requires a registered key and login; it established no public no-account vintage-observation bulk route. No credential, account, subscription, purchase or terms acceptance occurred, and revised FRED history remains an invalid substitute.

Only bounded SEC read-only access was observed at £0. Local compute/storage at £0 remains an assumption. Identity, sector, ALFRED operating and complete recurring costs remain unknown; no affordability conclusion was drawn. The protocol, labels, folds, portfolio policy, risk controls, source contract and candidate budget are unchanged. No Step 4 registration, model fit, score, simulation, backtest, performance comparison, candidate selection, fresh holdout access or broker/account action occurred. Step 4 remains unauthorized.

Verification passed all 11 focused decision-package tests, Ruff, strict mypy for the three new source files, the isolated sdist/wheel build, local documentation links, `git diff --check`, ignored-output checks, artifact-integrity checks and the scoped secret-pattern scan. The fixed-input reproduction matched all 12 files byte-for-byte. The full repository suite completed with 433 passes, five failures and one skip: all five failures are existing R3 learning tests blocked before fitting because this runtime lacks the declared optional `scikit-learn` research dependency; the skip lacks optional `exchange_calendars`. Full `mypy src` is likewise not green: it reports eight import/unused-ignore diagnostics at the existing sklearn imports, while the new files pass strict checking. No dependency was added merely to turn those environment checks green.

Remaining limitations are evidence limitations, not implementation omissions: the SEC date is sampled rather than full-universe complete-case coverage; prospective boundaries are calendar lower bounds rather than exact exchange-session folds; no qualifying identity or sector source has been selected; no ALFRED observations were accessed; permissions and recurring costs remain incomplete; and the pre-existing dirty Step 3/R3 worktree was preserved rather than normalized.

## Model rationale

Ridge was a reasonable first baseline for a small set of correlated momentum, volatility and market features: regularization limits coefficient magnitude and the additive model is inspectable. It was not established as the best investment model. See [Ridge documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).

There is a specific limitation to the current feature/model combination. Market return, volatility and trend are identical across stocks at one decision date. In additive Ridge their contributions shift all predictions equally and cannot directly change that date's ranking. Explicit stock-feature interactions with market state are needed for conditional rankings. Examples include momentum × market volatility and beta × market trend.

XGBoost can learn nonlinear interactions and provides regularization and row/feature subsampling. However, HGB already tested boosted trees; replacing it with XGBoost on the same inputs is not evidence of a new source of predictive value. See [XGBoost parameters](https://xgboost.readthedocs.io/en/stable/parameter.html).

The proposed hypothesis is: **relative price behaviour and company fundamentals contain complementary information that a regularized nonlinear model can combine into better selections after costs**.

Start with regression on the same one-month label to isolate model effects. A later, separately registered ranking experiment may group stocks by decision date and optimize relative ordering. Specify label/relevance construction and date weights; do not blindly use information-retrieval defaults. Ranking scores are not expected returns and must not be compared directly with transaction costs. See [XGBoost ranking documentation](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html).

Keep the initial hyperparameter budget small and explicit. Use shallow trees, regularization and chronological validation for any early stopping. Define weight normalization: the existing inverse cross-section date weights affect the scale of regularization and XGBoost's Hessian-based `min_child_weight`. Do not equate that parameter with HGB's unweighted leaf-row count. Do not add neural networks, reinforcement learning, intraday execution or broad automated searches to this cycle.

## Feature and data priorities

Aim initially for approximately 20–30 additional, economically motivated features. Freeze exact formulas, horizons, availability rules and missing-data handling before evaluating returns. This is a bounded design target, not permission to select the best-looking features from repeated trials.

| Priority | Family | Proposed features | Required inputs and hypothesis |
| --- | --- | --- | --- |
| 1 | Relative momentum | Sector-relative momentum, market-residual momentum, cross-sectional momentum ranks | Existing prices and dated sector classifications; separate stock strength from market/sector exposure |
| 1 | Risk and trading behaviour | Downside and residual volatility, beta, overnight-gap frequency, volume surprise | Existing causal bars; distinguish persistent trends from unstable price moves |
| 2 | Profitability and cash quality | Gross profit/assets, operating cash flow/assets, accruals, margin change | Historical filings; test whether operating performance supports price strength |
| 2 | Valuation and balance sheet | Earnings yield, cash-flow yield, leverage, share-count growth | Filings and contemporaneous market capitalization; distinguish quality from expensive or fragile growth |
| 2 | Operating change | Year-over-year sales growth, profitability change, days since filing | Actual filing availability; test new operating information |
| 3 | Economic conditions | Yield-curve slope, credit-spread changes, vintage inflation measures | Dated releases/market observations; condition stock signals on economic conditions |

Fit learned preprocessing and imputation on training only. Same-date ranks may use only the eligible contemporaneous cross-section. Specify robust handling of negative earnings, zero denominators, accounting differences and missing coverage. Never substitute present-day sectors, shares outstanding or market capitalization for historical values.

### SEC EDGAR first

Investigate [SEC filing-history and XBRL APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) as the first new external source. They provide raw ingredients, not an automatically point-in-time research dataset.

Bind each value to the filing accession, actual acceptance/public availability timestamp, fiscal period, unit, taxonomy, source hash and transform version. Account for publication/processing latency. Handle amendments and restatements as later information, not replacements available at the original period end. Map issuers to stable security identities, including historical changes and multiple share classes. Audit representative joins manually.

Mandatory XBRL began in 2009. Establish actual usable history and coverage before promising the existing 8/2/1 folds. Do not fabricate pre-coverage fundamentals, backfill with later filings, or silently shorten the validation protocol. If history is insufficient, report it and explicitly register any prospective protocol amendment before examining outcomes; it does not relax qualification gates by implication.

### Macro vintages and deferred sources

Use [ALFRED vintages](https://fred.stlouisfed.org/docs/api/fred/alfred.html) for revised economic series, with explicit release-time availability. Latest revised history is not what investors knew then. Shared macro variables need interactions to affect an additive model's cross-sectional ranking.

Defer news sentiment, social data and analyst estimates until a specific incremental hypothesis and affordable, timestamped historical source are established. No subscriptions or purchases are implied. Preserve source terms, licenses or their absence, provenance and redistribution limitations. Existing permission to use unclear-license data for local development does not make it qualification-grade.

## Ordered work packages and exits

| Step | Deliverable | Exit condition |
| --- | --- | --- |
| 1. Evaluation repair — complete 2026-10-02 | Separate feature/scoring eligibility from matured training labels; regression and mutation tests; failure audit | Implemented and verified with synthetic fixtures; no historical performance inference |
| 2. Corrected controls — complete 2026-10-02 | New immutable momentum/Ridge/HGB reports using the repaired evaluator | Corrected controls retained and reconciled; no candidate advanced |
| 3. Source feasibility and registration | Audited sample of filings/identity/availability joins, coverage and cost budget; bounded model/feature trial register | Enough causal history for the declared protocol; dependencies, formulas, trials, splits and selection rules fixed before selection |
| 4. Information-versus-model experiment | Original/enriched feature comparison with Ridge and XGBoost; corrected momentum/HGB references | Comparable dates, universe, risk policy and costs; full failed/successful trial record and feature-group ablations |
| 5. Optional separate horizon experiment | Three-month labels and a predeclared lower-turnover policy with monthly monitoring | Separate registration; actual overlap purging and maturation; no relaxation of mandatory risk reductions |
| 6. Research decision | Reject, mark inconclusive, or propose a frozen recipe for the existing qualification process | Complete evidence against objective, controls and passive opportunity-cost reference; no automatic advancement |

Before step 4, register the exact candidate count and hyperparameters, allowed feature groups, seeds, refit schedule, costs, validation selection rules and uncertainty method. Compare original and enriched models over the same supported dates and universe; separately disclose coverage losses so data-source selection is not mislabeled as model uplift. Never choose the candidate using an outer test, even when that period is already development data.

Attribute idle capital to the market overlay, volatility sizing, whole-share rounding, economic order floor, fee reserves, missing data/scores and halt state. Distinguish interactions between constraints and do not interpret raw exclusion counts as causal attribution. Fix correctness issues before evaluating whether a portfolio-policy change is justified.

The slower-horizon proposal is an optional distinct question, not a simultaneous change to the initial comparison. Lower turnover is a hypothesis. A three-month label does not permit waiting through mandatory exits or resetting risk state.

## Economics, success criteria and stop conditions

- Evaluate the actual £3,000 account after execution, FX, account and recurring operating costs. Verify commission offsets rather than silently double counting or omitting them. Record research expenditure separately and debit it when funded from starting capital.
- An illustrative £10/month subscription consumes £120/year, or 4% of initial capital. This is arithmetic, not a vendor quote. New information must justify its full incremental cost.
- Report one-year cohort outcomes, target attainment, losses, uncertainty, worst drawdown, time halted, turnover, exposure and gross-to-net reconciliation. Include every attempted account and explain invalid accounts; no success rate based only on survivors presented as overall attainment.
- Preserve the existing ML promotion threshold: at least 2 percentage points higher paired median annual net return than momentum, no lower target attainment, no worse maximum drawdown, and a positive 95% lower confidence bound for mean paired annual excess return. Require the nonlinear challenger to justify itself against the registered linear control as well. Insufficient independent periods means inconclusive, not a pass.
- Retain a costed, comparable risk-budget broad-equity reference and a low-turnover diversified opportunity-cost reference. Verify any investable instrument's ISA accessibility and costs; do not assume SPY is purchasable. Benchmark exemptions from stock caps do not alter strategy limits.
- Feature importance, prediction error, rank correlation and top-ranked-stock diagnostics help explain behaviour; none substitutes for account-level net performance.
- Stop if evidence cannot support causal evaluation, necessary data is unaffordable, all candidates fail, or apparent gains are unstable or disappear after costs. Do not respond by adding an unregistered search round.
- All inspected history stays development data, including corrected reruns and new-vendor versions. Fresh evaluation requires a frozen recipe and documented non-access or forward observations. The existing qualification and paper/live gates remain applicable; this brief does not compress their timeline.

## Non-negotiable safety and evidence discipline

Preserve long-only equities, no leverage/margin/shorting/derivatives, at most five stocks, at most 30% per stock, gross at most 100%, the configured cash/fee reserves, 10% soft drawdown control and permanent 15% halt. The halt cannot guarantee maximum realized loss. Carry state and high-water marks across folds/refits for continuous accounts. Mandatory reductions bypass discretionary bands/minimums and do not create unrelated buys.

Keep stale/missing data and model failure fail-closed for new risk. Derive holdings from fills, not submissions. Do not connect to live accounts or change broker state. Reconciliation, idempotency, qualification, paper gates and exact user authorization still precede eventual live orders.

For each implementation change, follow [AGENTS.md](../AGENTS.md): inspect status/specifications, make a narrow reviewable change, run targeted tests then `pytest`, `ruff check .`, `mypy src` and a package build, and report actual results and unrun checks. Check installed dependencies first. Record Git commit/tree, config/data/universe/calendar/cost/model hashes, environment, seeds and timestamps. Keep raw data, reports, models and credentials out of Git and preserve all failed trials.

## Next decision

The post-Step-3 package is complete. Bounded public-source work under Option B is now authorized and has begun; see [the 2026-10-04 record](SOURCE_REMEDIATION.md). Continue resolving historical identity, source availability and costs within that scope. A choice between later-period, older-source or price-only research is pending; no protocol amendment, Step 4 registration or performance experiment has begun.
