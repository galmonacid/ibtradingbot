# Current experiment: momentum, Ridge and XGBoost

Registered design: 2026-10-10. Authorization: the user requested faster iterations and explicitly confirmed XGBoost **alongside Ridge**, without a preceding Ridge acceptance gate. The [roadmap](ROADMAP.md) controls the working policy; this file specifies the current experiment rather than repeating historical progress.

## Question and budget

On the available causal price/volume/market features, does a shallow nonlinear estimator show a useful ranking difference from a linear control and momentum? This isolates estimator effects; fundamental enrichment is a separate next hypothesis, not claimed as implemented here.

| Family | Fixed configuration |
| --- | --- |
| Momentum | Existing 252-session momentum skipping 21 sessions |
| Ridge | Training-only weighted standardization; alpha 10 |
| XGBoost | Squared-error regression; 100 trees, depth 3, learning rate 0.05, minimum child weight 100, L2 10, L1 0; full row/column sampling; CPU histogram method, one thread |

Exactly three candidates, no search and no early stopping. Seed 20261010. Parameters are fixed in [configuration](../config.r3-iteration.yaml). Equal total sample weight per date is normalized to mean row weight one for both learners; this makes XGBoost's Hessian threshold and regularization scale explicit and differs intentionally from legacy Ridge weights. See the [official XGBoost API](https://xgboost.readthedocs.io/en/release_3.1.0/python/python_api.html). XGBoost 3.1.3 is a separate optional dependency; unavailable libraries fail explicitly, never fall back to another model.

## Inputs and timing

Use `data/local/r3_2_20261002_corrected_v2` unchanged, verifying its report and artifact hashes. Twelve existing price/volume/market features; GBP next-month benchmark-excess labels. Retain the source's unresolved outcomes and limitations. The artifact does not include every historical security and has unbounded provider-coverage/identity biases. The separate full historical identity audit retains denominator 793; retained feature-row counts are not that denominator.

Use the six [later-period folds](LATER_PERIOD_DESIGN.md), starting 2010, initial 8-year training / 2-year validation / 1-year test, annual steps. Build new assignments from calendar boundaries; do not reuse the old nine-fold assignments. Fit once before each validation segment and once before each test segment, using expanding prior history with actual label-exit/maturity checks and 31-session purging. No within-segment refits in this first diagnostic. Test-start fits include matured prior validation observations under the same fixed parameters. No model or parameter is selected from test performance.

Score every feature-eligible security at complete month ends, including those with missing eventual labels. Select the top five by score, then stable ID, before inspecting label coverage. Do not replace unresolved picks. This top-five basket is a diagnostic, not a change to the four-stock, risk-constrained account policy.

## Outputs and interpretation

- Monthly rank correlation on resolved labels, with eligible/resolved counts. It is conditional on outcome coverage.
- Top-five label completeness; mean excess return only when the selected basket is complete. Incomplete months remain in denominators.
- Paired differences for Ridge–momentum, XGBoost–momentum and XGBoost–Ridge. Cancel shared picks before assessing unresolved differential exposure.
- Illustrative missing monthly excess outcomes of -10%, 0%, +10%, symmetric adversarial scenarios and break-even values. These are stress assumptions, **not established error bounds**.
- Incremental monthly drag of 0/25/50 bps against the comparison control. This is a diagnostic haircut, not a broker tariff or all-in £3,000 cost model.
- Separate fold/segment outputs and saved predictions/models; no pooling overlapping validation windows as independent evidence, no annualization of diagnostic averages and no claim of >10% account attainment.

Registration is written before fitting and includes Git/tree/file hashes, complete environment, inputs, calendar, model policy and seeds. Failed runs retain their registration and failure record; completed outputs receive a hash manifest. All generated files stay ignored. Old experiments remain immutable.

## Run and next decision

With Python 3.12+ and `.[dev,historical-data,iteration]` installed:

```bash
python -m src.cli.r3_iteration --config config.r3-iteration.yaml --output data/local/r3_iteration_new_run
```

Requires the named local artifacts and a new output directory. macOS XGBoost additionally needs a discoverable OpenMP runtime; the actual run environment is recorded in registration.

After the report, decide which feature or outcome-coverage question is worth the next bounded cycle using validation evidence. A promising diagnostic supports further research, not qualification or deployment. Shared-policy account simulation, costed incremental value, fresh evidence and paper/live gates remain separate.

