# Phase 2 Delivery Record

## Objective

Deliver Phase 2 from `docs/ROADMAP.md`: deterministic risk-aware portfolio
construction for the existing local research pipeline, including inverse-volatility
sizing, a portfolio volatility target, exposure constraints, causal drawdown circuit
breakers, rank hysteresis, and stressed transaction costs. This remains an engineering
research result, not financial advice, a return promise, or evidence of deployability.

## Roadmap phase and scope decisions

- This is Phase 2 only. Do not add ML, broker connectivity, live execution,
  point-in-time universe acquisition, walk-forward optimization, bootstrap analysis,
  or other Phase 3+ infrastructure.
- Estimate expected portfolio volatility from a trailing 20-session, annualized sample
  covariance matrix using only returns known at the signal close. Missing or invalid
  covariance inputs exclude a candidate with an explicit reason. Volatility scaling
  may reduce final weights below the 10% pre-scaling floor because the risk target has
  priority; it never increases an allocation.
- Rank hysteresis retains an otherwise eligible incumbent while rank is at most `2N`.
  Mandatory eligibility, trend, and risk exits override the buffer. Vacancies are filled
  in deterministic rank order from entry ranks at most `N`; buffered holdings are not
  displaced merely to admit a new entrant.
- Portfolio drawdown uses close-marked equity and a non-decreasing high-water mark.
  At the configured 10% soft threshold, target gross exposure cannot exceed its prior
  target and the position cap is halved. At the fixed 15% hard threshold, liquidation is
  scheduled for the next available session and the risk-review state remains latched for
  the rest of the research run. The conflicting `hard_stop_new_entries_days` automatic
  reset is not used because the risk specification requires explicit human re-enable.
- A risk event in the research report is the Phase 2 observable alert. External alerting
  and human re-enable workflows belong with later execution phases.
- The default-cost, stressed-cost, and equal-weight comparisons reuse the primary run's
  dated target requests. Their applied risk overlays are reported because cost-dependent
  account marks can cause paths to diverge. Stress means
  10 bps slippage per side, twice the configured commission, and unchanged FX friction.
- The checked-in fixture is synthetic and uses a fixed present-day universe. Phase 2 can
  calculate provisional gate metrics but cannot honestly demonstrate Phase 3 mandatory
  out-of-sample deployment gates. Gate status must therefore be reported as inadmissible
  for deployment evidence even if a numeric threshold happens to pass.
- The optional -12% single-name emergency stop is deferred: Phase 2's roadmap explicitly
  calls for portfolio drawdown circuit breakers, while safe single-name triggering first
  requires the corporate-action/data-validation workflow described in the risk spec.

## Measurable acceptance criteria

- [x] Inverse-volatility construction is deterministic; lower-volatility candidates get
  weakly higher unconstrained weight; zero, missing, and non-finite volatility fail closed;
  and pre-scaling weights obey the configured 10%/30% bounds when feasible.
- [x] A causal trailing covariance estimate scales allocations only downward so expected
  annualized portfolio volatility is at most 12%; residual capital remains cash and all
  calculations are prefix/future invariant.
- [x] Every final target is long-only, has at most five positions, no position above 30%,
  gross exposure no greater than the applicable regime ceiling or 98% cash-buffer ceiling,
  and risk-off exposure is zero. Invalid targets fail before portfolio mutation.
- [x] Stateful rank hysteresis enters only ranks `<=N`, retains eligible incumbents through
  rank `2N`, exits ranks `>2N`, allows mandatory trend/eligibility/risk exits, and produces
  turnover no greater than an unbuffered control on the exercised fixture.
- [x] Close-marked high-water mark and drawdown state are causal. Boundary tests prove the
  10% soft state prevents exposure increases and halves the position cap; the 15% hard
  state liquidates no earlier than the next session and permanently blocks later entries.
  Transitions are deterministic and visible in the report.
- [x] The Phase 2 report compares inverse-volatility and equal-weight construction on the
  same signals and reports default and stressed costs. Stress uses exactly 2x commission,
  10 bps slippage, unchanged FX friction, and cannot improve net equity solely through the
  cost model. It reports the stressed CAGR/Sharpe thresholds without claiming deployment.
- [x] Weekly scheduled trades and emergency risk trades preserve after-close signal timing
  and next-available-session execution, including holiday gaps and missing-open fail-closed
  behavior. Existing delisting and accounting guarantees remain intact.
- [x] Configuration exposes and validates every Phase 2 tuning input, preserves fixed hard
  risk limits, keeps ML disabled, and removes or clearly deprecates contradictory automatic
  hard-stop reset behavior.
- [x] With a fixed timestamp, the full JSON report is byte-deterministic and includes Phase
  2 strategy provenance, sizing/risk decisions, exclusions, risk events, comparison metrics,
  costs, trades, equity, and explicit fixed-universe/synthetic limitations.
- [x] Supported Python 3.12 install, full pytest, Ruff, strict mypy, package build, installed
  console commands, and direct CLI behavioral inspection all pass. Independent reviews find
  no remaining material correctness, leakage, accounting, or risk-invariant issue.

