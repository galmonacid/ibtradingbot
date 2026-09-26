# Quantitative Strategy Specification — V2 Research Candidate

Specification date: 2026-09-22. Proposed strategy identifier: `monthly-momentum-v2`.
Roadmap stage: **Phase 3 V2 development implementation; not qualified**.

The implemented Phase 1–3 strategy and both YAML configurations remain V1. Its original
specification is preserved in [QUANT_SPEC_V1.md](QUANT_SPEC_V1.md); the phase delivery
records describe implemented conventions where that original document was ambiguous.
This document defines the fixed V2 candidate. The separate `momentum-v2-validation`
command and `config.phase3-v2.yaml` implement development research; original commands
remain V1. See [implementation status](PHASE3_V2_IMPLEMENTATION.md) and
[delivery record](../GOAL-PHASE3-V2.md) for verification and remaining evidence gaps.
It does not authorize paper trading, live trading, new data purchases, or ML.

## 1. Objective and acceptance

Build a reproducible, long-only momentum system for liquid US common stocks, intended for
an IBKR UK Stocks & Shares ISA with £1,000–£3,000. Preserve the aspiration of **10–20% net
annualized return over a full market cycle**. This is a research objective, not a forecast
or guarantee. A specification cannot establish that these objectives are achievable.

The existing mandatory gates in [BACKTEST_AND_VALIDATION.md](BACKTEST_AND_VALIDATION.md)
remain unchanged: OOS CAGR >= 8%, Sharpe >= 0.8, maximum drawdown <= 15%; stressed CAGR
>= 6% and Sharpe >= 0.6; at least 150 closed trades; year/stock profit concentration
<= 35%/20%; parameter robustness; and the bootstrap and data-admissibility gates.
An 8–10% result can pass the minimum return gate without meeting the aspirational target.

Optimize in this order: valid evidence and account safety, drawdown/cost resilience,
stable risk-adjusted return, then return. Do not increase leverage, position limits,
the volatility target, or gate tolerances to force a desired CAGR. If the candidate fails,
retain cash and report failure. Additional strategies remain later-roadmap work.

## 2. What Phases 1–3 established

| Evidence | Result | Consequence |
|---|---|---|
| [Phase 1 delivery](../GOAL.md) and [conventions](PHASE1_BASELINE.md) | 64 tests and deterministic synthetic runs recorded; causal execution and accounting exercised | Reuse the engineering foundation; no investment-performance inference |
| [Phase 2 delivery](../GOAL-PHASE2.md) and [conventions](PHASE2_RISK_PORTFOLIO.md) | 99 tests recorded; sizing, hysteresis and circuit breakers exercised on synthetic data | Preserve risk controls; fixture performance cannot select a strategy |
| Root [research_report.md](../research_report.md) | Synthetic, fixed universe; 6.75% CAGR and 4.68 Sharpe are inadmissible | Do not confuse this fixture with real historical evidence |
| [Phase 3 delivery](../GOAL-PHASE3.md) and local native report | Certified PIT data; nine folds and 1,254 stitched OOS sessions, 2021-07-01–2026-06-30 | Valid evidence of V1 failure; this period is now development data for V2 |

The authoritative native artifacts remain local and ignored:
`data/local/phase3_build_v3/research_report.{md,json}`. Their verified SHA-256 values are:

```text
Markdown: 98cef846cf0fc3a5da05b41c6be5d763c095517dbc52c6225dd7625675fb7e3c
JSON:     19dbd834da6264650a58120255d649c2575d137a7fa992a4f84a84c0f15c7fdb
```

| Real native result | CAGR | Sharpe | Maximum drawdown |
|---|---:|---:|---:|
| V1 full strategy | -0.174% | 0.001 | 15.027% |
| V1 stressed costs | -0.368% | -0.031 | 15.514% |
| SPY reference | 13.367% | 0.816 | 24.497% |
| Full minus regime component | 0.957% | 0.142 | 15.125% |
| Full minus inverse-volatility sizing | 0.059% | 0.037 | 10.346% |
| Full minus drawdown controls, diagnostic only | 6.388% | 0.557 | 17.079% |