## Result — 2026-10-10

Completed local run: `data/local/r3_iteration_20261010_v1`; report SHA-256 `820620a8bd4ce928e4f6f2a1b2ae8cb21c2b9a17573d9fd344856a0c1c002b4e`. All three fixed candidates ran over six validation/test folds, producing 24 learned fits plus 12 momentum manifests. Test segments cover 72 non-overlapping monthly decisions in 2020–2025. Each model scored the same 33,398 stock-month observations; 26,937 have resolved labels. All dates remain development evidence.

| Model | Mean monthly rank IC, resolved labels | Missing top-five outcomes / 360 | Fully resolved top-five months / 72 |
| --- | ---: | ---: | ---: |
| Momentum | 0.00163 | 48 | 38 |
| Ridge | -0.01813 | 29 | 45 |
| XGBoost | 0.00644 | 45 | 41 |

IC measures ranking association, not return; these values are close to zero. XGBoost's six test-fold IC means are 0.0309, -0.0127, 0.0359, -0.0253, 0.0100 and -0.0002. Its validation-fold means are 0.0484, -0.0022, 0.0019, 0.0219, 0.0038 and -0.0197; validation windows overlap and are not independent replicates. No uncertainty estimate establishes a robust positive edge.

Only 23/72 test months have fully resolved differential XGBoost–momentum selected exposure. Their conditional mean difference is -0.489 percentage points per month; this incomplete subset cannot estimate overall performance. Across all 72 months, assigning unresolved differential outcomes adversarially within illustrative +/-10% monthly excess produces average difference scenarios from -3.5831 to +1.2502 percentage points, before any extra diagnostic cost drag. This range straddles zero and is not an evidenced error bound. Shared unresolved picks cancel in paired differences, but remaining source-selection bias is unbounded. No account return or target attainment was calculated.

**Decision:** no model is promoted and no additional hyperparameter search is justified by this run. The next registered question is a small price-only versus causal-fundamental ablation with the same three controls, explicit missingness and paired coverage. Scope source work to the joins/outcomes that prevent that comparison; do not restart a full-universe data-completion phase. This is a proposed next experiment, not an already implemented enriched model, and its exact inputs/trial budget must be fixed before fitting. Use validation to make decisions; do not optimize the next trial to the test table.

Verification in this turn: eight new focused tests passed; the full suite passed **525 tests**, with one non-failing joblib CPU-detection warning. Ruff and `mypy src` passed (121 source files); sdist/wheel build passed. A separate reproduction in `data/local/r3_iteration_20261010_reproduction` matched all 108 model/score/model-manifest artifacts byte-for-byte and every numerical report field. Registrations/completion timestamps differ by design. Both artifact manifests verify; the source dataset remains unchanged. PyArrow emitted sandbox CPU-probing warnings during the real runs without preventing completion.

Runtime: Python 3.12.14, NumPy 2.3.5, scikit-learn 1.8.0, PyArrow 23.0.1 and XGBoost 3.1.3. The run used `/private/tmp/ib-r3-venv/bin/python`, temporary XGBoost packages from `/private/tmp/r3-xgb-deps` via `PYTHONPATH`, and the existing scikit-learn OpenMP runtime via `DYLD_FALLBACK_LIBRARY_PATH=/Users/guillermo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages/sklearn/.dylibs`. The repository's old `.venv` is Python 3.9 and was not used or modified. Generated evidence and fitted models remain ignored; no broker access occurred.

## Sparse fundamental ablation — 2026-10-11

The user authorized adding available fundamentals. The separately versioned [configuration](../config.r3-fundamental-iteration.yaml), [join code](../src/research/r3_fundamental_iteration.py), [learner](../src/learning/r3_enriched.py) and [CLI](../src/cli/r3_fundamental_iteration.py) compare price-only momentum/Ridge/XGBoost with enriched Ridge/XGBoost. No parameter search or change to the source price dataset is made. The four SEC ratios and their four missing indicators are appended to the original twelve price features; zero-filled values are always paired with an explicit missing flag. Ridge fits scaling on training only. XGBoost uses the same fixed 100-tree parameters and mean-one date weights as the price-only comparison. Training still uses matured labels and the 31-session/actual-exit purge. All candidates score the same feature-eligible securities and dates.

