# Phase 3 Delivery Record

## Objective

Deliver Phase 3 from `docs/ROADMAP.md`: robust, reproducible historical validation
for the deterministic long-only strategy. The implementation must support point-in-time
universe membership, expanding walk-forward evaluation, parameter sensitivity, block
bootstrap, ablation testing, and generation of `research_report.md` with an explicit,
evidence-backed assessment of every mandatory deployment gate. No result is financial
advice or a guarantee of returns.

The initial real-data route is version-pinned open-source membership + Tiingo, rather than a
requirement for CRSP/WRDS: `chinobing/historical_sp500_constituents` provides primary S&P 500
membership from 1996; `unliftedq/index-constitution` provides ticker-change/delisting events for
the security master; `riazarbi/sp500-scraper` Wikipedia and iShares IVV histories provide two
QA streams from the same pinned repository; and Tiingo raw/adjusted OHLCV, dividends, and splits
provide price history.
FMP is optional supplemental QA, not one of the user-authorized minimum sources. The route remains subject to
the complete lineage, reconciliation, coverage, delisting, and independent 50–100-event audit
requirements in `docs/PHASE3_HISTORICAL_VALIDATION.md`.

## Measurable acceptance criteria

- [x] Point-in-time universe records have explicit effective intervals and source/version
  metadata; membership is resolved strictly as of each signal date, delisted constituents
  remain historically available, overlaps/duplicates fail closed, and future membership
  changes cannot alter earlier results.
- [x] An expanding walk-forward engine produces deterministic chronological train,
  validation, and test windows with configurable 8y/2y/1y/6m defaults; parameter choice uses
  validation data only and every out-of-sample observation belongs to a test window.
- [x] Sensitivity analysis evaluates a predeclared broad one-axis-at-a-time design across every
  configured axis around the production baseline, records all
  candidates and validation scores, applies a documented stable-plateau selection rule, and
  never selects from test performance.
- [x] Block bootstrap supports daily returns, closed-trade returns, and market-regime blocks,
  uses at least 2,000 iterations by default, records its seed/method, reports portfolio CAGR,
  drawdown, Sharpe and horizon distributions from daily/regime paths when defined, and reports
  a mean-trade-return distribution without pretending overlapping trades are portfolio paths.
- [x] Ablation testing reports like-for-like out-of-sample results for the full deterministic
  strategy and each required component removal, with identical windows, data, and costs.
- [x] Gate evaluation covers OOS CAGR, Sharpe, maximum drawdown, stressed-cost CAGR/Sharpe,
  calendar-year and single-stock profit concentration, closed-trade count, and parameter
  robustness. Missing or inadmissible evidence fails closed and cannot claim paper readiness.
- [x] A supported CLI generates deterministic machine-readable validation output and a
  human-readable `research_report.md` containing provenance, dataset limitations, windows,
  selected parameters, sensitivity, bootstrap, ablations, benchmarks, all gates, and an
  unambiguous overall pass/fail decision.
- [x] Event timing remains causal (signals after close, execution no earlier than the next
  available session), all Phase 2 hard risk invariants remain enforced, and prefix/future
  invariance tests cover new Phase 3 paths.
- [x] The checked-in engineering fixture exercises the complete Phase 3 workflow without
  being represented as deployment evidence; real historical data is never fabricated.
- [x] Implement the open-source-membership + Tiingo historical-data producer: immutable,
  commit-pinned source snapshots; point-in-time membership/security-master construction;
  canonical Parquet output; optional supplemental reconciliation; and a reproducibly sampled
  50–100-event independent membership audit.
- [x] Full tests, Ruff, strict mypy, package build, installed CLI smoke tests, deterministic
  report comparison, and direct report inspection pass; independent reviewers find no
  remaining material correctness, leakage, reproducibility, or risk issue.

## Task backlog

- [x] Inspect repository status, roadmap, validation/data/architecture specifications, current
  Phase 2 implementation, and supported tooling.
