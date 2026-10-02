# R3 backtest and validation contract

Status: R3.3 implements the shared development event simulator, cohort summaries and paired ML comparisons. Its fixed run failed the development objective and every ML promotion comparison, and retained fail-closed invalid accounts. The full R3.4 qualification/stress wrapper remains unimplemented and is not permitted after this stop result without a new scope decision. **Existing `assess_deployment_gates` accepts 8% CAGR and must not certify R3.** Historical gate outputs remain unchanged.

## Measure the user's objective

For an account funded with £3,000 and no subsequent external flows, `R12 = terminal_GBP_wealth / initial_GBP_capital - 1`. Define inception as the funding timestamp before the first eligible execution session. Evaluate at the last exchange-session close on or before the 12-calendar-month anniversary, reserving liquidation/conversion costs; never extend past one year to obtain a better outcome. Terminal wealth includes only supported recovery values and after-withholding entitlements; disclose unsettled cash and accruals. Report `R12 > 0.10` strictly, not >=10%, CAGR, deposits or pre-cost gains.

Deduct commissions, regulatory charges, spread/slippage, actual FX conversion costs, any conservative friction allowance, account charges, foreign withholding and recurring data/hosting/software costs. Report a bridge from gross returns to trading-net to all-in net; disclose any allowance that overlaps measured costs. If development expenses come from initial capital, debit them at inception; otherwise show them separately and publish an additional first-year economic result including them.

Evaluate a continuous account and monthly launch cohorts, each starting with £3,000. Net first-year profit must exceed £300 and terminal wealth must exceed £3,300. £1,000 scenarios are historical evidence only, not required R3 qualification runs. Publish first-year return, each cohort return, share above 10%, share below zero and below -15%, median, 5th/95th percentiles, maximum drawdown and time halted. Monthly overlapping cohorts are correlated; present non-overlapping annual cohorts separately and never treat every rolling window as independent evidence. No probability estimate is a guarantee or a causal forecast.

## Development and model selection

Use expanding chronological folds: initial 8-year training, 2-year validation, 1-year outer test, 1-year step. This replaces the legacy overlapping 6-month step in R3 to simplify unique test coverage. If clean history cannot support these windows, report insufficient evidence; do not shorten them after looking at results.

All old inspected dates remain development even in an outer test. Purge every training label whose [entry,exit] interval or availability overlaps the next evaluation segment. Use a 31-exchange-session boundary gap, and require all included labels to have matured; actual interval purging takes precedence if longer. No random row split, random early-stopping split, whole-dataset scaling or cross-sectional date leakage. The same causal rules apply to quarterly refits.

Run only the six configurations in QUANT_SPEC. Select on inner validation, first discarding candidates that breach safety/data rules; then rank by after-cost one-year target attainment frequency, median one-year return, and lower turnover in that order. Prefer the simpler model on exact ties. Disclose uncertainty and the whole trial ledger, including prior V1/V2 attempts. Test data never selects models, features, thresholds or training dates.

ML promotion additionally requires, on paired equal-date/equal-cost evaluation, at least **2 percentage points** higher median one-year net return than R3-M, no lower target-attainment frequency, no worse maximum drawdown and a positive 95% lower confidence bound for mean paired annual excess return. R3-T must also justify itself against R3-L by the same rule. These are predeclared research decision thresholds, not expected improvements. If inconclusive, prefer the simpler qualifying candidate; if none qualifies, stop.

## Retained safety and evidence gates

All gates are conjunctive; unassessable means fail closed. Apply to the qualifying continuous account in GBP, with USD diagnostics also published. The old USD outputs cannot replace the GBP objective.

