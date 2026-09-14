# Phase 3 Historical Validation

Phase 3 adds reusable validation primitives; it does not make the checked-in synthetic
fixture admissible evidence and does not authorize broker connectivity or order placement.

## Conventions

- Point-in-time membership uses half-open intervals: `effective_from` is inclusive and
  `effective_to` is exclusive. A blank end is open-ended. One file has one source version;
  intervals for the same symbol may not overlap.
- Walk-forward folds use actual exchange sessions and half-open calendar boundaries. The
  training window expands; validation and test remain chronological. With overlapping test
  windows, the earliest genuinely out-of-sample result owns a date, so no return is counted
  twice.
- Parameters are scored on validation data only. A candidate is selectable only when its
  validation score is within 20% of the best score and at least one one-dimension neighbour
  is also viable. Unsupported isolated optima fail closed.
- Bootstrap uses seeded circular moving blocks for daily returns, resamples closed trades
  for the mean-trade-return distribution, and uses complete contiguous runs for
  regime-labelled returns. Regime paths keep the final sampled episode whole and therefore
  may exceed the observed path length; CAGR is annualized using each path's actual length.
  Trade returns are not compounded as if every trade used the
  whole portfolio. An admissible analysis requires at least
  2,000 iterations. The default block length is 20 sessions. One- and three-year statistics
  are unavailable when the observed path is shorter than 252 or 756 sessions respectively.
- Ablations remove one component at a time from the full deterministic strategy—momentum,
  trend, regime, inverse-volatility sizing, and risk controls—then include the unmodified full
  strategy as the comparison anchor. ML is deferred to Phase 6 and is not an ablation.
- Profit concentration divides the largest positive contributor by net cumulative realized
  profit, including losing contributors in that denominator. If net cumulative profit is not
  positive, the gate is `NOT_ASSESSABLE`; it is never silently passed.
- Paper-trading readiness requires admissible point-in-time evidence and every mandatory
  gate to be `PASS`. A missing metric, fixed universe, synthetic dataset, or incomplete
  historical window fails closed.
- Bootstrap robustness is an explicit readiness gate. The configured defaults require the
  worst of the daily- and regime-block distributions to have 5th-percentile CAGR and Sharpe
  of at least zero, and 95th-percentile maximum drawdown no greater than 25%. These are
  lower-confidence viability checks, not substitutes for the stricter point-estimate gates.

## Required sensitivity scenarios

An admissible run must evaluate configured grids covering target positions, rebalance
frequency/day, recent-return skip, volatility target, breadth threshold, trend windows, and
momentum weights. It must also include one additional execution-day delay, 2x commissions,
and 10 bps slippage. All scenarios must reuse the same point-in-time dataset and OOS windows.

## Current evidence limitation

The repository contains a 380-session synthetic dataset and fixed seed universe. It is useful
for deterministic engineering regression tests, but it cannot establish historical return,
trade-count, robustness, bootstrap-horizon, diversification, or deployment-gate evidence.
Supplying a clean, versioned point-in-time universe and matching 2007-present daily
bars/corporate actions is an external prerequisite for the roadmap exit condition. It does
not require CRSP/WRDS: the planned initial producer uses version-pinned open-source membership
and identity records plus Tiingo, subject to the controls below.

## Historical-data approach: open-source membership + Tiingo

Phase 3's initial admissible-data target is a reproducible open-source membership + Tiingo dataset,
not a licensed academic dataset. `chinobing/historical_sp500_constituents` supplies the primary
1996-present dated S&P 500 membership snapshots. `unliftedq/index-constitution` supplies the
ticker-change and delisting event layer used to create the security-master identity history.
`riazarbi/sp500-scraper` and historical SPY holdings are independent membership-QA sources.
Tiingo supplies daily raw and adjusted OHLCV plus dividends and splits. Source snapshots, provider
responses, and derived canonical files must be kept separately and versioned; no source may be
refreshed in place.

### Supplemental FMP validation layer

The available FMP Basic endpoints strengthen validation but do not replace any primary source or
silently fill missing history. Retain their immutable responses and request metadata in the
manifest, and quarantine—not repair—material disagreements:

- `historical-price-eod/full` is an independent raw-OHLCV and last-tradable-bar coverage check
  against Tiingo. It must not supply adjusted returns, fill a missing Tiingo bar, or determine a
  historical execution price.
- `dividends` is an independent check of Tiingo dividend events. It must not replace Tiingo's
  corporate-action series.
- `delisted-companies` is an independent check of delisting dates and exchange metadata. It must
  not override the version-pinned identity-event layer or treat a missing FMP record as proof that
  an instrument was not delisted.
- `profile`, `search-symbol`, `quote`, and `historical-market-capitalization` are security-master
  enrichment and plausibility checks only. Current-state fields must never be projected backwards
  to establish historical eligibility, membership, or identity.