- [x] Define initial Phase 3 scope and measurable acceptance criteria.
- [x] Establish canonical point-in-time universe format, validation, and as-of selection.
- [x] Implement deterministic walk-forward window construction and validation-only selection.
- [x] Implement sensitivity grids and stable-plateau parameter selection.
- [x] Implement seeded block bootstrap for required sources and statistics.
- [x] Implement ablation scenarios and contribution/diversification calculations.
- [x] Implement fail-closed mandatory deployment-gate assessment.
- [x] Integrate the Phase 3 workflow and Markdown/JSON report CLI.
- [x] Add fixtures and unit/property/integration/regression/leakage tests.
- [x] Update config, README, and Phase 3 documentation.
- [x] Define and implement the open-source-membership + Tiingo data-ingestion and audit contract
  before attempting a real-data validation artifact.
- [x] Run focused and full verification and inspect actual CLI behaviour.
- [x] Complete independent reviews, fix all material findings, and reassess every criterion.
- [x] Bind primary membership, identity, QA evidence, Tiingo bars/actions, and FMP observations to
  the exact verified raw files parsed in-process; reject unrelated but valid manifests.
- [x] Replace caller-asserted execution-audit booleans with concrete next-session and documented
  2x-commission/10-bps-slippage audit records.
- [x] Reject duplicate semantic constituent events even when caller event IDs differ.
- [x] Provide supported offline raw-sources-to-canonical and native validation/report commands.
- [x] Reconcile the execution audit against the exact decision/order/fill population emitted by
  a native backtest and bind it to the canonical dataset, strategy, cost, and validation run IDs.
- [x] Separate canonical dataset certification from execution certification: raw-to-canonical
  builds no longer accept execution audit input, and dataset evidence cannot make a validation run
  admissible without the future content-bound native execution certificate.
- [x] Pin the approved chinobing and unliftedq checkouts to exact commits and generate manifests
  from verified Git origin/HEAD/tracked-file state instead of accepting caller-declared origins.
- [x] Add a native canonical-dataset backtest/validation artifact builder so trusted producer
  evidence, stitched OOS outcomes, stressed executions, ablations, and gates share one content
  identity; keep the generic caller-artifact CLI permanently inadmissible.
- [x] Remove primary-derived event/security identifiers from independent QA inputs and reconcile
  source observations independently by symbol, action, and date, rejecting duplicates and
  ambiguous matches.

## Active delivery plan (2026-09-12 resumption)

1. **Producer contract and canonical model** — define typed, fail-closed schemas for pinned
   source snapshots, stable security identities, membership changes, Tiingo bars/actions,
   exclusions, quarantine records, audit observations, and the immutable dataset manifest.
2. **Deterministic local build** — construct half-open membership intervals and the dated
   security master; validate identity continuity/delistings and member-session coverage;
   reconcile raw/adjusted prices with splits/dividends; write canonical Parquet plus hashes
   without allowing provider access from analytics code.
3. **Acquisition and audit orchestration** — add resumable/throttled Tiingo acquisition,
   commit-pinned Git-source input verification, seeded 50–100 event sampling, independent
   evidence comparison, quarantine semantics, and a supported CLI that never embeds secrets.
4. **End-to-end trust boundary** — connect producer evidence to validation eligibility only
   through semantic checks performed in-process; preserve fail-closed behavior when any source,
   coverage, audit, action, delisting, timing, or cost requirement is unresolved.
5. **Verification and closure** — run focused and full tests, Ruff, strict mypy, build and
   installed-wheel CLI smoke tests; compare deterministic outputs; inspect produced artifacts;
   obtain independent data, validation, and delivery reviews; fix all material findings and
   repeat until closure.

The tasks are ordered by dependency. Schema/review work and validation review run in parallel;
implementation work that touches shared producer files remains coordinated in the main worktree
because the repository already contains extensive uncommitted Phase 2/3 user-owned changes.

## Completed work

- 2026-09-09: Created the Phase 3 delivery goal and inspected the repository, dirty worktree,
  roadmap, validation specification, architecture, data requirements, and existing Phase 2
  handoff. Existing Phase 2 changes are treated as user-owned baseline.
- 2026-09-09: Launched independent scope, implementation-gap, and verification audits.
- 2026-09-09: Added PIT membership, expanding fold/stitching, parameter-grid/plateau,
  daily/trade/regime bootstrap, deployment-gate, and ablation primitives with tests.
- 2026-09-09: Added typed validation configuration, Phase 3 conventions, and an honest
  fail-closed engineering report. The first full gate passed 136 tests, Ruff, strict mypy,
  diff checks, and package build.
