# R3 completion progress

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
