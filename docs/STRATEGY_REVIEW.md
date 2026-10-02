# Strategy and methodology review

Decision date: 2026-09-26. Stage: R3 research reset. This review selects a research method, not a profitable strategy.

## The actual objective

Earn more than £300 on an initial £3,000 over the first 12 months, net of trading and recurring operating costs: terminal wealth must exceed £3,300. No additional deposits count as profit. £3,000 is the sole R3 starting-capital and qualification scenario; no £1,000 launch is planned. Report one-time research expenditure separately and also show first-year wealth after that expenditure. If the user funds it from the initial capital, it reduces investable capital and the objective result.

The objective conflicts with a desire for a reliably small drawdown and very small fixed-cost budgets. There is no established probability of achieving it. A one-year deadline cannot turn existing, inspected historical data into fresh evidence, or compress the retained multi-year safety qualification requirements.

## What the two attempts actually show

| Observation | Interpretation | Required response |
| --- | --- | --- |
| V1 historical OOS CAGR -0.17%, Sharpe 0.001, drawdown 15.03% | Engineering succeeded; investment objective failed | Retain as a rejected control |
| Historical V2 £1,000: zero orders, £180 modeled fees over five years, CAGR -3.8917% | Earlier evidence of fee erosion; outside the revised capital scope | Preserve the result without requiring a new £1,000 qualification run |
| V2 £3,000: CAGR -2.9947%, 4.186% mean exposure, 49 orders, 23 completed episodes | The effective product barely invested and still lost money | Attribute eligibility, risk scaling, rounding, cash and halt effects |
| £3,000 fixed-fill gross CAGR -1.2973% | Removing modeled costs from the same fills does not repair the strategy | Do not explain every loss as brokerage expense |
| Most recorded exclusions were below $500m median daily turnover | The screen is unusually restrictive relative to £150–£900 stock allocations | Test a capacity-based liquidity policy fixed before returns are viewed |
| No viable V2 sensitivity neighbor | Another small momentum retune has weak support | Compare a bounded new model family; keep failed trials visible |
| Existing gate allows 8% CAGR | Passing that gate would not establish >10% within a year | Add the actual one-year objective; retain risk gates |

These findings come from local artifacts checked during this review; see [evidence and limitations](LEGACY_EVIDENCE.md). Exclusion counts are not unique securities or a causal decomposition. Low exposure alone does not prove why entries failed. R3 must complete the funnel audit before treating a proposed fix as effective.

## Economics before model complexity

The official [IBKR ISA overview](https://www.interactivebrokers.co.uk/en/accounts/isa-accounts.php) and [minimums schedule](https://www.interactivebrokers.co.uk/en/accounts/required-minimums.php), checked 2026-09-26, state a £3 adult ISA monthly minimum. Public pages do not establish the account's complete billing, fractional-share permissions or FX operation.

| Initial capital | Required net profit | £36 annual minimum / capital | Approximate gross hurdle with only £36 cost |
| --- | ---: | ---: | ---: |
| £3,000 | >£300 | 1.2% | >11.2% |

These are first-order arithmetic examples, not forecasts; monthly timing changes compounding. Account minimums and eligible commissions may overlap. Establish the exact offset rule; do not add £36 to commissions as if that necessarily equals billed cost. Preserve the old full-fee-plus-commission case as an explicitly conservative stress until verified.

A hypothetical £10/month data service consumes a further 4% of the £3,000 starting capital each year. This is an illustration, not a provider quote. Use incremental data, hosting and software costs; also disclose full economic cost and existing resources. No paid service or purchase is authorized by this plan. An unaffordable data requirement is a reason to stop, not omit the cost.

At 4.186% average exposure, even an illustrative 20% return on invested capital contributes only about 0.84% before costs under a crude constant-exposure approximation. This is not a reconstruction of V2 returns. It explains why improving rankings alone may have little impact unless feasible exposure also improves.

## Alternatives considered

| Approach | Decision | Reason |
| --- | --- | --- |
| Another hand-tuned momentum variant | Control only | Two failed candidates and inspected data create selection risk |
| ML gate on V2's few completed trades | Reject as starting design | Too few episodes; inherits V2's narrow opportunity set |
| Pooled cross-sectional return ranking | Research now | Can learn conditional momentum, reversal and risk interactions across eligible stock-months |
| Deep learning, reinforcement learning, intraday trading | Defer | More complexity, labels, execution dependence and cost without supporting evidence |
| Low-turnover diversified equity investment | Required opportunity-cost benchmark | Establish whether the bot adds value; it also cannot guarantee 10% in a year |
| Different broker, ETF portfolio or larger capital | Separate scope decision if economics fail | May address structural constraints, but not authorized trading changes or a way to relabel failure |

Use a broad-equity total-return reference and, if verified affordable and ISA-accessible, an investable UK retail fund reference. Do not assume SPY is a purchasable ISA instrument. Fund benchmarks are explicitly outside the stock strategy's 30% single-name constraint; they do not silently change it.

## Why ML now, and why it might still fail

[Gu, Kelly and Xiu](https://www.nber.org/papers/w25398) find useful nonlinear predictor interactions in empirical asset pricing. That supports testing ML; their results do not establish returns for a four-stock, cash-only £3,000 ISA. [Da, Nagel and Xiu](https://www.nber.org/papers/w33070) discuss statistical limits when signals are weak. Neither paper certifies this product.

Choose regularized linear regression as the first learned model and shallow gradient-boosted trees as the nonlinear challenger. Train on the entire eligible cross-section at monthly decision dates, not only trades chosen by a failed strategy. Predict next-month benchmark-relative returns, then subject every score to the same cost, sizing and safety policy. Do not train a binary “10% annual profit” classifier from a handful of annual observations.

Begin implementation in R3 after the economics/data gate; do not wait for deterministic profitability, paper trading or live results. Retain ML only if it improves after-cost objective evidence over the control. No neural networks, text feeds, alternative data, GPU service or automated hyperparameter search is needed for this experiment.

## Decision and stopping rule

Build one bounded experiment with three candidate families and a locked evaluation protocol. Stop if feasible orders/costs fail, data cannot support causal labels, every candidate fails development gates, or untouched evidence is unavailable. Publish “objective not demonstrated” rather than a third strategy advertised as working. The first implementation task is the economics and exposure audit in [R3.1](ROADMAP.md), followed immediately by data/label contracts and model training if viable.