- 2026-09-09: Independent reviews found missing end-to-end orchestration plus material
  statistical gaps. Corrective tasks are active; these findings are not waived by the data
  blocker.
- 2026-09-10: Added an artifact-driven end-to-end workflow and supported CLI, historical
  security master, fold-specific sensitivity records, derived deployment evidence, complete
  performance schemas, provenance hashes, and a deterministic synthetic engineering artifact.
- 2026-09-10: Closed material review findings: validation contexts hide test dates and reject
  observations; robustness requires a minimum economic score; realized trades use unique lot
  IDs and derived basis/proceeds economics; trade bootstrap no longer compounds overlapping
  positions; undefined ablation ratios remain undefined; non-synthetic artifacts require a
  canonical OAT design, hashed source files, exact cost stress, and next-session timing audit.
- 2026-09-10: Final reviewers demonstrated that file hashes and artifact flags cannot establish
  semantic PIT completeness or causal coverage. The CLI was changed to make every artifact-only
  run deployment-inadmissible, even when its caller claims real PIT data. This removes the
  false-readiness path while leaving trusted source validation as discovered work blocked on the
  real data/producer contract. Supporting plateau neighbours must now individually clear the
  configured economic threshold. Reviewer-found Ruff closure capture was also fixed.
- 2026-09-12: Added public-reconstructed research commands: a pinned `pitindex==0.2.1` S&P 500
  membership exporter and a separately hashed Yahoo daily-price acquisition path. Both manifests
  permanently disable deployment admissibility and paper execution; failed public-price symbols
  are recorded rather than silently excluded.
- 2026-09-12: Independent review found and the implementation fixed public-source horizon and
  identity defects: interval ends are closed at the export boundary, the public-price importer
  binds to the exact membership manifest and rejects out-of-range bars, and canonical PIT
  snapshot content is hashed into the source version. A final boundary re-review passed.
- 2026-09-12: Replaced the unavailable FMP route with a version-pinned open-source membership +
  Tiingo plan. `chinobing/historical_sp500_constituents` is primary membership;
  `unliftedq/index-constitution` supplies identity events; and the Wikipedia and historical IVV
  streams in `riazarbi/sp500-scraper` supply QA. The existing immutable lineage, point-in-time
  identity, corporate-action reconciliation, and seeded 50–100-event audit controls remain.
- 2026-09-13: Implemented the offline trusted producer boundary: verified source manifests and
  content, stable dated identities and membership intervals, resumable Tiingo acquisition and
  transformation, explicit canonical raw/adjusted OHLCV and actions in atomic Parquet output,
  semantic certification, seeded dual-source membership audit, and content-bound producer
  evidence. Direct construction can no longer spoof a verified source or trusted evidence.
- 2026-09-13: Added mandatory supplemental FMP reconciliation for raw OHLCV, dividends, and
  delistings. FMP cannot add or repair canonical history; discrepancies fail unless mapped to an
  exact documented quarantine. The report is hash-bound to canonical bars/actions and included in
  the producer identity.
- 2026-09-13: Closed material independent-review findings in validation, canonical verification,
  Tiingo resume safety, bootstrap tails/regime episodes, derived metrics, OOS trade bounds, and
  caller-asserted trust. The engineering fixture remains deliberately fail-closed.
- 2026-09-13 completion reassessment reopened the producer criterion: canonical manifests contain
  opaque lineage hashes but not the specification-required readable Git and provider provenance,
  and FMP has reconciliation primitives but no immutable acquisition manifest yet. These are
  locally actionable implementation gaps, not external-data blockers.
- 2026-09-13: A renewed independent delivery audit found five material gaps: unrelated verified
  manifests could be paired with caller-built domain objects, execution audit was a boolean/hash,
  sparse FMP observations could be cherry-picked and quarantines were not propagated, duplicate
  semantic changes could inflate the audit, and the installed producer command remained
  acquisition-only. The producer criterion and final-review criterion remain open.
- 2026-09-13: Fixed the execution and duplicate-event findings. Eligibility now hashes a concrete
  execution report whose fills must occur on the next exchange session and whose stress applies at
  least 2x commission and 10 bps/2x slippage. Audit populations now reject duplicate
  security/symbol/action/date events and are checked against changes derived from consecutive
  primary membership snapshots.