Native ablation names identify the **removed** component. The `momentum` row is
unexecutable, not a momentum-only baseline. No reported removal passes the mandatory
gates. Removing drawdown controls is neither sufficient nor permitted for an operational
candidate. V1 has 242 closed trades, failed parameter robustness, and unassessable profit
concentration because net profit is negative. Worst bootstrap tails are -5.163% CAGR
(q05), -1.159 Sharpe (q05), and 28.378% drawdown (q95). Only two of 13 gates pass.

These findings justify testing a simpler construction, not claiming to have identified
the cause of every loss. The native summary does not establish whether turnover, signal
quality, cash exposure, or halt duration dominates failure. The native executor defaults
to $100,000 and the research ledger is USD: this is not evidence of £1,000 ISA feasibility.
The 400-member certified universe floor is a coverage control, not a claim of complete
S&P 500 coverage or absence of provider-availability selection bias. Retain those limitations.

## 3. Redesign hypotheses

| V1 design | V2 candidate | Testable hypothesis |
|---|---|---|
| Weighted momentum, trend, volatility and drawdown ranking | One prior-year momentum rank excluding the recent month | Fewer overlapping score terms reduce fragility |
| Weekly selection and resizing | Monthly selection with a no-trade band | Fewer discretionary orders improve small-account net economics |
| Inverse-volatility allocation | Equal weight before portfolio risk scaling | Avoid loading both selection and sizing toward low-volatility names |
| SPY trend, breadth and expanding volatility percentile gate | SPY trend alone; breadth remains a diagnostic | Simpler regimes may reduce unnecessary cash exposure |
| 20-session covariance sizing | Maximum of 20- and 63-session portfolio risk estimates | Retain shock sensitivity while checking longer-window risk |
| $100,000 USD research default | Explicit £1,000 and £3,000 feasibility runs | Measure the intended account's economics |

All are hypotheses. Initial V2 development runs have failed; they are not qualification
evidence. Current results and limitations are recorded in the delivery record. Monthly prior-(2–12)-return
formation is an established research convention in the
[Kenneth French momentum definition](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html).
V2's daily-session approximation and concentrated long-only portfolio differ from that
diversified long–short factor; its published returns are not V2 evidence.

## 4. Universe and data

Retain certified Phase 3 source roles, stable security identities, dated membership,
quality quarantines, corporate-action treatment and provenance. No fixed current universe,
future-availability screen, new fundamental inputs, sector classifications, or QA-source
backfills. All eligible PIT members enter ranking; no arbitrary first-50 cap.

At decision close `t`, require US-primary common-stock status, raw close >= $10, trailing
20-session median raw close times volume >= $500M, and **253 consecutive exchange-session
adjusted closes through t**. These are XNYS sessions, not compressed available bars.
The 253 observations support `P[t-252]` through `P[t]`; missing observations exclude the
name with a reason. Live ISA eligibility and fractional capability must later be verified
for the exact instrument/account; current broker metadata must not be backdated.

Use total-return-consistent adjusted closes for signals. Use raw tradable prices, recorded
actions and causal share accounting for fills; never apply future action knowledge to an
earlier decision. SPY is a reference and regime input, not an added tradable holding.
Unavailable held data blocks new risk and invalidates certification unless a documented
corporate-action disposition resolves it. Never invent a liquidation price.

## 5. Signal and monthly selection

For each eligible name, using exchange-session offsets:

```text
M_i(t) = P_i[t-21] / P_i[t-252] - 1
SMA200_i(t) = mean(P_i[t-199], ..., P_i[t])
```

This is a 231-session return ending 21 sessions ago, **not** a 252-session return ending
21 sessions ago. Rank descending by `M` among names with `M > 0` and `P[t] > SMA200[t]`.
Ties use ascending stable security ID. No z-score blend, trend bonus, volatility penalty,
drawdown penalty, or ML probability enters ranking. Missing inputs fail eligibility.

Target four names, with zero permitted and five the absolute maximum. At each monthly
selection, retain eligible actual incumbents ranked <= `2N` (8 by default). Fill remaining
vacancies from ranks <= `N` (4), in rank order. Buffered incumbents are not displaced
merely to admit a higher-ranked newcomer. No forced replacement, minimum holding period,
profit target, or maximum holding period. Holding duration is a measured outcome.

Select after the last XNYS session close of each calendar month. Execute no earlier than
the next XNYS session's open with costs. Boundaries come from the pinned calendar, never
the last available row of a truncated dataset. Failed/skipped entries do not become
incumbents. Corporate-action and instrument-ineligibility exits are mandatory when known;
ordinary momentum/rank/stock-trend exits occur at monthly selection.

