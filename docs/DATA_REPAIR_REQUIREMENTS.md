# R3 historical-data acceptance requirements

**Current policy, 2026-10-10:** the user authorizes faster bounded offline experiments with imperfect data and explicit sensitivity analysis. The [current iteration policy](ROADMAP.md#current-iteration-policy--2026-10-10) supersedes earlier blanket requirements here to complete all historical remediation or obtain renewed permission before development comparisons. Earlier records remain historical evidence. Qualification gates remain unchanged. The separately implemented diagnostic and its current status are documented in [NEXT_RESEARCH_CYCLE.md](NEXT_RESEARCH_CYCLE.md).

Status: 2026-10-10, source remediation before the separately registered Ridge/XGBoost comparison. This is an acceptance brief for an existing provider route, historical export or alternative source; it does not authorize a purchase, vendor contact or a change to the research protocol. See [later-period design](LATER_PERIOD_DESIGN.md) and [current evidence](R3_COMPLETION_PROGRESS.md).

The immediate requirement is a coherent historical security and action record, not additional model capacity. Current Tiingo responses recover some renamed histories but also expose reused tickers, absent historical coverage and special distributions that the legacy accounting cannot represent. A different estimator cannot repair these omissions. Ridge remains a low-cost linear control; XGBoost remains an eligible nonlinear challenger once both receive the same valid data and portfolio policy.

## Required source delivery

| Component | Acceptance requirement |
| --- | --- |
| Universe | Preserve all 793 reconstructed historical identities in the coverage denominator. Distinguish index membership from exchange listing and economic security existence. Document every unresolved interval; do not retain only currently available securities. |
| Dates | Cover registered monthly decisions from January 2010 through August 2026, with the required pre-decision feature lookbacks. The current acquisition uses 2008 onward where needed. Respect actual listing inception and terminal events; no backfilled pre-inception bars. |
| Stable identity | Provide issuer and share-class identifiers, dated symbol/exchange intervals, ticker-reuse separation and evidence for mergers, conversions, spin-offs and renames. A present-day ticker-to-name table alone fails. |
| Prices | Daily unadjusted OHLCV with exchange/calendar, currency, actual coverage, revision/retrieval timestamps and raw response hashes. Retain missing sessions explicitly. Reconcile overlaps before combining vintages. |
| Actions | Dated split ratios, cash and stock distributions, entitlement and payment dates, election/default terms where applicable, and terminal consideration. Separate publication/availability time from event time. No invented recovery, fictitious fill or spendable ex-date cash where payment occurs later. |
| Adjustments | Explain adjustment factors and reconcile them to raw bars/actions. An adjusted total-return series alone cannot establish a cash-account ledger or point-in-time action knowledge. |
| Issuer facts | Historical filing acceptance times, original/amended versions, units and accounting periods, joined through the dated class/issuer map. Missing facts may remain explicitly missing under the frozen feature policy; they must not remove securities from the scoring universe. |
| Terms and economics | Record licensed use, actual subscription/access limits, recurring fees and one-time research costs. Do not assume an old plan label proves current entitlement. Include recurring costs in the £3,000 account evaluation; disclose research costs separately and include them when funded by that capital. |

## Concrete failure cases for a source sample

A prospective route should resolve representative failures before any broad acquisition or purchase: historical Paramount Class B despite recycled PARA; a delisted security such as NYX or MDP whose metadata advertises overlap but whose requested history is empty; JNPR's 2009 exchange transfer and actual 2025 termination; WY's 2010 elective cash-and-stock distribution; and one punctuation-only alias such as BF.B/BF-B. Preserve the issuer/class and date evidence for each sample. Class A, preferred stock and a merger successor are not interchangeable substitutes.

Use existing access first. For every request, check expected identity/class and advertised date overlap before requesting prices. Cache immutable successes and failures. Do not retry an unchanged empty response, guess undocumented stable-identifier routes, or infer EOD support from a separate fundamentals endpoint. Ask the user for an existing export or a specific access/budget decision only when the available authorized routes cannot meet the required sample.

## Research decision boundary

Source remediation passes only when the dataset can account for the full native universe, with causally valid identities, coverage and action/valuation failure states, and meets the registered evaluator's evidence contract. This does not require inventing observations for truly unavailable securities. It does require preserving those failures and their portfolio consequences rather than silently deleting them.

If the full source contract remains unsatisfied, do not claim full-universe enriched readiness. Bounded conditional ranking diagnostics are authorized under the current iteration policy; report unsupported scope and unbounded biases. Never narrow to today's survivors or call missing experiments a Ridge victory. Any different universe, period or instrument scope requires an explicit separately registered research decision. A data-access blocker is also not completion of R3: qualification, paper observation and exact live authorization remain separate gates.

Once the data gate passes, freeze feature groups, shared momentum control, Ridge/XGBoost trial budget, causal preprocessing and validation selection before fitting. Compare incremental after-cost value with uncertainty; keep the inspected historical period as development evidence. The target remains more than £300 net first-year profit on £3,000, subject to all existing cash and drawdown invariants.

## Implemented R3 adjustment convention

[`r3_adjustments.py`](../src/data/r3_adjustments.py) now implements `r3-ex-date-close-total-return-v1` as a separate numerical check. For a cash-only distribution, the expected adjusted/raw factor change is `1 + D/P1`. For a split of `S` new shares per old share, it is `S`; a simultaneous distribution requires explicit pre-split or post-split share units. No units are inferred. Callers must supply the actual exchange-calendar predecessor and finite nonnegative tolerances. Identity/date mismatch, stale bars and invalid inputs fail closed.

This component is exercised on recovered source responses, but has not replaced legacy certification or been integrated into a new full-universe builder. A consistent factor does not admit a security, certify the distribution as cash, or authorize ex-date reinvestment in the account evaluator. Identity, action terms, availability and payment-time accounting remain separate requirements. Never change the original canonical artifacts or rerun old evidence under this convention while retaining its old identity.

The R3 component also exposes `adjustment_context_keys`: for each required in-scope action/price window, it selects the current and actual predecessor session from a verified calendar. Retrieve those observations from the full identity-validated bar store, separately from scoring membership. A pre-membership context bar does not create pre-membership eligibility. Missing source bars remain missing, and an absent predecessor in the calendar is an error. This rule prevents membership boundaries from manufacturing missing-action evidence; it does not cure identity discontinuities or unverified distributions.