- 2026-09-13: Upgraded canonical manifests to v2 with readable transformation version and exact
  Git/provider provenance fields rather than opaque hashes alone. FMP reconciliation now requires
  complete coverage of every canonical raw bar and every canonical dividend/delisting action; the
  trusted producer currently rejects any remaining FMP finding, including a nominally quarantined
  one, until safe quarantine propagation is implemented.
- 2026-09-13: Closed the review's source-binding and sparse-FMP bypasses. Primary membership,
  identity events, and both QA evidence sets now arrive only through attested transformers that
  recheck their file against a verified manifest. Tiingo and FMP provider records arrive only from
  immutable manifest/raw-file transformers; their result objects cannot be caller-constructed.
  The trusted producer derives the audit population from consecutive primary snapshots, derives
  delistings from the identity source, and performs FMP reconciliation itself against the exact
  Tiingo-derived canonical data.
- 2026-09-13: Added immutable, resumable FMP acquisition for all three required supplemental
  endpoint classes with plan/API/licence metadata, checkpointed successes/failures, secret
  redaction, prior-manifest resume binding, raw hashes, and a strict transformer. Tiingo manifests
  now also require an explicit reviewed licence/terms label.
- 2026-09-13: Closed the FMP request-integrity review finding. The transformer now reconstructs
  every endpoint-specific request ID from canonical symbol/security/date parameters, rejects
  parameter tampering, and requires bounded, chronological, unique price/dividend/delisting rows.
- 2026-09-13: Removed primary event IDs and stable security IDs from the independent membership-QA
  schema. QA observations are now matched in-process by source-native symbol/action/date only;
  missing, duplicate, or ambiguous per-source matches fail the sampled event closed.

## Discovered work and decisions

- Phase 3 requires honest separation between validation infrastructure and admissible market
  evidence. The checked-in synthetic fixture can prove engineering behaviour but cannot make
  the mandatory deployment gates pass or justify paper trading.
- The worktree begins dirty with Phase 2 implementation and documentation. Phase 3 changes
  must preserve those files and avoid reverting unrelated edits.
- A trade-return bootstrap reports the distribution of mean closed-trade return only. Portfolio
  CAGR, drawdown, Sharpe, and horizon returns are derived from stitched daily portfolio returns,
  avoiding the invalid assumption that overlapping trades each deploy the full account.
- The final roadmap exit is deliberately distinct from engineering completion: it requires an
  admissible real dataset and an actual all-gates-pass report.
- Version-pinned open-source membership + Tiingo is the selected initial real-data route.
  CRSP/WRDS is not a Phase 3 prerequisite; an independent rerun on a higher-assurance dataset is a
  later confidence check if results justify it. The current `pitindex` + Yahoo route remains a
  retired, permanently inadmissible fallback.
- 2026-09-15 re-verification corrected the earlier stale source finding:
  `chinobing/historical_sp500_constituents` is public and active. The approved sources are checked
  out locally at commits `6e06d3a2fdb81105a55edd3f33a460ca997d8316` (chinobing),
  `dd1604c5176176f6cf6418c2a4bab0277b51d4ff` (unliftedq), and
  `016212b68791b6ca476b34c63634719115080d40` (riazarbi). Origin/HEAD/tracked-file manifest
  generation is now performed by a fail-closed CLI rather than trusting declared URLs.
- Direct inspection found limitations that must remain visible: the chinobing snapshot has only
  442–505 symbols per date (below 490 through 2017-07-25), unliftedq's event audit begins in 1999,
  and riazarb contains iShares IVV—not SPY—holdings beginning 2006-10-31. The riazarb repository
  has no detected licence file. These facts prevent a claim of complete 1996-present coverage
  until resolved or the admissible validation horizon is explicitly narrowed.
- Independent validation review found and closed a caller-boolean trust bypass: the generic
  workflow can no longer mark a run paper-ready without typed, fully validated producer evidence,
  and closed-trade evidence must both open and close within the stitched OOS period.
- Independent data, validation, and delivery audits ran during implementation and their material
  findings were fixed. Subsequent review turns could not run because the agent workspace reported
  that it was out of credits; the missing re-review is not treated as a pass.
