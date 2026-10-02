# R3 research strategy specification

Status: R3.3 implements the registered six-candidate scoring, quarterly fitting and common development simulator. The fixed experiment failed: momentum did not support the one-year objective and every learned configuration failed paired promotion. Existing V1/V2 code/configurations remain frozen research controls; no R3 candidate is qualified or permitted to advance.

## Objective and candidate set

Primary product outcome: GBP terminal wealth after 12 calendar months >£3,300 from an initial £3,000, net of costs (net profit >£300; return >10%). £3,000 is the sole required starting-capital scenario. Validation also assesses the frequency and uncertainty of that outcome across historical entry dates. A prediction score, CAGR or profitable month is not the objective.

Register exactly these candidate families on identical inputs and portfolio rules:

| Candidate | Score | Role |
| --- | --- | --- |
| R3-M | Adjusted close[t-21] / adjusted close[t-252] - 1 | Simple momentum control |
| R3-L | Ridge regression prediction of next-month excess return | Regularized ML baseline |
| R3-T | Shallow histogram gradient-boosted regression prediction of the same label | Nonlinear challenger |

All eligible names enter scoring; no V2 positive-momentum or stock-SMA veto precedes ML. Missing mandatory features excludes the name with a reason. Ties use ascending stable security ID. Train models on stock-month observations, weighting each date equally. No future return, trade closure, provider survival or future membership determines eligibility.

## Universe and capacity

Retain the point-in-time US common-stock scope and existing source lineage. Require contemporaneous primary-listing/common-stock evidence, raw price >= $10, 253 consecutive session closes, and 20-session median raw dollar volume >= **$20m**. This replaces V2's $500m research screen only in R3; it is a predeclared engineering capacity hypothesis, not a discovered profitable threshold.

Each order must also be <= 0.01% of trailing median daily dollar volume. Audit the $10m and $50m liquidity alternatives as two registered diagnostics; neither may replace the center after seeing qualification results. Corporate actions, missing histories and ISA permissions follow [data rules](DATA_AND_FEATURES.md). No current-only constituent list, arbitrary first-50 limit or provider backfill.

## Timing and selection

Calculate scores after the last XNYS session close of each calendar month. Execute no earlier than the following exchange-session open. A stock selected after close cannot fill at that close. Scheduled model refitting completes before signal generation; only matured labels are available.

Target four stocks. Retain eligible actual incumbents ranked <= 8, then fill vacancies from the top four names, with zero holdings permitted. No random tie-breaking, mandatory monthly replacement or minimum holding period. An unfilled target never becomes an incumbent. Eligibility exits and risk reductions take precedence over ranking.

Retain the weekly market-risk overlay for this experiment: SPY adjusted close above its 200-session SMA permits exposure up to 98%; otherwise target cash. Missing regime data blocks increases. Re-entry waits for month-end. This overlay is shared by all three candidates; do not let ML override it. Exposure and rejected-trade attribution must reveal whether it prevents the objective.

## Portfolio construction

Start with equal weights `min(regime_ceiling / number_selected, 0.30)`. Scale down, never up, to a 12% annualized volatility ceiling using the larger of the aligned 20- and 63-session sample-covariance portfolio estimates. Missing, invalid or zero-risk estimates block new risk. Unallocated capital stays cash; no leverage to compensate for low exposure.

Daily safety checks reduce breaches without reallocating released risk to other names. Preserve the 10% soft drawdown state (15% name cap and no gross increase) and the permanent 15% hard halt. Apply a 3-percentage-point discretionary resize band only when retaining actual holdings is feasible. Mandatory exits and reductions bypass the band and economic minimum.

Whole-share quantities round down. Reserve at least 2% cash plus any additional cash necessary for known near-term fees and mandatory liquidation; never borrow to fund fees. Check the entire post-cost portfolio against long-only, <=5 names, <=30% per name and <=100% gross. Report drift and blocked/infeasible orders.

Replace the blanket £150 discretionary minimum **in the new engine only** with a cost-derived floor: estimated complete round-trip variable cost divided by order notional must be <= 1%, using conservative sell costs, FX and slippage at decision time. Include broker lot minimums and the capacity limit. This 1% budget is an experimental ceiling, not evidence of profitable expected returns. Fixed account/operating costs remain in account-level feasibility. Do not round a small order upward to pass a floor. No minimum may suppress a necessary risk reduction.

## Features and labels

Use the fixed feature list and causal label definition in [DATA_AND_FEATURES.md](DATA_AND_FEATURES.md). Models forecast a one-month cross-sectional excess return; the portfolio's one-year return is assessed by simulation, not inferred by compounding model predictions.

R3-L uses training-fitted standardization and ridge regression; validation grid for alpha: 1, 10, 100. R3-T uses squared-error histogram gradient boosting, learning rate 0.05, 200 iterations, L2 regularization 1, min samples per leaf 100 and leaf counts 7 or 15. Disable automatic randomly split early stopping. Fixed random seed: 20260926. These five learned configurations plus the momentum control are the complete initial selection budget. Model retraining is quarterly on expanding eligible history; ranking remains monthly.

The technology choices are proposed additions, not installed capabilities. Record exact dependency versions, training cutoff, feature schema and model hash. A failed or stale model blocks new positions; it never silently switches to a better-looking model.

## Experiment boundary

Use a shared R3 event ledger for all candidates. Compare with preserved V1/V2 outputs only as historical controls; never confuse changed cost/universe rules with ML uplift. R3-L minus R3-M and R3-T minus R3-L comparisons isolate score changes within the common R3 policy. Separately attribute the liquidity and cost-floor migration before training.

Keep each £3,000 account, its holdings and high-water mark continuous across model updates and validation segments. For one-year launch cohorts, each cohort is a separate hypothetical account started once; restarting those accounts is not permission to reset a live halt. The full continuous account is always reported alongside launch cohorts.

Freeze before unseen evaluation. Neither favorable development results nor this document qualify a candidate. Use [all validation gates](BACKTEST_AND_VALIDATION.md); a failed center cannot be rescued by selecting a sensitivity neighbor.