The source is the hash-bound [fundamental coverage audit](FUNDAMENTAL_FEATURE_AUDIT.md). Only eight one-to-one mappings from the manual issuer/security audit are used. Its ambiguous Alphabet/Meta/Berkshire classes and the eight newer issuers without reviewed joins stay explicitly missing; no issuer values are projected onto an unverified security. For even these eight, the joins are sample-level development evidence without qualification-grade dated continuity. SEC values must be available by the actual decision close; that close can be earlier on half days than the legacy price-feature cutoff. Missing fundamentals never delete a stock from scoring. Original price-only score files and their complete manifest are verified and reused, giving a direct paired ablation.

Coverage is expected to be sparse, so the question is deliberately narrow: do the available four ratios change price-only rankings in a way that survives paired outcome uncertainty? A missing indicator can identify which issuer was sampled; any apparent advantage must be treated as conditional and may reflect source selection. Monthly rank IC and top-five diagnostics remain conditional development evidence, not an account backtest or a CAGR estimate. The £3,000 all-in objective and risk gates are unchanged.

Run with Python 3.12+, the historical-data and iteration dependencies, and a discoverable OpenMP runtime:

```bash
python -m src.cli.r3_fundamental_iteration --config config.r3-fundamental-iteration.yaml --output data/local/r3_fundamental_iteration_new_run
```

The command requires the frozen local source reports and baseline scores named in the config, refuses overwrite, writes registration before fitting, and preserves failed attempts.

### Completed ablation result — 2026-10-11

Canonical ignored run: `data/local/r3_fundamental_iteration_20261011_v2/report.json`, SHA-256 `b1f877a00aa5ae5b493030ad30a90ca416de683801d3cedcfd040a77216a4716`. The first v1 attempt and its repeat are preserved; v2 adds full Git/tree/dependency/file provenance and produced the same numerical fields and all 48 fitted-model/score files byte-for-byte. All 24 enriched learned fits completed. The original price-only report and source artifacts were verified and not rewritten.

Of **86,763** scored stock-month rows, **1,332 (1.54%)** have one of the eight manually reviewed issuer/security joins. Observed ratio counts on the joined rows are liabilities/assets 1,244, annual net income/assets 1,312, annual operating cash flow/assets 1,124 and annual gross profit/assets 609. Other issuer facts exist in the source audit but have no reviewed security join, so they are not attributed to a stock. The same 72 non-overlapping test months and 33,398 scored test rows are used by each candidate.

| Test diagnostic | Price only | Four SEC ratios + missing flags |
| --- | ---: | ---: |
| Ridge mean monthly rank IC on resolved labels | -0.01813 | -0.01326 |
| XGBoost mean monthly rank IC on resolved labels | 0.00644 | 0.00373 |
| Ridge selected outcomes missing / 360 | 29 | 27 |
| XGBoost selected outcomes missing / 360 | 45 | 40 |

Rank IC remains close to zero; test values are inspected development data, not fresh evidence. The paired top-five differences are fully resolved in only 40/72 months for Ridge and 47/72 for XGBoost. Conditional mean monthly differences on those complete pairs are -0.38 and -0.14 percentage points, respectively; incomplete months cannot be silently dropped to infer account performance. Illustrative +/-10% missing-excess scenarios straddle zero for both. No net £3,000 account return, CAGR or objective attainment was calculated.

The missingness indicator exposes source coverage. In the test top-five baskets, joined securities occur **3/360** times for price-only Ridge versus **195/360** for enriched Ridge, and **1/360** times for price-only XGBoost versus **92/360** for enriched XGBoost. That shift could arise from the eight-issuer sample identity rather than the economic ratio values. At most 1.54% of scored rows carry an audited join, and issuer/class continuity is not qualification-grade. No model is promoted; the contribution of the ratio *values* remains unproven. A future targeted control would keep the same missing flags while masking the values, registered as another inspected-data experiment before running it. Wider historical joins are needed for any representative performance claim.

The full suite passed **530 tests** (one non-failing joblib CPU-count warning); `ruff check .`, `mypy src` (124 source files), sdist and wheel build passed. The canonical artifact manifest verified, the v1/v2 numerical reports matched, and the run remained local and ignored. The first attempted run found an actual half-day close mismatch between source and price cutoffs; the corrected join requires the SEC close to occur no later than the price cutoff and the fact itself to be available by that cutoff. A dedicated regression test covers this case.