## 6. Regime and event priority

At each completed exchange week's final close, compare adjusted SPY close with SMA200:

```text
SPY_close > SPY_SMA200: regime ceiling = min(100%, 1 - configured_cash_buffer)
SPY_close <= SPY_SMA200: regime ceiling = 0%
```

The default 2% cash buffer implies a 98% risk-on ceiling. Initialize risk-off until a
valid weekly observation exists. Month-end uses the most recently completed weekly
observation, including that close if also week-end. Risk-off schedules liquidation next
executable session. Re-entry and exposure increases wait for monthly selection. Breadth
and SPY volatility remain diagnostics, not extra entry vetoes.

At each close, priority is: data/reconciliation failure; hard account halt; mandatory
liquidation/eligibility exit; soft drawdown and concentration/cash/volatility reductions;
then monthly selection and discretionary sizing. Merge colliding intents into one feasible
portfolio, with sells funding buys and no duplicate orders. Risk reductions never create
unrelated buys. Missing SPY inputs block increases; retain the last valid regime only for
non-increasing holdings while flagging invalid evidence, never assuming risk-on.

## 7. Allocation and risk budget

For `n` selected names, calculate:

```text
b_i = min(regime_ceiling / n, 0.30)       # n = 0 or risk-off means all cash
sigma_L(b) = sqrt(b' * Cov_L * b)         # L in {20, 63}
sigma(b) = max(sigma_20(b), sigma_63(b))
k = min(1, 0.12 / sigma(b))
w_i = k * b_i
```

`Cov_L` is 252 times sample covariance of L aligned daily adjusted returns known at that
close. Missing, non-finite, zero-risk or invalid covariance inputs fail closed and are
reported. Do not divide by zero for an all-cash target. No leverage-up to reach 12%; cash
receives the residual. Remove V1's 10% allocation floor; tiny proposed entries instead
face the order feasibility check. Fewer candidates can mean much less than full exposure.

At every daily close, check actual weights against both risk estimates, the active name
cap, regime ceiling and cash buffer. Breaches schedule only necessary downward adjustments
next executable session: first remove mandatory exits, clamp each remaining weight to
its active name cap, scale the remaining vector down uniformly to the applicable gross
ceiling, then scale it down by `min(1, 0.12 / sigma)` using that vector's risk estimate.
Do not redistribute any released weight. Recheck the complete plan against post-cost
equity and round conservatively; an infeasible plan fails closed and is reported.
Risk capacity is restored only at monthly selection. A 12%
estimated volatility ceiling does not guarantee a 15% maximum realized drawdown. Preserve
gap/delay stress and report time outside limits due to market moves.

The unchanged account overlay has precedence:

- Drawdown >= 10% from the non-decreasing high-water mark: cap each name at 15% and prevent
  target gross exceeding the previous accepted target. No redistribution to increase
  another name during a risk-only adjustment. The soft state clears only when marked
  drawdown becomes less than 10%; increases still wait for month-end.
- Drawdown >= 15%: liquidate next safely executable session, block entries, and permanently
  latch the simulated account in risk-review. No monthly/fold reset or timed re-enable.
  A later live account requires explicit human review and re-enable.
- No shorts, margin, derivatives or leverage; <= 5 holdings; <= 30% per holding; gross
  <= 100%; preserve the configured cash buffer after costs and rounding. Market drift
  can breach a cap between observations; flag and reduce it, never claim continuous protection.

The optional V1 -12% single-name stop remains deferred pending its documented data/action
checks. Do not assume it exists or tune it to repair results. The account halt is an
operational circuit breaker, never a selectable strategy parameter.

## 8. Turnover and account feasibility

At monthly selection, skip an incumbent's discretionary resize when absolute target minus
actual weight is **less than 3 percentage points**; exact-boundary trades are eligible.
The band applies only when retaining the holding satisfies every risk constraint. It
never suppresses full exits, hard/soft reductions or concentration/cash/volatility
corrections. Apply it before whole-portfolio feasibility checks; retained weights cannot
make the final plan exceed cash or risk ceilings. Risk takes precedence over the band.