The FMP current constituent, historical constituent, and symbol-change endpoints are unavailable
to the configured account and are not dependencies of this route.

The canonical dataset is only eligible for validation after all of the following are recorded
in its manifest:

- retrieval timestamp, repository URL, commit SHA, source licence, request parameters where
  applicable, source file hashes, Tiingo plan/API version where exposed, and source-to-canonical
  transformation version;
- primary membership snapshots mapped into non-overlapping, dated intervals, with
  `index-constitution` ticker changes and delisted identities applied rather than treating a ticker
  as a permanent security identifier;
- Tiingo raw and adjusted daily bars, dividends, and splits, with per-security coverage and
  missing-data/exclusion reasons;
- reconciliation of raw-to-adjusted price behaviour against recorded split/dividend events;
- a randomly selected, reproducibly seeded audit of 50–100 primary-source constituent changes
  against `riazarbi/sp500-scraper` and historical SPY holdings, with every discrepancy resolved or
  the affected interval quarantined;
- explicit treatment of delistings. Missing delisting date, last tradable bar, or return/cash
  treatment is a data-quality failure—not permission to forward-fill, silently remove, or use
  a favourable terminal price.

Source licences, upstream update semantics, Tiingo access limits, and terms must be checked at
acquisition time. The project must pin Git source commits, throttle and resume Tiingo requests
safely, retain failed requests in the manifest, and never infer that an open-source snapshot or
free-tier response proves complete historical coverage. SimFin and SEC EDGAR may later add
point-in-time fundamentals for Phase 6; they are not inputs to S&P 500 membership construction.

## Validation artifact interface

`momentum-validation-pipeline` consumes an immutable JSON artifact produced by the historical
backtest layer. Required top-level fields are `sessions`, `verified_complete_through`,
`point_in_time_universe`, `complete_data_coverage`, `data_id`, `cost_id`, `grid_axes`,
`candidates`, `fold_results`, `evidence`, `ablation_returns`, `settings`, `dataset`,
`provenance`, `benchmark_metrics`, `stress_scenario`, and `limitations`. A non-synthetic
artifact must additionally provide hashed `source_files` and a next-session
`execution_audit`. Parameter-score keys are canonical
compact JSON objects with sorted keys. Each fold contains its own validation scores and test
returns for the parameter set selected in that fold. Stressed returns, regimes, and realized
closed-trade evidence are keyed or dated explicitly. The workflow derives performance,
trade-count, profit-concentration, and robustness gates rather than accepting reported gate
values. It reconstructs folds and requires an exact observation for every declared test
session; callers cannot inject arbitrary dates, mark synthetic inputs admissible, or override
failed admissibility flags. Required provenance includes Git state, config/data/universe/
calendar/corporate-action hashes and versions, strategy version, run timestamp, the canonical
session-list hash, and the final artifact hash.

Artifact hashes alone cannot prove point-in-time semantics or complete cross-sectional data.
The artifact-only CLI therefore always marks its output inadmissible for deployment. A future
trusted historical producer for the configured primary membership, identity-event, independent-QA,
and Tiingo sources must parse and cross-link the canonical membership, dated security metadata,
calendar, bars, corporate actions, decisions, and stressed fills in process. It may set
`deployment_admissible: true` and `paper_execution_permitted: true` only after all of the
following pass:

- source commits, licences, retrieval timestamps, and source-file hashes are pinned in the
  manifest;
- membership intervals, ticker successors, delistings, per-member coverage, and exclusions have
  been semantically validated rather than caller asserted;
- raw/adjusted Tiingo prices reconcile with recorded split and dividend events;
- supplemental FMP price, dividend, and delisting checks have either reconciled or quarantined
  material disagreements without backfilling Tiingo or primary-source observations;
- the seeded 50–100-event independent membership audit has no unresolved discrepancy; and
- the next-session execution and stressed-cost audit is complete, and every mandatory Phase 3
  deployment gate is `PASS`.

This eligibility permits entry to Phase 4 paper execution only. It does not permit live orders,
override Phase 4 reconciliation/idempotency/kill-switch controls, or waive the required paper
trading period. This is intentionally blocked rather than self-certified.

## Retired public reconstruction mode

`momentum-public-reconstructed` uses the optional `pitindex` package to export S&P 500
membership snapshots into canonical interval CSV. It never refreshes pitindex in place; the
manifest records the package version, source metadata, and output hashes. Its generated security
master is an explicitly labelled heuristic, and its manifest always has both
`deployment_admissible: false` and `paper_execution_permitted: false`.

Use this mode only to run a conservative public-data research challenge. It cannot satisfy the
Phase 3 exit condition or start Phase 4, even if its simulated gate values happen to pass. It is
retained for legacy regression coverage only; it is not the Phase 3 data plan.