| Gate | Required result |
| --- | --- |
| Data/execution admissibility | Complete, independently audited, content-bound causal evidence |
| Legacy return floor | OOS CAGR >=8%; this alone never meets the product objective |
| Risk-adjusted result | OOS Sharpe >=0.8 |
| Drawdown | OOS maximum drawdown <=15%; retain gap/delay stress and halt behavior |
| Stress costs | CAGR >=6%, Sharpe >=0.6, complete feasible ledgers |
| Profit concentration | <=35% of total positive net profit attributable to one year; <=20% to one stock; full P&L allocation required |
| Sample evidence | >=150 closed FIFO trades AND >=150 completed independent position episodes |
| Bootstrap tails | Worst across prescribed methods: q05 CAGR >=0, q05 Sharpe >=0, q95 drawdown <=25% |
| Sensitivity | At least 80% of registered neighbors pass CAGR >=6%, Sharpe >=0.6 and drawdown <=15%, with a viable neighbor on every axis |
| Product objective | First predeclared untouched 12-month account return >10% all-in net on initial £3,000 (terminal wealth >£3,300) |
| Repeatability of objective | Median unseen launch-cohort R12 >10% and 95% lower confidence bound of target-attainment frequency >50%; otherwise evidence is insufficient |
| Incremental value | ML passes paired uplift rule; chosen candidate also exceeds the comparable risk-budget broad-equity reference's median R12 after costs |

The new objective and uplift gates strengthen the prior contract; no old failed result becomes a pass. Profit concentration must reconcile open positions, dividends, realized gains, FX and all fees to total NAV change. Negative total profit or missing allocation cannot pass concentration. Split sales do not manufacture independent episodes.

Sharpe uses a documented risk-free convention shared by all comparisons; use zero only as an explicit existing development assumption. Cash earns zero unless actual account eligibility/rates support accrual; apply account fees even during halted/cash periods. A passive reference outside the account is separately labeled and uses its own verified costs.

## Stress, uncertainty and sensitivity

Run base tariff and conservative full-fee treatment, twice commission, 10 bps per-side slippage (or worse verified estimates), adverse FX friction and one additional session execution delay. Check gap losses, mandatory sub-minimum sells, whole-share affordability, missing held prices and corporate actions. Stress inputs are not alpha hyperparameters.

Freeze eight R3 portfolio sensitivity neighbors: target positions 3/5; volatility ceiling 10%/14%; market SMA 160/240; liquidity minimum $10m/$50m. Require at least 7/8 viable and at least one on each axis. Keep all other settings fixed. Model hyperparameters are the separate bounded selection budget; no sensitivity winner replaces a failed center. Report no-band and feature-group ablations as diagnostics without removing account safety.

Use >=2,000 seeded bootstrap paths, with 20-session daily blocks and complete regime-run resampling for retained legacy tail checks. These conditional historical checks can underrepresent halt/path dependence; add full-account path stress and never treat resampled returns as executable ledgers. For annual/cohort uncertainty and ML uplift use paired date blocks at least 12 months long, preserving cross-stock and cross-model alignment. If too few independent blocks exist, mark the intervals inconclusive rather than implying precision. Report all thresholds, seeds and interval methods before evaluation.

Compare cash, broad-equity total return, an attainable passive instrument where verified, the same regime/risk-budget reference, R3-M/L/T, and preserved V1/V2 controls. Label any benchmark exemption from single-stock caps. Share-period, numeraire, distributions, taxes and costs must be explicit.

## Freeze and fresh evidence

Freeze code/tree, configuration, model recipe, retraining schedule, tariff, cost budget, sources, split dates, benchmarks, sensitivity list and endpoint before accessing a holdout. None is frozen or qualified today. Default untouched evaluation starts at the first XNYS session after freeze. A historical alternative requires documented non-access; using a new vendor on old dates is robustness, not freshness.

The first 12-month endpoint is fixed and reported even if it fails. It is the one-year product test, not permission to deploy. Preserve the prior minimum of **756 fresh sessions**, 150 lots and 150 episodes, evaluated at the first calendar year-end meeting those minima. Keep state/high-water marks continuous, including every cash year after a halt. Do not extend a failed endpoint to search for a pass. A new strategy requires a new registration and new untouched evidence.

This can take several years and may remain statistically inconclusive. The user wants a one-year investment outcome; that does not establish a one-year safe-development timeline. No fresh evidence presently demonstrates the target.

## Paper and live progression

Paper broker integration waits until every historical/fresh gate passes. Require >=60 trading sessions of reconciled paper behavior, including partial fills, rejections, reconnects, stale data, corporate actions and independent risk tests. Paper profits do not prove alpha. Live orders require separate explicit authorization after these gates for the planned £3,000 starting account. Capital increases require at least six months operational stability and fresh review, never one good month.