- The latest independent delivery re-review confirms FMP request binding and installed-entry-point
  configuration are closed. It still finds two locally actionable P1 gaps: execution records are
  not exact-set reconciled to a content-bound native backtest run, and trusted producer evidence
  has no supported path into an admissible native validation report. Git-origin authenticity and
  real-source availability remain operator-controlled blockers.
- 2026-09-15: Removed the circular execution assertion from canonical dataset production.
  `TrustedDatasetEvidence` now covers only manifests, membership/identity, corporate actions, and
  the canonical dataset hash; `momentum-historical-build` no longer accepts `--execution-audit`.
  The generic workflow remains deliberately inadmissible until native run execution certification
  binds the complete decision/order/fill population.
- 2026-09-15: Added `momentum-git-source-snapshot` and adversarial tests. It accepts only approved
  source-role/origin pairs and derives the commit and file hashes from clean tracked checkout
  state. Real manifests were generated for the approved chinobing and unliftedq commits under the
  ignored `data/local/phase3_manifests/` directory.
- 2026-09-16: Added immutable native execution traces and an attested exact-set auditor. It binds
  baseline/stressed decisions, order intents, fills, missing-open dispositions, corporate-action
  settlements, next-session timing, cost economics, calendar hash, dataset manifest, strategy,
  configuration, validation specification, and run identity. Missing opens now fail certification.
- 2026-09-16: Corrected identity construction for symbol reuse. In strict temporal mode a successor
  symbol's earlier history remains a distinct security (for example, historical ANTM and WLP may
  coexist); the post-event symbol inherits only the predecessor's identity from the event date.
- 2026-09-16: Made FMP genuinely optional supplemental QA. The user-authorized minimum is the
  three pinned Git sources plus Tiingo; omitting FMP no longer prevents canonical production, while
  supplied FMP extracts retain their strict reconciliation path.
- 2026-09-16: Generated a membership-bounded Tiingo plan with a 400-calendar-day feature warm-up:
  1,175 identity-alias requests replace the invalid all-symbol 1996-present plan. Acquisition is
  resumable and immutable. A first live pass preserved successful extracts, distinguished genuine
  provider-history misses from throttling, and added exponential/`Retry-After` handling.
- 2026-09-16: Hardened quota interruption behavior. A persistent HTTP 429 now stops the run after
  bounded backoff and preserves a resumable checkpoint instead of labeling the unattempted tail as
  failed. A CLI-level regression test proves membership-bounded aliases, warm-up dates, and full
  benchmark coverage.
- 2026-09-16 independent review found that exact event reconciliation alone did not prove the
  supplied native results came from the claimed canonical dataset/configuration/strategy/spec.
  That task was reopened; no execution certificate is currently accepted as deployment evidence.
- 2026-09-16: Closed three other review paths. Trusted dataset production now requires each Git
  checkout's actual approved origin, current HEAD, tracked files, clean state, and manifest commit
  to be revalidated at consumption time. Certified QA must carry source-native parser attestation;
  caller-normalized three-column event files are rejected. Tiingo manifest v2 binds the complete
  request plan, preserves prior failure history, and recovers safely from interruption between raw
  payload and manifest commits using a hash-bound pending file. Disjoint membership spells remain
  disjoint requests rather than downloading long non-membership gaps.

- 2026-09-21: Completed Tiingo Power acquisition: 1,220 planned requests produced 832 immutable
  successes and 388 explicit unavailable histories, 3,095,690 daily bars, and 39,450 corporate
  actions. No unavailable history was fabricated or backfilled from a QA source.
- 2026-09-21: Built and certified `data/local/phase3_build_v3`. The evidence-driven universe
  begins validation on 2011-07-01 only after sustaining at least 400 price-eligible constituents
  on every session (range 400–488); its feature-certification warm-up begins 2010-05-27. Eighteen
  observed quality findings create dated forward quarantines. The 75-event membership QA sample
  has 64 events corroborated by one or both riazarbi streams.
- 2026-09-21: Completed the native canonical walk-forward implementation and closed independent
  findings covering trading-session embargo, fold-reset validation, sequential OOS hysteresis,
  fold-varying cost rejection, OOS trade bounds, raw-price eligibility, aligned benchmark returns,
  bootstrap provenance/horizons/trade summaries, honest unexecutable ablations, and OAT design
  documentation.
