# R3 completion progress

Current result, 2026-10-10: the [momentum/Ridge/XGBoost diagnostic](NEXT_RESEARCH_CYCLE.md#result--2026-10-10) completed and reproduced. No candidate is promoted; account returns were not evaluated. The source-acquisition timeline below is preserved historical evidence, not a block on bounded offline experiments.

**Current policy, 2026-10-10:** the user authorizes faster bounded offline experiments with imperfect data and explicit sensitivity analysis. The [current iteration policy](ROADMAP.md#current-iteration-policy--2026-10-10) supersedes earlier blanket requirements here to complete all historical remediation or obtain renewed permission before development comparisons. Earlier records remain historical evidence. Qualification gates remain unchanged. The separately implemented diagnostic and its current status are documented in [NEXT_RESEARCH_CYCLE.md](NEXT_RESEARCH_CYCLE.md).

Updated 2026-10-10. The user requested continued work until R3 is complete. This authorizes the remaining offline research, source remediation and engineering within the roadmap's gates; it supersedes earlier statements that another request was required merely to continue. Model experiments still require a bounded registration and valid inputs. This instruction does not certify data, remove stop rules, authorize subscriptions or grant exact live-order authorization.

R3 is **not complete**. R3.1 and R3.2 were closed by prior scope decisions with evidence gaps; corrected R3.3 controls failed; the separately approved later-period research direction remains in source remediation. The [later-period design](LATER_PERIOD_DESIGN.md) supports six calendar-complete folds, not six proven executable enriched-feature experiments.

## Fundamental engineering progress — 2026-10-10

Four tested period-aligned SEC ratios and an immutable monthly coverage report now exist. The [fundamental feature audit](FUNDAMENTAL_FEATURE_AUDIT.md) records 28,610 facts and 3,800 issuer-months across 19 issuers, actual exchange-close timing, a primary-filing reconciliation and remaining identity/history gaps. No security-level feature dataset, model fit or performance experiment has been admitted. Public-source work has progressed while the Tiingo access/export question remains pending.

## Full-universe inventory completed

The new [coverage audit](../src/research/r3_universe_coverage.py), [offline CLI](../src/cli/r3_universe_coverage.py) and [tests](../tests/test_r3_universe_coverage.py) compare pinned native membership with retained canonical membership and feature eligibility for all 200 complete monthly decisions, January 2010–August 2026. Native means the existing reconstructed historical source; this comparison does not independently certify its correctness. Half-open intervals, missing histories, exclusions and candidate identities remain separate.

| Measure | Result |
| --- | ---: |
| Unique native stable security IDs | 793 |
| Native security-month observations | 96,513 |
| Native observations missing retained membership | 7,016 |
| Distinct IDs with at least one missing retained membership month | 98 |
| Native observations without usable price features | 9,750 |
| Native observations without even a cached sample issuer match | 94,461 |
| Retained membership / usable feature observations outside the native universe | 0 / 0 |

Missing usable features include genuine causal exclusions, not just download failures. No return bias is estimated from these counts. Full enriched readiness remains false. There are no admitted dated issuer/class joins in this audit; the eleven manually sampled issuers remain discovery candidates.

The prioritized repair queue contains every historical identity, source symbols, missing-month counts and sanitized provider-request references. Ordering uses missing coverage and stable IDs, never investment returns. The largest gaps include EQR, BK/BNY, WY, MMC, MSI and JNPR, demonstrating that repairing Meta/Berkshire alone would be insufficient.

## Public-source discovery completed

Three public reference downloads succeeded without credentials or charges: Tiingo's supported-symbol archive and EOD documentation, and the SEC current ticker directory. The [Tiingo documentation](https://www.tiingo.com/documentation/end-of-day) says catalogue entries can include reserved symbols; actual metadata/API availability must be checked. The [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) describes current ticker metadata, which cannot establish historical issuer intervals.

The catalogue provides exact-symbol discovery candidates for 750/793 identities; the current SEC directory provides candidates for 616/793. These are discovery counts, not validated historical coverage. All duplicate symbols and asset types remain retained. For example, the downloaded catalogue lists `FB` as an ETF and `META` as a stock with advertised history from 2012-05-18; BNY has both ETF and stock entries. No ticker substitution or automatic merge was made.

The public [SEC CIK lookup](https://www.sec.gov/search-filings/cik-lookup) route was also investigated. The archived company-name lookup file contains 1,062,149 lines. Exact alphanumeric name matching against pinned constituent names found candidates for 72 IDs, including 15 without a current-symbol candidate. Multiple CIKs remain explicit; punctuation normalization is discovery only. No fuzzy name match, inferred effective interval or current-name backfill entered model features.

The configured `TIINGO_API_TOKEN` was absent from this process. The user was asked asynchronously to make the existing credential available locally, provide an export, or choose public sources only; no response is assumed. No credential values were inspected or printed, no provider account was created and no paid access was purchased. Public discovery continued independently.

## Immutable evidence and reproduction

- Full universe report: `data/local/r3_universe_20261007_audit_v2/report.json`, SHA-256 `74fa5514521f2f8a387eadd7df35fecdc8be0df51effc5e0b0178e28839db25a`; fixed-timestamp reproduction matched byte-for-byte. Exploratory v1 is retained but not the cited record; its supplied timestamp was ahead of execution time.
- Public raw references: `data/local/r3_source_discovery_20261007_v1/access_manifest.json`, with individual URLs, actual retrieval timestamps, sizes and physical hashes.
- SEC company-name lookup: `data/local/r3_cik_lookup_20261007_v1/access_manifest.json`; raw SHA-256 `3dc36655245cacdd5c9d25de454e3f0f08c6f4d7405b08cd23c0c1313de2b810`.
- Name-discovery report: `data/local/r3_name_discovery_20261007_v1/report.json`, SHA-256 `95d58234800b88c17b760affed578155d050e0c1df15cd848af86f46db8e71aa`; its retained source script and separate repeat reproduced identical bytes. Source retrieval time is in the referenced raw manifest. The report binds lookup, universe, constituent-name, helper-code and script hashes.

```bash
python -m src.cli.r3_universe_coverage \
  --output data/local/r3_universe_reproduction/report.json \
  --run-timestamp 2026-10-07T06:38:17.720236+00:00

PYTHONPATH=. python data/local/r3_name_discovery_20261007_v1/reproduce.py \
  --output data/local/r3_name_discovery_reproduction/report.json
```

Run from the repository root with Python 3.12+ and declared historical-data dependencies. Outputs must be new. The universe report binds the working tree and dependencies; later code/documentation changes legitimately change its provenance hash. Sources and generated outputs remain local and ignored. The offline CLI deliberately targets the recorded later-period evidence and source paths rather than introducing an unregistered configurable universe.

## Work still required

1. Obtain or acquire missing historical price/action data, resolve the 98 membership-gap identities and reconcile revised aliases against primary class/transition evidence. Missing rows remain in the denominator.
2. Resolve dated historical issuer/class identities for all 793 IDs, investigating the remaining unmatched and ambiguous cases. Current SEC name/ticker candidates cannot satisfy this gate alone.
3. Acquire filing-specific facts and acceptance history for resolved issuers; audit every monthly decision across the six folds, including stale/missing facts, amendments, units and accounting periods. Complete feature formulas and the source/cost budget before registering Ridge/XGBoost trials.
4. Run the bounded information-versus-model experiment only when its data gate passes. Retain all failures; no implicit parameter search or threshold changes.
5. Make the research decision. A failure or inconclusive result blocks advancement. R3.4 requires at least 756 genuinely fresh sessions plus its other gates; R3.5 requires qualification and at least 60 paper sessions; R3.6 requires exact live authorization and actual forward evaluation. Existing inspected history cannot satisfy those elapsed-observation requirements.

The next autonomous task is historical identity/source acquisition from the recorded queue. Do not rerun corrected controls, modify old artifacts, narrow the universe to current survivors or reinterpret this inventory as completed R3.

## Verification — 2026-10-07

Eleven focused tests passed, covering missing-universe denominators, half-open membership and future-addition invariance, non-native rows, duplicate features, overlapping/empty memberships, chronological decisions, provider-symbol reuse, class punctuation and ambiguous/malformed company-name lookups. Final full suite: **476 passed**, with one non-failing joblib CPU-detection warning. Ruff and strict mypy passed (114 source files), and the isolated package build produced an sdist and wheel. The original/corrected evidence verifier returned `all_verified: true`; documentation links, whitespace and ignored-output checks passed. No historical investment run, fitted model, broker connection or live order was created.

## Blocking review — 2026-10-10

**Goal status: blocked, not complete.** The same acquisition dependency has persisted across at least three consecutive goal turns. Those turns made independent progress on public-source discovery, coverage and feature engineering; they did not resolve the data needed for the end-to-end comparison. The latest inspection confirmed that the configured `TIINGO_API_TOKEN` is absent, no project `.env` or `.env.local` exists, and no replacement repair/export dataset was identified in the local acquisition inventory. Credential contents were not searched or printed.

The universe report still identifies 7,016 missing retained-membership security-months across 98 identities. The expanded SEC report remains issuer-level evidence with no admitted dated security joins. Neither report permits model fitting or qualification. Further isolated feature additions or synthetic model tests cannot replace these missing inputs; another performance run would not fulfill the registered experiment's coverage contract.

To resume the acquisition path, make the existing Tiingo credential available to the configured process, or supply a historical price/action export with security identifiers, coverage, provenance and terms. Access alone does not certify or repair the data: newly acquired responses must be reconciled and dated issuer/class joins completed before a new dataset and bounded Ridge/XGBoost trial registration. A separately evidenced alternative source is also possible; no paid account, purchase or automatic vendor substitution has been authorized or assumed.

| R3 requirement | Current evidence and disposition |
| --- | --- |
| R3.1 account economics | Closed by explicit prior scope decision; tariff, permissions and operating-cost evidence remains unresolved |
| R3.2 causal data/evaluation | Implemented and closed under prior development scope; later-period enriched dataset remains incomplete |
| R3.3 learned/control comparison | Corrected original controls completed and rejected; new richer-feature comparison blocked before registration/fitting |
| R3.4 qualification | No candidate admitted; no qualifying untouched 756-session evidence or completed forward gates |
| R3.5 paper operation | Not eligible to start; qualification and at least 60 paper sessions remain required |
| R3.6 live evaluation | Not eligible to start; exact live authorization and actual forward outcomes remain required |

No model promotion, risk relaxation, new experiment budget, unseen-data claim or broker action follows from the user's request to complete R3. The full objective is preserved. Resume from source acquisition and identity remediation when the external dependency changes; do not repeat the completed audits merely to keep the goal active.

This review changed documentation only. It checked current acquisition availability and readiness reports, local links and diff whitespace; it did not rerun the implementation suite. The prior 491-test, typing, lint and build results remain dated verification in the feature-audit record, not new passes claimed by this review.

### Local credential-file support

Acquisition now supports ignored `config/credentials.local.toml` with `[tiingo]` and `api_token = "..."`. The historical producer uses `src.config.credentials.load_tiingo_token`: a nonempty configured environment variable takes precedence, then the local file. Future readiness checks must use that loader without printing its return value; absence of the environment variable alone no longer proves that acquisition credentials are missing. The template was created with owner-only permissions and checked to be absent from Git-visible files and both package artifacts. Adding this support does not itself supply a credential, repair source coverage or resume model evaluation.

## Credential supplied; acquisition resumed — 2026-10-10

The user saved the local token. The configured loader successfully read it without displaying it, and authenticated Tiingo metadata requests succeeded for META, BRK-B, EQR, WY and BNY. **The credential blocker is resolved and the R3 goal is active again.** The earlier blocking review remains historical; data reconciliation and qualification gates remain open.

A new five-request historical package succeeded for META, BRK-B, WY and BNY; EQR returned an unusable/empty response and that failure remains recorded. EQR metadata identifies the provider's current symbol as VMRK. A separate VMRK request recovered a price history as an unmerged candidate, without rewriting the failed EQR request or asserting a historical legal-identity interval.

| Provider query | Downloaded rows | Coverage | Additional dates versus retained bars |
| --- | ---: | --- | ---: |
| META | 3,601 | 2012-05-18–2026-09-15 | 2,531 |
| BRK-B | 4,705 | 2008-01-02–2026-09-15 | 1,003 |
| BNY | 4,705 | 2008-01-02–2026-09-15 | 4,625 |
| WY | 4,705 | 2008-01-02–2026-09-15 | 0 |
| VMRK, candidate EQR alias | 4,705 | 2008-01-02–2026-09-15 | 4,705 |

The bounded histories have no interior missing XNYS sessions or off-calendar rows. Berkshire and WY match all overlapping fields checked. BNY has one changed volume observation. Meta's raw OHLCV matches the old overlap, but all 1,070 overlapping adjusted closes differ; an adjustment explanation remains required. VMRK has no retained EQR price overlap, so continuity cannot be inferred from a numerical comparison. No canonical merge has been admitted.

The WY case changes the next action: its old prices already existed, while retained membership stops on 2010-07-20. The preserved universe policy records a `CORPORATE_ACTION_FACTOR_MISMATCH` quarantine beginning that date. The legacy producer truncates affected membership intervals at an unresolved action finding. Of the 98 identities with missing retained membership, 18 have quality-quarantine records; the other 80 do not. This is an identity-level intersection, not a complete attribution of every missing month. Do not describe all 98 gaps as failed downloads. Retrying prices alone cannot resolve action quarantines; source/action reconciliation must precede restoring eligibility. No risk or quality threshold was relaxed.

Local evidence:

- `data/local/r3_tiingo_metadata_20261010_v1/manifest.json`: successful metadata response hashes and actual retrieval times.
- `data/local/r3_tiingo_repair_20261010_v1/tiingo_manifest.json`: four successful series and the retained EQR failure.
- `data/local/r3_tiingo_eqr_alias_20261010_v1/tiingo_manifest.json`: separate successful VMRK acquisition.
- `data/local/r3_price_repair_20261010_audit_v1/report.json`: source-bound comparison, SHA-256 `90c4a3079457158f428453095ab55b9e4fe2f0a07add7e7be8a0d27ed58d1286`, with retained reproduction script.
- Preserved universe-policy SHA-256: `5b1201ef5b28d4d3984f4fd99dcf0de18ee641cb69257328d6d4159342fe4e48`.

Acquisition used the existing credential; the current subscription tier was explicitly recorded as unverified rather than assuming the old Power-plan label still applied. No subscription change, payment, broker action, model fitting or return calculation occurred. Source hashes and date coverage were checked, the preservation verifier passed, and the token was absent from generated acquisition/audit files. Implementation tests were not rerun for this data-only acquisition; the credential implementation's prior full suite passed 499 tests.

Next: attribute all missing membership months between request gaps and action quarantines, reconcile the new aliases/actions and adjustment differences, then rebuild a separately identified dataset only where admission is supported. Keep the full reconstructed universe as the coverage denominator and preserve historical failures.

## Missing-membership attribution and identity defect — 2026-10-10

The reproducible read-only audit in `data/local/r3_gap_attribution_20261010_v1/reproduce.py` accounts for all 7,016 preserved missing membership security-months. Its immutable report SHA-256 is `d87a42591a1f097659e28c48c3be345bb904c4f97966def1f7f956c93c4287a3`. It binds the universe report, policy, canonical security master and original identity events by physical file hashes.

| Attribution under the preserved policy | Security-months | Distinct identities within category |
| --- | ---: | ---: |
| Failed provider request window | 4,384 | 63 |
| Corporate-action quarantine | 1,792 | 18 |
| Neither above; outside recorded identity interval | 814 | 17 |
| Neither above; recorded identity active | 26 | 1 |

Categories partition months, not identities. No month overlaps both a failed request and a quarantine. Request end dates are inclusive; quarantine and identity ends are exclusive. The residual 26 months belong to VIAC (`IC-US-fff2761dac2499ff`), December 2019 through January 2022. Attribution describes the old pipeline's exclusions, not verified economic causes or permission to restore rows.

A material source defect is now confirmed. The pinned `event/us.csv` calls JNPR's 2009-10-29 event a delisting while its note describes Nasdaq-100 removal. The temporal identity parser closes the security on that date. Juniper's [2010 SEC Form 10-K, Item 5](https://www.sec.gov/Archives/edgar/data/1043604/000144530511000332/juniper10k123110.htm) establishes that this was a transfer from Nasdaq to the NYSE under the same JNPR symbol, with continued trading in 2010. Therefore this event cannot support economic termination of the security. The original filing is preserved at `data/local/r3_jnpr_primary_20261010_v1/juniper_2010_10k.htm`, SHA-256 `a47b1c4bf261da90656704d2031bea8175ff102d120d351f6e12fea557bbdad2`, with actual retrieval metadata.

The event inventory contains 105 delisting records whose notes contain “removed from.” These are review candidates, not 105 proven errors. Likewise, the 814 months outside identities cannot all be restored from Juniper's evidence. Each relevant event needs a dated issuer/class decision and any actual later termination; exchange transfers, index removals, acquisitions and ticker reuse must remain distinct. The 2010 filing is retrospective evidence, not proof it was available in October 2009. A causal repair needs contemporaneous availability evidence or an explicitly later admission boundary.

This finding further limits the old performance comparisons: correcting label-dependent eligibility did not correct source identity truncation. Preserve those results as rejected development evidence. Repair the separately versioned identity/event path before constructing the later-period comparison; do not silently modify the legacy parser, drop unavailable names, or infer open-ended survival from current metadata.

Verification for this data/documentation increment: attribution totals and unique date/security pairs checked; inclusive/exclusive boundary assertions passed; immutable reproduction compared byte-for-byte; primary filing fetched successfully. No canonical data changed, no model fitted and no return calculation performed. Implementation tests are not a current verification claim for this increment. Next work: resolve VIAC's residual mapping, obtain contemporaneous exchange-transfer evidence and inventory primary-supported event corrections before rebuilding eligibility.

### Juniper announcement and VIAC response coverage — 2026-10-10

The follow-up acquisition recovered Juniper's [October 6, 2009 Form 8-K](https://www.sec.gov/Archives/edgar/data/1043604/000129993309003997/htm_34591.htm) and its SEC filing index. The index displays acceptance `2009-10-06 16:40:58`; timezone conversion and the configured processing delay still need explicit treatment in any admitted event record. The announcement describes an intended exchange transfer, subject to NYSE approval, and continued Nasdaq trading until completion. It supports rejecting economic delisting, but is not itself completion confirmation. Both files are archived under `data/local/r3_jnpr_contemporaneous_20261010_v1`, with SHA-256 `c7ae1b7e290e622396fcfc81513c6c9a589fbeb39864fabdb46d74300eb95284` (announcement) and `947271295baaa3eb6fb7a80395c808a4967be750b221de72e83d6bc0882bd614` (filing index). The direct Nasdaq archive request failed and remains recorded; browser-readable evidence was not represented as downloaded bytes.

Two bounded authenticated requests produced `data/local/r3_jnpr_viac_repair_20261010_v1/tiingo_manifest.json`:

- JNPR: 4,403 daily rows, 2008-01-02 through 2025-07-02; raw SHA-256 `f495b1da75f57d534b94e420f873bf433bf108fd2acc9c196794d5e66a9f9732`. This recovers a candidate post-2009 history. HPE's [July 2, 2025 merger-completion filing](https://www.sec.gov/Archives/edgar/data/1645590/000114036125024519/ef20051378_8k.htm) documents the later acquisition and cash consideration. Archive and reconcile that terminal event before admitting a complete identity/action history; do not extend JNPR indefinitely or fabricate a sale fill.
- VIAC: the same 275 rows as the original request, 2018-10-31 through 2019-12-04; identical raw SHA-256 `a2d67fc43b313d33a5a399ebced2a36cffbae0d9b83f7bd0adcb29fd76c1a978`. None overlap the missing December 2019–January 2022 membership months. The producer drops membership intervals with no overlapping bar, independently of request status. This explains the residual 26 months: successful but insufficient response coverage, not a failed request window or action quarantine.

The [CBS merger-completion filing](https://www.sec.gov/Archives/edgar/data/813828/000119312519306334/d842322d8k.htm) states that VIAC Class B trading starts December 5, 2019. The provider response ends the day before that. Its predecessor history must not be assumed to identify the desired post-merger security. Investigate the provider's successor alias and class mapping before further acquisition; simple VIAC retries reproduce the same insufficient result.

The coverage summary SHA-256 is `80424668dbab4b13ea5de370abed4b1e44a6a8c868305d6facde7d73f9ea66be`. Dates, counts and raw-byte identity were checked; no histories were merged, event overrides admitted, models fitted or returns calculated. This source-only increment did not rerun the implementation suite. Next: construct explicit, source-bound event decisions and reconcile successor aliases; retain request success separately from usable coverage.

### Paramount successor lookup rejects recycled ticker — 2026-10-10

Six bounded source requests are recorded in `data/local/r3_viac_identity_20261010_v1/manifest.json`: three SEC filings and VIAC/PARA metadata succeeded; CBS metadata failed. The archived 2019 merger filing distinguishes continued CBS shares from Viacom shares converted at a merger ratio. The archived [2022 name-change filing](https://www.sec.gov/Archives/edgar/data/813828/000081382822000011/viac-20220216.htm) establishes the Class B change from VIAC to PARA at the February 17, 2022 market open. Class A (PARAA) and preferred (PARAP) cannot substitute for that Class B history. Juniper's actual 2025 merger-completion filing is also now archived in this package.

The provider's current `tiingo/daily/PARA` metadata identifies **Banzai International Inc — Class A**, with coverage starting 2021-02-12. Its VIAC metadata identifies CBS Corp with coverage ending 2019-12-04. The preserved supported-symbol CSV has three distinct PARA records, including historical coverage ending 2025-08-07 and the current recycled symbol. Thus neither current metadata endpoint supplies an unambiguous historical Paramount Class B identity. No PARA price download or substitution was made.

The [Tiingo EOD documentation](https://www.tiingo.com/documentation/end-of-day) exposes ticker-based requests; the [symbology documentation](https://www.tiingo.com/documentation/appendix/symbology) limits stated delisted support to symbols not recycled. The [search documentation](https://www.tiingo.com/documentation/utilities/search) describes permaTicker as a placeholder for upcoming support. Fundamentals documentation separately advertises stable identifiers, which does not establish their availability for EOD prices. Do not invent an EOD permaTicker route from the fundamentals API.

A documented `tiingo/utilities/search?query=Paramount` request is preserved in `data/local/r3_paramount_search_20261010_v1`. It returns five candidates, none historical Paramount common Class B. Search absence does not prove the vendor lacks the data, but this query establishes no usable alternate identifier. The affected history remains unresolved pending a documented provider route or a separately verified historical source/export. Continue other identity/action repairs; do not eliminate these native members from the denominator, treat preferred shares as common, or repeatedly query the known wrong alias.

This increment acquired primary evidence and rejected an unsafe provider mapping. Response manifests preserve hashes and actual retrieval times; failures remain recorded. No implementation changed and the test suite was not rerun. Model registration remains gated by the incomplete coherent dataset.

### Broad request triage and WY distribution evidence — 2026-10-10

A bounded 57-request metadata batch, `data/local/r3_gap_metadata_20261010_v1`, covers the remaining failed-request symbols after five previously investigated cases. It binds the gap report and preserves all responses. Fifty metadata calls succeeded: 26 have no price coverage dates and 24 have dates requiring identity validation. Seven calls failed. Metadata success is not historical coverage or identity admission. Current symbols include unrelated reused names such as APC, CA, CDAY, CSRA, INFO, LB, NFX, SPLS, STI, TE and WIN; these were not submitted as price repairs.

Nine company-name-compatible raw-price candidates were requested for the original missing intervals in `data/local/r3_gap_prices_20261010_v1`. BF.B normalized to BF-B recovered 804 rows, 2023-07-03 through 2026-09-15. Eight returned empty/malformed payloads: DXC, LXK, APOL, VIAV, NYX, QLGC, MDP and BTUUQ. Six requests predate the metadata's advertised coverage and should have been eliminated before acquisition; do not repeat them. NYX and MDP failed despite advertised overlap. All failures remain preserved. Subsequent batches must require interval overlap as well as a plausible issuer/class before spending a price request. No recovered history is admitted or merged yet.

WY's action quarantine is now tied to original issuer evidence, archived in `data/local/r3_wy_action_20261010_v1`. The [July 15, 2010 announcement](https://investor.weyerhaeuser.com/2010-07-15-Weyerhaeuser-Announces-Ex-Dividend-Date-for-Special-Dividend) specifies the July 20 ex-date. The [September 1 payment announcement](https://investor.weyerhaeuser.com/2010-09-01-Weyerhaeuser-Announces-Payment-of-the-Special-Dividend) describes an elective cash-and-stock distribution. It cannot be treated as wholly spendable cash on the ex-date.

The preserved provider row reports `divCash=26.51341416`, `splitFactor=1` on July 20. Adjacent closes imply an observed adjustment-factor change of 2.66332585695, while the current cash-only formula yields 2.73102638127 (relative difference −2.47894%). `comparison.json` binds the actual provider file and retains the adjacent observations and calculation. An implied cash amount derived algebraically from adjusted prices is diagnostic only, not a verified distribution or permissible replacement. Retain the quarantine until entitlement, election/default treatment, stock allocation, payment timing and causal availability can be represented and reconciled. Do not loosen tolerances or use later payment terms as ex-date knowledge.

Verification: metadata response hashes checked; actual date ranges and provider failures inspected; WY primary responses both archived successfully; factor calculation reproduced from preserved adjacent rows; diff whitespace checked. No implementation changed, model fitted, return simulated or historical artifact overwritten. Full implementation tests were not rerun for this acquisition increment. Full-universe data repair remains incomplete and the model comparison is not ready.

### Successor-symbol batch — 2026-10-10

Fourteen successor metadata hypotheses returned plausible company names and date ranges in `data/local/r3_successor_metadata_20261010_v1`. These are discovery mappings, not admitted security joins. Fifteen bounded requests (two inherited IDs use ELV) then succeeded in `data/local/r3_successor_prices_20261010_v1`. Every requested interval overlaps advertised coverage; requests are limited to the missing windows from 2008 onward, ending no later than 2026-09-15.

The downloaded candidates cover 1,629 distinct previously missing security-month decision dates across COR, ELV, BALL, DAY, CTRA, LUMN, FBIN, GAP, DINO, MRSH, RVTY, EG, GL and WTW. This is candidate raw-bar coverage, **not 1,629 admitted repairs**. Dated issuer/class continuity, predecessor/successor treatment, action accounting, feature lookbacks and revision reconciliation still govern admission. Some source IDs already encode distinct predecessor histories; a shared provider alias does not authorize merging them.

`coverage_audit.json` SHA-256 is `47bccd1f9a2859a1d22567cacf89df0ec08429cabeb1cb008eb1f4b4044fa654`. Its retained `audit.py` verifies each raw response hash, checks duplicate dates, binds the original gap report and acquisition inputs, and reproduces the coverage report without modifying an existing result. It reports zero admitted repaired months explicitly. No model or performance calculation was run.

[Historical-data acceptance requirements](DATA_REPAIR_REQUIREMENTS.md) now defines the required delivery and representative failure cases for an existing provider route or alternative historical export. It keeps model spending behind the data gate and distinguishes a failed enriched-data feasibility decision from a claim that Ridge outperforms XGBoost. No purchase, vendor message or protocol change was made. Next work is to turn supported identity/action evidence into separately versioned admissions and quantify residual coverage; raw download success alone cannot close the data gate.

### Combined recovered coverage and adjustment-convention defect — 2026-10-10

`data/local/r3_recovered_coverage_20261010_v1/report.json` combines all five successful acquisition packages against the original 7,016 missing membership security-months. Candidate bars cover **2,531 distinct missing decision dates**; **4,485 remain without a recovered candidate bar**. No package has an interior missing XNYS session over its actual response interval. Counts do not establish lookback completeness, identity admission or a repaired dataset. The report SHA-256 is `6fa38a66367fa465083771fcf6e3e4cfe8481f8963237cb0ffbea52242c46e5e`; its reproduction script verifies source hashes and duplicate dates.

A strict factor diagnostic exposed a legacy formula defect. For a cash-only event, let `P0` be the previous raw close, `P1` the ex-date raw close, `D` the dividend and `A` adjusted close. The legacy check expects `(A1/P1)/(A0/P0) = P0/(P0-D)`. Across the acquired series, the observed factors instead match `1 + D/P1`, which makes the adjusted daily price ratio equal `(P1+D)/P0`. This is the total-return convention with ex-date-close dividend reinvestment. It is an observed numerical finding consistent with the provider's stated total-return methodology, not a new vendor guarantee.

`data/local/r3_factor_convention_20261010_v1/report.json` tests both formulas at the same fixed diagnostic tolerance (`rtol=1e-5`, `atol=1e-8`): **917 events without simultaneous splits; 743 prior-close mismatches; zero ex-date-close mismatches**. Its SHA-256 is `6d40217085780632be988c5572d20b77f52a0b23f0dedf49ed29cc6703674c69`. The diagnostic tolerance is not a new certification setting. Legacy certification uses a looser 2% tolerance, which conceals many small convention differences. Neither its formula nor threshold was changed, and old artifacts remain intact.

This changes the next engineering action: implement an explicit separately versioned R3 adjustment convention and verify it with cash, split and combined-event unit rules before recertification. Do not attribute every mismatch to bad vendor data. Conversely, matching adjusted prices does not prove a distribution was cash, establish its availability/payment date, or permit reinvestment in the actual cash-account ledger. WY's special-distribution representation remains unresolved even though the provider's factor matches its own cash-equivalent field.

Brown-Forman's [2023 Form 10-K](https://www.sec.gov/Archives/edgar/data/14693/000001469323000074/bfb-20230430.htm) was archived in `data/local/r3_bfb_primary_20261010_v1`, SHA-256 `a3b8318a1f0e0f048af68adb963e0f5ba1c8d3b4547b2a54e8088c4f308fe983`. It distinguishes nonvoting Class B common from Class A. The attempted index request failed and remains recorded; no acceptance timestamp was invented and no dated mapping was admitted from this filing alone.

These are forensic source calculations, not investment performance results. Both diagnostic reports reproduce immutable bytes; raw hashes and date uniqueness were checked. No implementation changed or full test suite rerun. Next: correct the R3 factor model without modifying legacy evidence, then combine identity, action and coverage evidence for admission.

### R3 adjustment checker implemented — 2026-10-10

A separate typed component, `src/data/r3_adjustments.py`, implements `r3-ex-date-close-total-return-v1` without changing legacy certification. It validates matching security/event dates, exchange-calendar predecessor, finite positive prices/split ratios and finite nonnegative distributions/tolerances. Combined split/distribution events require explicit pre-split or post-split share units. The result reports numerical factor consistency only; it supplies no identity, eligibility or cash-accounting admission.

`data/local/r3_adjustment_validation_20261010_v1/reproduce.py` exercises the actual component on the recovered raw packages. All **67,881 adjacent windows** reconcile at `rtol=1e-5`, `atol=1e-8`, including **917 distribution events and nine splits**, with no findings or ambiguous combined events in these inputs. Report SHA-256: `c46d4a9f507bcd8a0b29c5fbc65b39703fab1b2324263ecd70221cf00e575f6a`. The script verifies raw hashes and real calendar predecessors and binds its implementation and source inventory. This is arithmetic/source consistency, not independent confirmation of distribution terms or investment performance.

Thirteen focused tests cover one-share total wealth under a cash dividend, split/reverse split wealth preservation, equivalent combined-event share units, rejection of missing units, unexplained adjustment changes, invalid numeric inputs/tolerances, wrong identities, event-date mismatch and stale bars. The new component is not yet a full-universe builder or replacement certificate. Existing identity, coverage, cash-payment and special-distribution gates remain open.

Current implementation verification: **512 tests passed** (one non-failing joblib CPU-detection warning); Ruff passed; strict mypy passed on 118 source files; isolated sdist/wheel build passed. The real-data component report reproduced byte-for-byte, and the preserved-evidence verifier returned `true`. Diff whitespace passed. No old source, canonical, fitted-model or performance artifact was rewritten. Remaining work is full source/identity/action admission and a separately identified dataset, followed by model registration only if the data/economics gates pass.

### Quarantine triggers and distribution-access gate — 2026-10-10

The new R3 checker was applied to all 18 preserved quarantine trigger dates using the canonical bars/actions and actual calendar predecessor. Fifteen triggers are numerically consistent under the corrected convention; MDLZ and KHC lack adjacent bars; MSI combines split and distribution amounts with unverified share units. This checks trigger dates only, not every later excluded interval. Some legacy `ACTION_WITHOUT_BARS` triggers have adjacent bars in the exported canonical data; this discrepancy requires tracing the producer's certification input slice and cannot be attributed solely to the factor formula.

The immutable report `data/local/r3_quarantine_review_20261010_v1/report.json` has SHA-256 `777fb9549b83528eb20e88a86cafcf739b9ae1bd558dde6b4e407115a974a42b`. Its reproduction script binds original policy, canonical prices/actions, calendar and the new implementation. Every admission remains false: factor agreement does not resolve distribution terms, payment timing or identity semantics. No quarantine was removed.

The documented distribution endpoint was probed with the saved credential for WY's 2010 actions and BF-B's recovered 2023–2026 period. **Both returned HTTP 403.** `data/local/r3_distribution_probe_20261010_v1/manifest.json` preserves the exact endpoints, bounded date parameters, retrieval times and failure codes without credential contents. EOD access is working; distribution-endpoint access is not established. No subscription change, purchase or vendor message occurred. The user was asked whether an existing action export or enabled Tiingo distribution access is available; independent identity work can continue while that is unresolved.

Brown-Forman's accession-directory SEC index was successfully retrieved separately, preserving the prior failed request. It displays acceptance `2023-06-16 16:03:20` (interpreted as America/New_York). The existing cover extractor, with its 24-hour processing latency, recovered separate Class A voting and Class B nonvoting observations, plus two debt securities, without extraction issues. Source and output are in `data/local/r3_bfb_acceptance_20261010_v1`. Index SHA-256: `f04c53526f36c89a5afa618bc0a57e3f9ee32870e92c05a6e5af409358f4314b`. Class B evidence is available before the July 2023 missing-price interval; an interval-wide security map and payment evidence still require admission work. Debt observations are not equity substitutes.

This increment used the existing tested components and changed only local evidence/documentation. Quarantine report reproduction and diff whitespace checks passed; no fresh implementation-suite result is claimed. The last implementation verification remains 512 tests plus lint, typing, build and preserved-evidence checks. Next: establish a source-supported identity admission path and trace missing-bar certification slices; do not claim R3 complete or fit models while the registered dataset remains incomplete.

### Membership-boundary context defect reproduced — 2026-10-10

The pre-quarantine membership path was replayed from the verified original membership and identity snapshots, failed-request subtraction and identity intersections. All ten `ACTION_WITHOUT_BARS` trigger dates are first sessions of their relevant retained membership segment. Eight have the prior bar in the canonical export: CBOE, RTX, BBWI, ARES, DISCK, GRMN, DD and EVHC. The legacy producer's `active_member` filter removes that preceding observation before certification. MDLZ and KHC lack the preceding source bar itself. Report SHA-256: `162d311cb22a517d67c905aff983f99d46a778d2058fa3f69a828294affd9ec7`, at `data/local/r3_membership_boundary_20261010_v1/report.json`.

This is a second independent pipeline defect, not a reason to relax action checking. `adjustment_context_keys` was added to the separate R3 component: it requests the actual predecessor and current session while preserving the original eligibility set. It rejects malformed calendars and missing calendar predecessors and never fabricates missing observations. Five additional regression cases verify the first-membership-day action across a weekend, unchanged membership, absence of fabricated bars and invalid calendar boundaries.

The real-data context audit requests 20 lookup keys for ten windows and finds 18 existing bars; only the two MDLZ/KHC predecessors remain absent. Package `data/local/r3_adjustment_context_20261010_v1` binds implementation, canonical bars, calendar and boundary report; report SHA-256 `485569932437d9e37183354f87e0552864bf4ad6a112c4e268a4d7b90fc0b76e`. The eight available predecessor bars are validated context candidates, not restored membership or approved identity links. Legacy producer behavior, old quarantines and old evidence were not changed.

The earlier factor-validation report binds the previous implementation hash; it remains immutable rather than being re-signed after adding this helper. This context audit is a new artifact with the new implementation hash. Full-universe builder integration and legal/action admission remain outstanding; model fitting remains gated.

Current verification for the context-selector change: **517 tests passed**, with the known non-failing joblib CPU-detection warning; Ruff passed; strict mypy passed on 118 source files; isolated sdist/wheel build passed. The context report reproduced byte-for-byte, preserved-evidence verification returned `true`, and diff whitespace passed. No investment experiment, source-admission override or broker action occurred.

### Consolidated current-input readiness decision — 2026-10-10

The combined inventory now distinguishes original raw observations from new candidate downloads. Of the original 7,016 missing retained-membership security-months:

| Raw-bar inventory at the decision date | Count |
| --- | ---: |
| Existing canonical raw bar | 1,792 |
| Recovered candidate bar | 2,531 |
| Present in both | 194 |
| Additional candidate observations beyond existing bars | 2,337 |
| Existing or recovered candidate | 4,129 |
| Neither, under the inherited security ID | 2,887 |

The remaining 2,887 dates span 61 inherited identities: 2,233 overlap original failed requests, 628 lie outside recorded identity intervals, and 26 are VIAC's insufficient-response period. These are missing-under-ID counts, not proof that no other alias/provider can supply the economic history. The earlier 4,485 figure measured absence from new downloads only; it must not be described as absence from both old and new data. None of these decision-close counts certifies feature lookbacks, execution bars, label horizons or legal continuity.

The immutable package `data/local/r3_repair_readiness_20261010_v1` contains the complete residual queue and source-bound reproduction script. Report SHA-256: `855a10758957c90598fe589c3870a9b0f60013c0ad31d19e7b63c236b3fddfec`. The report explicitly retains zero admitted repairs, `model_fitting_ready=false` and `qualification_ready=false`; the two distribution-access probes remain HTTP 403.

**Decision: the separately registered enriched comparison cannot run on the current assembled inputs.** This is a present data-readiness decision, not evidence favoring Ridge, rejecting XGBoost, or proving the return objective impossible. Corrected arithmetic and recovered candidates are useful prerequisites but do not close the historical source contract. Keep fitting and hyperparameter spending at zero until a coherent dataset is admitted. Historical identity/event remediation and builder integration remain engineering work; missing histories and distribution evidence require verified sources, including a documented vendor route or export where current access fails. The user's pending data-access answer can change that path; no new purchase or vendor communication is assumed.

Verification for this consolidation: source hashes and successful raw responses verified, missing-date partitions asserted, report reproduced byte-for-byte, diff whitespace checked. This data/documentation increment did not rerun the implementation suite; the preceding 517-test result remains the dated implementation verification. No performance experiment or qualification claim was made.

### Blocked audit after source remediation — 2026-10-10

The persistent external-data gate has recurred over more than three consecutive continuation turns, including the distribution probes, independent context-check implementation and consolidated readiness decision. EOD credentials are working, but current assembled evidence cannot satisfy the registered historical dataset. The latest one-request recheck again returned HTTP 403 for BF-B distributions; it is preserved in `data/local/r3_access_recheck_20261010_v1/manifest.json`. A recursive local-evidence inventory found no other new or modified source files after the readiness report. This does not claim that no source exists elsewhere; none has been supplied or established as an accessible replacement.

**Goal disposition: blocked, not complete.** Additional model experiments cannot resolve the missing data, and more disconnected audits or unintegrated scaffolding would not produce an admissible end-to-end comparison. Retain the completed acquisition, corrected R3 factor/context components and 517-test implementation verification. Do not retry unchanged empty histories or poll access indefinitely. No unfinished live process is being treated as stopped; all acquisition and check processes have completed.

Resume when an existing historical export, enabled distribution access or a verified alternative provider route supplies evidence meeting [the acceptance requirements](DATA_REPAIR_REQUIREMENTS.md). Distribution access alone does not solve recycled-ticker histories or all 2,887 missing-under-ID decision dates. No purchase, external message, protocol narrowing or broker action is authorized by this status. The user's pending data-access question remains relevant.

On resumption, verify actual access and source bytes first, then finish historical identity/action admissions, full dataset integration and readiness checks before separately registering the enriched model comparison. These engineering tasks remain incomplete; they are not represented as having been closed by successful unit tests. R3.4 still requires its genuinely fresh observation period, R3.5 requires paper qualification and observation, and R3.6 requires exact live authorization and actual outcomes. The full original objective remains unchanged.

This final gate review changed documentation only and revalidated external access; it did not rerun the implementation suite or fit a model. Diff whitespace and documentation links were checked. Earlier evidence remains immutable.