Use the existing £150-equivalent minimum for entries and discretionary resizes. Never
round a small order up to that value or redistribute skipped buys into other holdings.
Mandatory exits/reductions below the minimum must still execute, including fractional
residuals when supported: economic minimum size cannot block account safety. This is the
explicit V2 clarification of the blanket minimum-order wording. Skipped buys leave cash;
rounding that leaves a cash/cap violation fails the proposed plan closed.

Simulate the full plan against post-cost equity. Verify fractional capability; also test
whole-share rounding down. If neither supported mode is feasible at a capital level,
that level is not deployable. Selection state follows actual fills. Broker integration
remains Phase 4; no broker connection is required for this research.

Cost floors remain $0.35 per executed order, 5 bps slippage per side and the existing 5 bps
per-side FX friction buffer. Stress remains $0.70 commission and 10 bps slippage with
unchanged FX buffer, plus a separate extra-session execution-delay run. These are model
floors, not verified current ISA fees. Before qualification, pin the applicable broker
tariff and conversion method and use the more conservative model. Do not fit delay or
commissions as alpha parameters. Report actual conversion fees separately without silently
dropping the conservative FX buffer.

For both £1,000 and £3,000 require timestamped GBP/USD data, separate GBP/USD cash balances,
conversion timing/fees, minimum-order checks and rounding. Record the FX source/licence
before acquisition; this input is **not provided by the current native pipeline**.
Use `GBP value = USD value * GBP per USD`. Measure objectives, drawdown and fees in GBP
as well as USD. Cash earns zero unless account eligibility, rates and accruals are
established; do not assume T-bill interest is available to the account.

## 9. Predeclared research protocol

### Development and diagnosis

Treat all inspected history, including V1's 2021–2026 OOS and earlier validation, as V2
development evidence. Reproduce V1 with its original artifacts first. Preserve both
reports; never represent the root synthetic fixture as real market evidence.

On identical certified dates/costs, report V1, fixed V2, and single-change diagnostics:
V1 with only monthly scheduling, only the new score, only equal weighting, only the
simpler regime, and only the new covariance rule. Also run V2 without its discretionary
band. Keep remaining components fixed, including account safety. Disclose supporting
interface changes. Unexecutable variants fail; do not fabricate returns. Existing
no-drawdown-control ablations remain counterfactual diagnostics and cannot qualify.

Report gross/net returns, commission/slippage/FX totals, buy-plus-sell turnover, order
counts, completed position episodes, FIFO lots, holding duration, exposure, cash time,
regime transitions, exit reasons, first soft/hard halt date, time halted, pre-halt and
full-period results, and all required annual/stock/bootstrap metrics. Continue accounting
after halts; never truncate away cash years. Preserve the 150-lot gate and additionally
require 150 completed position episodes for V2; split exits cannot manufacture evidence.
An episode runs from a stable security ID's first fill from zero holdings until holdings
return to zero; partial resizes and ticker changes do not start another episode. Both
entry and final exit must lie inside the qualifying test period.

### Fixed sensitivity design

This table defines the fixed configuration contract implemented by `src/config/v2.py`.
The development CLI exposes typed values and preserves the fixed sensitivity center. Keep the center fixed; use
one-axis-at-a-time alternatives as fragility tests, not a search for the best historical
return. Publish unsuccessful variants; costs/delays are stresses, not tunable alpha.

| Axis | Baseline | Diagnostic alternatives |
|---|---|---|
| Positions | 4 | 3, 5 |
| Signal numerator offset | 21 sessions | 10, 42; denominator remains t-252 |
| Selection schedule | Last session of each month | Penultimate monthly session; every second completed exchange week anchored in the run manifest |
| Stock SMA | 200 | 160, 240 |
| SPY SMA | 200 | 160, 240 |
| Portfolio volatility ceiling | 12% | 10%, 14% |
| Longer covariance window | 63 | 42, 84; keep the 20-session comparison |
| Discretionary band | 3 percentage points | 0, 5 percentage points |

Require nearby net CAGR >= 6%, Sharpe >= 0.6 and drawdown <= 15% in at least 80% of these
16 non-baseline variants (at least 13), including at least one viable neighbor on every
axis. Unexecutable variants count as failures. The baseline independently passes all
stricter mandatory gates. This explicit V2 rule supplements the existing robustness
requirement; cost/delay stresses cannot rescue a failed axis. Disclose the same checks
on fresh test data without using that test to choose a different candidate.

