# Phase 1 Delivery Record

## Objective

Deliver the deterministic research baseline in `docs/ROADMAP.md`: a local,
reproducible, long-only research pipeline from validated daily prices through a
costed, delayed-execution backtest and benchmark-relative report. The result is
an engineering baseline only; it is not financial advice, a performance claim,
or evidence that the strategy is ready for deployment.

## Scope decisions

- Implement every feature marked required in `docs/DATA_AND_FEATURES.md`.
- Use equal weights only. Inverse-volatility sizing, volatility targeting, rank
  hysteresis, drawdown controls, stress costs, walk-forward and bootstrap
  analysis, and ML remain later-phase work.
- Evaluate regime rules in order: risk-on, then risk-off, otherwise neutral.
  The volatility percentile uses prior observations only; insufficient history
  is neutral. The last available session of a week is its signal session and
  orders execute at the next available session's adjusted open.
- Preserve hard invariants now: long-only, no more than five positions, at most
  30% per name, and gross exposure no greater than either the regime ceiling or
  one minus the cash buffer. Research values are USD; FX bps is a modeled
  per-side friction rather than an exchange-rate model.
- Use explicit, versioned fixed-universe metadata only for engineering
  validation. It cannot substantiate historical performance claims.
- Use adjusted research prices to handle ordinary corporate actions. A held
  symbol that disappears fails closed unless an explicit, versioned delisting
  event supplies cash recovery; no stale price is fabricated.

## Measurable acceptance criteria

- [ ] Ingestion validates canonical daily bars, returns typed deterministic
  records, and quarantines invalid rows with explicit quality reasons, including
  duplicates, OHLCV errors, suspicious moves, stale prices, and split-like jumps.
- [ ] A versioned 30–50-name fixed universe plus SPY has explicit eligibility
  metadata; as-of filters enforce price, trailing liquidity, history, and
  instrument rules and record every exclusion.
- [ ] Feature construction implements all required stock, benchmark, breadth,
  and dispersion fields causally, using adjusted prices and no forward-filling.
- [ ] Ranking applies 1st/99th percentile winsorization, population z-scores,
  the exact configured formula, strict price-above-SMA200 eligibility, explicit
  missing-input exclusions, and symbol tie-breaking.
- [ ] Regime classification implements explicit boundaries and a prior-only
  expanding volatility percentile without future information.
- [ ] Equal-weight targets preserve all hard risk invariants, retain the cash
  buffer, and produce zero exposure in risk-off.
- [ ] The engine produces weekly after-close signals, executes strictly at the
  next available session's adjusted open, supports cash and fractional shares,
  sells before buys, handles disappearing holdings explicitly, and exposes a
  deterministic ledger and daily net equity series.
- [ ] Commission, adverse slippage, and FX friction are configurable, charged
  on each executed side, separately reported, and absent on no-change targets.
- [ ] Reports include all required metrics, aligned SPY/cash comparisons,
  benchmark-relative measures, deterministic null semantics, and provenance.
- [ ] Tests prove formulas, boundaries, risk properties, cost accounting,
  next-session timing including holiday gaps, deterministic ties, invalid-input
  behavior, and prefix/future invariance for signals and targets.
- [ ] One documented local command runs a version-controlled long fixture twice
  with identical economic results and no network, broker, or live-order action.
- [ ] Python 3.12 passes install, pytest, ruff, mypy, build, the Phase 0 command,
  and the Phase 1 command; independent review has no material open finding.

## Backlog

- [x] Inspect repository, Git state, configuration, roadmap, and relevant specifications.
- [x] Define scope decisions and measurable acceptance criteria.
- [x] Extend configuration and add versioned fixed-universe metadata.
- [x] Implement ingestion, quarantine reporting, and as-of universe filtering.
- [x] Implement required features, ranking, trend eligibility, and regime model.
- [x] Implement equal-weight targets and hard-invariant checks.
- [x] Implement costed delayed execution and portfolio accounting.
- [x] Implement metrics, comparisons, provenance, report, and Phase 1 CLI.
- [x] Add a long fixture and unit/property/leakage/regression/end-to-end tests.
- [x] Update documentation and CI; run all quality and behavior gates.
- [ ] Complete independent reviews, fix material findings, and reassess scope.

## Completed work

- Repository and specification inspection completed on 2026-09-07.
- Three independent audits covered Phase 1 scope, repository readiness, and
  leakage/risk/test requirements. Their findings are reflected above.
- The first implementation pass delivered separate data, feature, strategy,
  portfolio, backtest, metrics, research orchestration, and CLI modules.
- Behavioral inspection found and fixed cost-induced cash-buffer erosion,
  ineligible-symbol breadth contamination, and a truncated-week scheduling bug.

## Discovered work / decisions

- The current two-session fixture cannot exercise 252-day features; a separate
  deterministic fixture with at least 258 sessions is required.
- Existing inputs do not carry security metadata; Phase 1 must add a versioned
  universe input rather than infer ISA or listing eligibility from prices.
- A varying run timestamp prevents whole-report byte identity. Economic payloads
  will be compared separately, and tests can inject a fixed timestamp.

## Evidence

- On Python 3.12.14, the first integrated gate passed 39 tests, `ruff check .`,
  and strict `mypy src` on 2026-09-07.
- A direct full-fixture run ingested 2,280 bars over 380 sessions with zero
  quarantines, produced 79 completed-week signals and 66 executed order sides,
  exercised risk-on/neutral/risk-off, and produced all metrics and provenance.
- The Memorial Day regression proves a 2024-05-24 close signal executes on the
  next observed session, 2024-05-28. Every trade is strictly after its signal.
- The integrated regression runs the pipeline twice with a fixed timestamp and
  compares the complete reports for equality.

## Blockers

- None.