- 2026-09-21: A further independent trust audit found and the implementation fixed two P1 issues:
  the validation identity now binds exact dataset evidence plus universe policy, and certification
  requires valid, unique policy rows exactly matching every canonical benchmark session from the
  validation start rather than trusting a sparse self-reported subset.

## Evidence

- Python 3.12.14: the latest 2026-09-16 gate passed 266 tests in 39.27s; Ruff passed; strict mypy passed
  across 63 source files.
- The installed wheel ran the validation CLI twice from `/tmp`; byte-for-byte comparison of
  both JSON and Markdown outputs passed.
- `research_report.md` was regenerated from the supported CLI and inspected: seven folds,
  3,654 sessions, 133 fold/candidate sensitivity records, 2,000 seeded bootstrap iterations,
  all ablations and gates, and an explicit `FAIL CLOSED` decision.
- Direct research CLI inspection completed 380 sessions, 79 signals, 67 trades, and zero
  execution issues; it correctly marked the fixed synthetic universe inadmissible.
- A direct Yahoo SPY probe returned five daily rows from 2007-01-03 through 2007-01-09. The
  bounded pitindex export resides under ignored `data/local/public_reconstructed/`, with its
  package snapshot limiting coverage through 2026-07-13.
- A clean Python 3.12 environment installed the rebuilt 0.2.0 wheel after the latest FMP and QA
  hardening; all seven installed CLI entry points returned help successfully. The installed validation CLI
  reproduced byte-identical JSON and Markdown across two runs, and the inspected report explicitly
  says `FAIL CLOSED — not ready for paper trading`.
- The latest sdist and wheel built successfully. A fresh environment installed the wheel and all
  nine installed CLI entry points returned `--help` successfully.
- The Tiingo Power membership-spell-bounded plan contains 1,220 requests, 1,160 unique provider
  symbols, and 1,153 stable identities. Acquisition completed with 832 successes and 388 explicit
  unavailable histories retained rather than fabricated.
- The universe policy is now explicit: primary point-in-time membership is intersected with
  Tiingo availability only for the affected request interval, with a 400 price-eligible-member
  floor on every validation session. Snapshot/session counts, unavailable requests, and daily
  coverage exclusions are written to `universe_policy.json` and its hash is bound into producer
  evidence. The intended request-plan hash must independently match the acquisition manifest.
- Native validation inputs now bind verified canonical content, config, validation specification,
  source tree, Git state, calendar, and cost models. Baseline and stressed executions are issued
  by the native executor and the bound audit requires identical market inputs and target sets.
- Latest verification after the universe/native-binding changes: 277 tests passed in 36.82s; Ruff
  and strict mypy passed across 69 source files; sdist and wheel builds passed. A fresh Python 3.12
  environment installed the wheel and ran the native-validation, historical-build, and historical-
  producer entry points. Two complete real native runs produced byte-identical JSON and Markdown.
- The authoritative report contains nine folds, 1,254 stitched OOS sessions, 162 sensitivity rows,
  2,000 seeded bootstrap paths with 11 reported distributions, six ablations, and all 13 mandatory
  gates. SHA-256: JSON `19dbd834da6264650a58120255d649c2575d137a7fa992a4f84a84c0f15c7fdb`;
  Markdown `98cef846cf0fc3a5da05b41c6be5d763c095517dbc52c6225dd7625675fb7e3c`.

## Blockers

- Data acquisition and producer certification are no longer blocked. The named sources are all
  present and used within their admissible roles. The universe is not forced to 500 names: it is
  primary point-in-time membership intersected causally with Tiingo availability and dated quality
  exclusions, with an exact 400-member daily floor. Riazarbi remains useful QA; neither stream
  defines or backfills the universe.
- The authoritative real native report is admissible but fails the strategy-performance exit gates.
  Its 2021-07-01..2026-06-30 stitched OOS result has -0.17% CAGR, 0.001 Sharpe, 15.03% maximum
  drawdown, 242 closed trades, and materially negative lower-tail bootstrap results; SPY CAGR is
  13.37%. Profit concentration is not assessable because cumulative net profit is negative, and
  parameter robustness fails. Phase 4 paper trading remains prohibited.
- Passing these gates requires a separately authorized, predeclared strategy redesign and a new
  untouched OOS evaluation—not weakening thresholds or tuning on the observed test period. This is
  the remaining product blocker after final packaging, determinism, and review closure.