### Freeze and unseen evaluation

Before qualification, record a freeze manifest binding strategy/spec, source revision
and tree hash, config, costs, universe policy, currencies, calendar, data cutoff, complete
sensitivity list, benchmark rules and test endpoint. Implementation must enforce this
boundary; today's documentation is not a completed freeze.

The default untouched test starts on the first XNYS session after implementation/config
freeze. Start each capital scenario once in cash with its own account high-water mark;
use earlier prices only to warm up trailing features and regime state. Accumulate at
least 756 sessions and both trade-count requirements; evaluate at
the first calendar year-end satisfying those minima. Predeclare that endpoint rule;
do not stop after a favorable run or silently extend a failed test. Safety failures are
recorded immediately. Offline forward research needs no broker paper connection.

Already observed dates, including July–September 2026, are not automatically untouched
because the old report ends in June. An alternative historical holdout needs documented
prior non-access, certified coverage and a frozen protocol; none is established here.
A second vendor on the same dates checks data robustness, not independence of the strategy
decision. Do not shorten training windows to rename inspected history as fresh OOS.

Keep portfolio, high-water mark and hysteresis continuous across test/fold boundaries.
Any adaptive walk-forward challenger retains expanding 8-year training, 2-year validation,
1-year test and 6-month step, the 20-session embargo and unique OOS stitching. It is a
separately registered experiment, not the fixed V2 qualification run. Material post-freeze
changes require a new version and new untouched evaluation.

### Qualification decision

Apply all 13 existing gates to the fresh continuous after-cost path, including >= 2,000
seeded daily/regime bootstrap paths and unchanged tail thresholds: worst q05 CAGR and
Sharpe >= 0; worst q95 drawdown <= 25%. Require GBP small-account paths as additional
evidence; preserve USD comparison rather than choosing whichever currency passes.
Report SPY buy-and-hold, zero-return cash and a SPY reference using V2's regime/risk budget
on the same dates and comparable costs. References are diagnostic, not new holdings.
The risk-budget SPY reference uses the same regime, volatility ceiling, currency and cost
assumptions; it is a single-asset benchmark exempt from the strategy's 30% single-stock
cap and must be labelled as such. It cannot itself be certified as this stock strategy.

Distinguish: working research infrastructure; promising development; passed minimum
deployment gates; achieved aspirational return. Any missing/failed gate blocks Phase 4.
Passing £3,000 while failing £1,000 does not authorize the planned £1,000 launch. Monthly
selection may accumulate evidence slowly; never increase turnover to satisfy trade count.

## 10. Implementation sequence and tests

Keep work within Phase 3 until qualification:

1. Preserve/reproduce V1; complete attribution reporting and small-account/GBP inputs.
2. Add an explicit V2 version/config; implement session-offset momentum, monthly scheduling,
   selection from fills, and weekly SPY regimes.
3. Add equal-weight risk scaling, daily reductions, the discretionary band and economic
   order sizing without changing broker interfaces or hard account limits.
4. Bind new inputs/state/config/spec to native provenance and execution certification;
   extend sensitivity/ablation reporting without weakening V1 validators.
5. Publish development experiments; reject V2 or freeze it for untouched evaluation.
   There is no automatic advancement to paper trading.

Required tests: exact return endpoints; 253-session warm-up and missing-session exclusion;
prefix invariance; holiday/month-end timing; deterministic ties; rank buffering; weekly
risk-off/monthly re-entry; covariance alignment/invalid inputs; downward-only risk events;
unchanged 10%/15% transitions; permanent hard halt across folds; band boundaries; failed
fills not becoming incumbents; small mandatory sells; fees/rounding at £1,000/£3,000; causal
GBP conversion; post-cost cash/caps; byte-identical reports with fixed provenance. Run
pytest, Ruff, mypy and build checks after implementation. The implementation delivery record distinguishes verified behavior, development results,
remaining input gaps and qualification. No improvement or deployment readiness is presumed.

## 11. Deferred ML

ML remains disabled until deterministic historical/operational gates pass and Phase 6
begins. It may filter candidate trades using purged chronological validation. Retain it
only for OOS Sharpe improvement >= 0.10, drawdown reduction >= 2 percentage points without
materially lower return, or materially lower turnover with preserved return. V1's tentative
labels/models remain historical notes, not permission to repair a failed baseline with ML.
