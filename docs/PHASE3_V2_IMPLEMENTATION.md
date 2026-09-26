# Phase 3 V2 research implementation

Status: development implementation and independent review complete. The candidate failed
development gates. No qualification or paper-trading permission.
The authoritative product candidate remains `QUANT_SPEC.md`; V1 commands and configurations
are preserved. New files have separate V2 entry points so old research remains reproducible.

## Research command

Install the historical-data and development extras using the project's supported Python 3.12
setup. `momentum-v2-validation --help` documents the new offline command. A complete local run:

```bash
momentum-v2-validation \
  --canonical-manifest data/local/phase3_build_v3/canonical/canonical_manifest.json \
  --config config.phase3.yaml --v2-config config.phase3-v2.yaml \
  --validation-spec docs/PHASE3_HISTORICAL_VALIDATION.md \
  --strategy-spec docs/QUANT_SPEC.md \
  --dataset-evidence data/local/phase3_build_v3/dataset_evidence.json \
  --universe-policy data/local/phase3_build_v3/universe_policy.json \
  --calendar data/local/phase3_v2/calendar.csv \
  --fx-csv data/local/phase3_v2/fx.csv \
  --fx-manifest data/local/phase3_v2/fx_manifest.json \
  --start 2021-07-01 --end 2026-06-30 \
  --run-timestamp 2026-09-26T08:00:00+00:00 \
  --v1-anchor data/local/phase3_v2/v1_anchor.json \
  --output-directory data/local/phase3_v2/audited_full_final_v2
```

The timestamp is explicit reproducibility metadata, not a freeze timestamp. `--baseline-only`
is an incomplete diagnostic, never the full experiment. Reports and exact ledgers must reside
under ignored local output directories. The command never connects to IBKR or places orders.

The full matrix contains £1,000 and £3,000 whole-share accounts, each with baseline, stressed
costs, one extra session delay, and all 16 predeclared sensitivity neighbors. Each run begins
once in cash. Account state and the hard halt carry through the entire period. V1 single-change
controls and fixed V2 are also reported on identical dates and V1 cost rates in a labelled
$100,000 USD comparison; their engine differences and synthetic unit-numeraire adapter are
explicit. Benchmark reference ledgers cannot relax stock-strategy limits.

## Implementation boundaries

- `src/config/v2.py`: strict versioned configuration and fixed one-axis sensitivity design.
- `src/strategy/v2.py`: exact session endpoints, calendar boundaries, rankings, actual-fill
  incumbent selection, and weekly SPY state.
- `src/portfolio/v2.py`: aligned dual sample covariance, equal-weight targets, daily
  reductions, discretionary band and permanently latched drawdown state.
- `src/backtest/v2_execution.py`: atomic raw-share plan simulation, post-cost cash/caps,
  whole-share rounding, economic minimums, explicit conversions and cost attribution.
- `src/backtest/v2.py`: sequential decisions and fills, corporate actions, separate cash,
  non-spendable dividend claims, continuous GBP high-water mark, FIFO lots and episodes.
- `src/data/fx.py` and `fx_source.py`: immutable source-bound FX observations and ECB normalization.
- `src/validation/v2_*`: deterministic reports, native input binding, controls, references,
  fixed robustness criteria and pure freeze-boundary guards.

Safety reductions cannot create new share purchases after overnight price or FX changes.
An already pending risk reduction retains its execution deadline. Missing held prices abort
valuation instead of inventing an exit. Whole-share orders are never rounded up to £150.
An infeasible complete plan produces no simulated fills and an explicit reason.

## Input and qualification limits

Read `PHASE3_V2_INPUTS.md` for FX licensing and public tariff assumptions. The local calendar
is an explicitly empirical SPY-session calendar whose file extends beyond the run endpoint;
it is not independent XNYS calendar certification. ECB observations are retrospective
reference rates, not executable quotes or certified historical release vintages.

The strict configuration default permits FX observations up to four calendar days old.
The development YAML explicitly uses six days to cover TARGET holiday closures plus the
normalizer's next-calendar-day availability. This affects a reference-rate simulation only;
it does not make stale market quotes executable or qualify the archive for deployment.

The canonical security master lacks dated US-primary/common-stock classifications. Membership
therefore cannot certify those additional V2 eligibility requirements. Canonical dividends lack
payment dates: the simulator records ex-date receivables but does not spend them. Tax withholding
and account-specific currency conversion/fractional permissions remain unverified. Public tariffs
are modeled conservatively, including a full £3 monthly fee without commission offsets.

All these gaps are reported. Development-gate comparisons use unchanged numerical thresholds
but always fail evidence admissibility. The future-test guard requires a matching freeze,
continuous post-freeze sessions, 756 observations, 150 closed lots and 150 independent episodes,
and the first qualifying calendar year-end. A pure guard is not execution certification.
No inspected historical result can supply an untouched V2 test.

## Verification record

See `GOAL-PHASE3-V2.md` for tests, review findings and exact local artifacts. The complete
development matrix executed all 38 account scenarios. The £1,000 baseline placed zero orders
and lost 3.89% annualized through modeled fees. The £3,000 baseline placed 49 orders, closed
26 FIFO lots and 23 independent position episodes, with GBP CAGR -2.99%, Sharpe -0.82 and
maximum drawdown 15.45%. Neither capital had a viable fixed sensitivity neighbor. The result
rejects this fixed candidate for qualification; thresholds were not changed after inspection.

Every scenario ledger passed independent arithmetic reconciliation. The report retains exact
exclusion rows in each content-bound ledger and publishes compact counts by reason. FIFO
stock/year attribution cannot allocate every account-level cost, dividend claim and open-position
result, so the associated concentration gates remain unassessable rather than using partial P&L.
The gross view replays the same actual fills and currency transfers with cost refunds held idle;
it is not a frictionless reoptimization.