## Task backlog

- [x] Inspect repository, Git status, roadmap, relevant specifications, architecture, config,
  current portfolio/backtest pipeline, tests, and available verification environment.
- [x] Define Phase 2 scope conventions and measurable acceptance criteria.
- [x] Add typed Phase 2 configuration accessors and validation.
- [x] Implement and unit-test stateful rank-buffer selection.
- [x] Implement and unit-test constrained inverse-volatility and equal-weight portfolio
  construction with causal covariance-based volatility targeting.
- [x] Extend the backtest with causal target-policy/risk-state support, soft/hard drawdown
  transitions, next-session liquidation, latch behavior, and risk event reporting.
- [x] Integrate Phase 2 construction and risk decisions into the research pipeline.
- [x] Add equal-weight and stressed-cost comparison runs plus provisional gate reporting.
- [x] Add property, boundary, leakage, timing, regression, and end-to-end tests.
- [x] Update README and Phase 2 documentation; preserve Phase 1 command compatibility.
- [x] Run focused and full verification, inspect actual CLI output, and repair findings.
- [x] Complete independent reviews, fix all material findings, and reassess every criterion.

## Completed work

- 2026-09-09: Inspected the Phase 1 baseline and all Phase 2-related specifications.
- 2026-09-09: Independent specification, implementation, and test/tooling audits launched.
- 2026-09-09: Identified the need for a causal target-policy interface because drawdown
  decisions cannot be safely precomputed before the backtest knows portfolio equity.
- 2026-09-09: Added canonical Phase 2 config validation, stateful rank-buffer selection,
  causal covariance estimation, bounded inverse-volatility sizing, scale-only-down
  volatility targeting, and explicit construction exclusions.
- 2026-09-09: Extended the event-driven engine with close-marked high-water/drawdown state,
  inclusive soft/hard boundaries, permanent hard latch, next-session liquidation, applied
  target audit records, and next-session concentration/soft risk reductions.
- 2026-09-09: Integrated the primary inverse-volatility scenario, sizing-only equal-weight
  comparison, canonical stressed-cost scenario, risk audit trail, and explicitly
  inadmissible preliminary gate assessment into the deterministic JSON report.
- 2026-09-09: Three independent review streams examined requirements/leakage, accounting and
  risk behavior, and test/acceptance coverage. Material findings were fixed, including
  candidate-level covariance isolation, exact threshold enforcement, comparator coupling,
  lost scheduled exits, soft-control timing, concentration drift, and full-book micro-trades.

## Discovered work and decisions

- The repository's local `.venv` is Python 3.9.6 and has no development dependencies.
  Verification therefore used the bundled Python 3.12.14 runtime and a temporary isolated
  environment containing only the project's declared dependencies.
- `GOAL.md` contains pre-existing user changes from Phase 1 and must remain untouched.
- Enforcing the 30% hard concentration invariant after price drift requires a causal
  next-session trim. Risk-reduction execution retains unaffected shares and never buys,
  avoiding the initial implementation's repeated full-book micro-rebalances.
- Scheduled strategy targets supersede a same-session pending concentration trim and still
  receive active drawdown limits, so risk-off and mandatory exits cannot be silently lost.
- The equal-weight arm intentionally shares the primary selector's hysteresis state and
  selected names; it is a sizing-only comparison, not a second independently selected strategy.
- Stressed costs reuse the same dated strategy requests, but costs can alter marks and risk
  overlays slightly. Each comparison therefore exposes its applied targets, risk transitions,
  and final state rather than claiming identical realized paths.

## Evidence

- Final Python 3.12.14 gate on 2026-09-09: 99 tests passed; `ruff check .`, strict
  `mypy src`, `git diff --check`, and `python -m build --no-isolation` all passed.
- The final build produced `momentum_ml_bot-0.2.0.tar.gz` and a universal wheel. The wheel
  installed into the verification environment; both packaged console commands ran.
- The research CLI ran twice with a fixed timestamp and produced byte-identical JSON. The
  inspected fixture contained 380 sessions, 79 weekly signals, 67 executed sides, 83 applied
  targets, and four targeted concentration-reduction sells with no unrelated risk buys.
- Maximum reported expected portfolio volatility was 0.004826, below the configured 0.12
  ceiling. Default costs were $394.20; canonical stressed costs were $602.46, and stressed
  final equity ($100,420.33) was below the primary result ($100,628.80) on this fixture.
- Boundary tests cover just above and exactly at 10%/15%, a soft breach without a scheduled
  signal, permanent hard latching, next-session liquidation across a calendar gap, scheduled
  target/risk-reduction collision, concentration drift, no unrelated risk trades, prefix
  invariance, and deterministic repeated reports.
- Independent rereviews confirmed causal covariance and next-session timing and verified the
  fixes for all initially material findings. The synthetic fixed-universe result remains
  explicitly inadmissible as a return claim or deployment-gate result.

## Blockers

- None at present.
