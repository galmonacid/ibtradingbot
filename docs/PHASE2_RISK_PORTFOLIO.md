# Phase 2 Risk and Portfolio Construction

## Purpose and boundary

Phase 2 adds deterministic portfolio construction and research risk controls to
the Phase 1 causal pipeline. It does not add ML, broker connectivity, live-order
behavior, point-in-time universe data, parameter optimization, or Phase 3
validation. Output from the synthetic fixed-universe fixture is engineering
evidence only and cannot establish investment merit or deployability.

## Selection and sizing conventions

- New positions enter only at ranks `1..N`. An incumbent that still passes all
  mandatory eligibility and trend rules remains selected through rank `2N`.
  Buffered incumbents are not displaced merely to admit a new top-N candidate;
  mandatory exclusions and portfolio risk states take priority.
- The selected set is sized from inverse annualized 20-session realized
  volatility. Before portfolio-level volatility scaling, deterministic bounded
  allocation enforces the configured 10% minimum and 30% maximum when feasible.
- Expected portfolio volatility is `sqrt(w' Cov w)`. `Cov` is the annualized
  sample covariance of the final 20 daily adjusted-close returns known at the
  signal close. Series are aligned to the configured benchmark sessions; missing,
  non-finite, asymmetric, zero-volatility, or non-positive-diagonal inputs fail
  closed and are reported.
- Volatility targeting only scales weights down. Because portfolio risk has
  priority, this final uniform scale may put a weight below the 10% pre-scaling
  floor. Unallocated exposure remains cash.
- Final targets are non-negative, contain no more than five names, retain at
  least the configured 2% cash buffer, respect the applicable regime ceiling,
  and never exceed 30% in one name.

## Drawdown controls

High-water equity is non-decreasing and drawdown is measured after each session
close as `equity / high_water_mark - 1` using only information then available.

- At 10% drawdown, the state becomes `soft`: the next requested target cannot
  increase the previously accepted target exposure and the normal position cap
  is halved.
- At 15% drawdown, the state becomes `hard`: liquidation is decided after the
  close and executes no earlier than the next available session open. The state
  remains latched for the rest of the research run and all later entries are
  blocked. This models the specification's explicit-human-review requirement;
  there is no timed automatic reset.
- State transitions are recorded as structured risk events. External alerts and
  human re-enable controls belong to later broker/execution phases.

The optional single-position 12% emergency stop remains deferred. Safely firing
it requires the market-data, corporate-action, and symbol-mapping checks stated
in `RISK_AND_EXECUTION.md`; it is not one of Phase 2's explicit roadmap items.

## Comparisons and costs

The primary scenario uses inverse-volatility targets and default costs. The
report also applies the same dated inverse-volatility requests under stress
(10 bps slippage per side, twice default commission, unchanged FX friction) and
runs a sizing-only equal-weight comparator over the same selected names. The
shared hysteresis state deliberately comes from the primary strategy so the
comparison isolates sizing rather than defining a second selection strategy. Each scenario
retains causal fills and its own cost-aware drawdown path.

The report exposes the stressed 6% CAGR and 0.6 Sharpe thresholds numerically,
but always marks the checked-in result inadmissible as deployment evidence.
Phase 3 owns the point-in-time, walk-forward, sensitivity, bootstrap, ablation,
and out-of-sample work needed to evaluate mandatory gates.
