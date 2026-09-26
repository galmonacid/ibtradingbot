# Phase 3 V2 delivery record

## Objective and scope

Implement the `monthly-momentum-v2` research candidate in `docs/QUANT_SPEC.md`,
preserve V1 as a control, and deliver reproducible development evidence and a
fail-closed qualification boundary. Remain in Phase 3. No broker connections,
orders, ML, leverage, new subscriptions, or relaxed deployment gates.

Started 2026-09-22. The repository already contains extensive uncommitted Phase 3
work; it is input to this delivery and must not be reverted. Tasks use disjoint new
files in the shared checkout rather than worktrees that omit those changes.

## Measurable acceptance criteria

1. V1 reports are preserved and their recorded hashes verified; the native V1
   command is rerun as a control with differences explained.
2. An explicit typed V2 config and supported command implement exact t-21/t-252
   momentum, 253 consecutive sessions, PIT eligibility, deterministic ties,
   monthly calendar scheduling, actual-fill incumbents and weekly SPY regime.
3. Equal-weight dual-covariance sizing, daily downward-only controls, unchanged
   10%/15% drawdown controls, permanent hard halt, and band/economic-minimum
   precedence are covered by behavior and edge-case tests.
4. Causal raw-share execution includes actions, fees, delay, conservative rounding,
   GBP/USD cash and timestamped FX, post-cost cash/caps, and £1,000/£3,000 scenarios.
   Missing FX source/licence or tariff/capability evidence blocks qualification.
5. Native input/config/spec/source/calendar/cost/FX identities bind deterministic
   decisions, orders, fills and reports. Development cannot claim unseen OOS or
   permit paper trading. Existing V1 validators remain intact.
6. Development reports include V1/fixed V2/single-change diagnostics, all 16 fixed
   sensitivity neighbors, baseline/stressed/delayed results, attribution, lots and
   independent episodes, annual/stock/bootstrap evidence and benchmark references.
   Unexecutable variants are explicit failures, never fabricated returns.
7. A freeze protocol enforces unseen dates, one continuous account per scenario,
   >=756 sessions, >=150 closed lots and >=150 complete position episodes, and
   the first qualifying calendar-year-end endpoint. Mandatory gates are unchanged.
8. Specific tests, full pytest, Ruff, strict mypy, sdist/wheel and installed CLI
   behavior pass. Independent review material findings are fixed and rechecked.
9. Final status distinguishes implemented infrastructure, development outcome,
   qualification evidence and external blockers. No passing performance is promised.

## Development plan / task backlog

- [x] P0 inspect specs, environment, prior evidence; baseline verification.
- [x] P1 typed V2 config, signals, selection, calendar and weekly regime (agent v2_strategy).
- [x] P1 pure portfolio covariance, reductions, bands and drawdown (agent v2_risk).
- [x] P1 freeze/qualification, sensitivity and episode primitives (agent v2_protocol).
- [x] P2 causal execution/accounting, native integration, FX input boundary, tests.
- [x] P3 reporting, diagnostic experiments, CLI and provenance/audit integration.
- [x] P4 independent review, fix findings, full checks, actual CLI runs and packaging.
- [x] P5 reassess every criterion; record development rejection and qualification blockers.

After each phase: targeted then full verification, inspect actual output, independent
review, fix material findings and add discovered work here.

## Completed work / evidence

- Read AGENTS.md, roadmap, V2 spec, architecture, validation requirements, current
  native input/strategy/workflow and execution interfaces; inspected working tree.
- System `/usr/bin/git` fails because Xcode licence is not accepted. Working fallback:
  `/Users/guillermo/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/git`.
- Existing Python 3.12 tool environment: `/private/tmp/phase3-venv/bin/`.
- Three bounded independent implementation tasks dispatched with disjoint ownership.

## Discovered work and limitations

- V1's precomputed target pipeline cannot provide V2 selection from actual fills;
  V2 needs a sequential decision/execution loop, preserving the V1 path.
- The spec explicitly says historical GBP/USD inputs are absent. Inspect local
  data before choosing a source; record licence before acquisition. Synthetic FX
  may test accounting but cannot supply real account-feasibility evidence.
- Previously inspected history is development only. A default untouched test starts
  after a real freeze and needs at least 756 future sessions; none exists today.
- Current baseline native reporting defaults to $100,000 and uses adjusted-share
  accounting; it does not establish small-account feasibility.

## Blockers

No implementation blocker established yet. Qualification requires external evidence
not currently present (unseen history, timestamped licensed FX, applicable pinned
tariff and instrument/account fractional capability). Continue independent work;
never relabel missing qualification evidence as a pass.

## 2026-09-23 continuation evidence and review log

Previous goal turn classification: progress (new implementation/modules and targeted
verification), interrupted before integration completion. Current authoritative state
was reinspected; this is not a completed goal.

- P0 baseline: full original suite passed **277 tests in 35.92s**. Preserved V1
  Markdown/JSON match the specification's SHA-256 values. Completed native rerun
  at `data/local/phase3_v2/v1_anchor.{json,md}` differs from preserved report **only
  in provenance**; every other report section is exactly equal.
- P1 modules implemented: strict V2 config, signal/calendar/actual-fill selection,
  dual covariance/downward-only controls, fixed sensitivity and freeze guards,
  independent episodes and report attribution. Targeted tests existed and passed;
  integration/independent review remains open.
- P2 raw-share executor and sequential engine implemented provisionally. FX factory
  rejects future/stale inputs and binds source/licence/hash. Unpaid dividend claims
  remain non-spendable receivables. Existing canonical data lacks payment dates and
  full dated common-stock/US-primary metadata; these are explicit evidence gaps.
- ECB official archive acquired via authorized network escalation after sandbox DNS
  failure; source/licence recorded first in `docs/PHASE3_V2_INPUTS.md`. Normalized
  ignored FX CSV has 1,288 rows (2021-06-21..2026-06-30). It is a retrospective archive,
  not certified original-release vintages; availability is conservatively modeled.
- Independent review fixes: protocol anchor must actually complete a calendar week;
  duplicated/overlapping episodes rejected; risk-only execution now clamps share
  targets so overnight moves cannot create buys; pending risk plans retain their
  execution deadline instead of repeated delay starvation; report side labels accept
  actual lowercase fills. Partial mandatory exits with invalid covariance are
  permitted only downward and evidence remains invalid.
- Latest focused command: pytest six V2/FX modules, **50 passed in 0.24s**.
- Engine mypy initially found a reused local variable with inconsistent type, fixed.
  Full lint/type/build verification still pending after active integration work.

### Additional tasks

- [x] Integrate native V2 command, source/FX/config/spec identities and exact ledgers.
- [x] Run real whole-share £1,000/£3,000 baseline, stressed, delay and all 16 neighbors.
- [x] Verify pending risk-plan escalation semantics and whole-portfolio post-fill risk.
- [x] Complete requested five single-change V1 diagnostics and benchmark references;
      report genuine incompatibilities explicitly, not fabricated results.
- [x] Close independent integration review, rerun full checks, build/install CLI,
      compare fixed-provenance reports byte-for-byte and update public docs.

External qualification gaps do not prevent remaining implementation work. No freeze,
fresh-test result or permission to paper trade has been issued.

## Latest integration checkpoint

- Previous continuation classified as progress: V2 native CLI and content-bound scenario
  workflow added; initial real smoke run exposed an FX holiday/availability issue.
- Full suite after integration tests: **338 passed in 36.91s**. Subsequent benchmark tests
  add two passing causal/account-halt reference checks. Ruff passes and strict mypy passes
  all **82 source files** after formatting/type fixes.
- sdist and wheel build passed with `python -m build --no-isolation`.
- Registered `momentum-v2-validation` entry point; module CLI executed against real data.
- FX age is now typed/bound configuration (safe default four days). Development YAML
  explicitly permits six days for ECB TARGET closures plus next-day modeled publication;
  retrospective reference rates still cannot qualify executable FX or historical vintages.
- Real baseline artifacts: `data/local/phase3_v2/development_smoke_v2/`. £1,000: zero
  executed orders, CAGR -3.8917%, 18% drawdown from full modeled monthly fees; £3,000:
  53 orders, 30 FIFO closures, 23 episodes, CAGR -3.0106%, 15.5163% drawdown. Both remain
  unqualified; six unpaid-dividend evidence issues in the £3,000 ledger. Do not tune
  the fixed strategy or safety thresholds based on these observations.
- Full experiment currently executing as tool process session **16652**, output intended
  for `data/local/phase3_v2/development_full`. Revalidate this exact handle before restarting.
- Agent credit errors interrupted new diagnostic/reference implementation. Their files
  were recovered and inspected locally; broader independent final review remains owed.
  Full workflow now integrates these helpers and unchanged mandatory numerical gate
  comparisons, always with development evidence inadmissible.
- New implementation guide: `docs/PHASE3_V2_IMPLEMENTATION.md`. This is an in-progress
  record, not a completion claim or a strategy freeze.

- Installed wheel smoke environment `/private/tmp/phase3-v2-wheel-smoke` now has its
  declared PyYAML/PyArrow dependencies; `momentum-v2-validation --help` passes from
  `/private/tmp` outside the source checkout. Initial missing-PyYAML environment error
  was resolved by installing declared dependencies, not changing application imports.
- Broad verification rerun: **344 passed, 1 failed** because the V2 template-config test
  still expected the four-day class default instead of the explicit six-day development
  setting. Updated that expectation; all seven strategy tests then passed. Full suite
  must be rerun after remaining source changes. The first chained lint invocation did
  not run because its temporary PATH assignment applied only to pytest; reran tools
  through their absolute installed paths.

- Verified wheel archive contains all 82 current Python source files byte-for-byte
  (no different source files). Wheel SHA-256:
  `6e48e8306ec4b3453136d297d411769a048594e7d12e76a1bf6ec94882501b61`.
- `git diff --check` passed. No secrets/data artifacts were added to tracked paths.
- Real source-vs-installed-wheel baseline determinism check currently executing as
  tool process **17701** via `/private/tmp/verify_phase3_v2_wheel.py`; it runs source
  and installed commands sequentially with identical provenance and compares every
  report/ledger byte. Revalidate exact process handle before rerunning.

### Post-run review items discovered locally

- [ ] Execution trace should explicitly record a buy that rounds to zero whole shares;
      currently a zero delta silently skips before producing a skip reason. Actual
      holdings remain correct, but the exclusion audit is incomplete.
- [ ] Distinguish canonical delisting cash dispositions from submitted/executed orders
      and discretionary turnover in attribution; current fill totals include both.
      Preserve those dispositions in lot/episode accounting.

Keep the currently running immutable-code experiments intact, then fix these trace/report
findings and regenerate affected evidence. They are not reasons to claim completion now.

- Latest full suite: **345 passed in 39.43s**. Added executor-boundary regression after
  that run: all **15 executor tests pass**, including rejection of a caller-supplied
  minimum order below £150.
- Process 17701 completed successfully: real source and independently installed wheel
  runs produced **four byte-identical files** (JSON, Markdown, two exact baseline ledgers).
  JSON SHA-256 `af709e025240c9cddf7c8acd1c37988bd824e2560ff0ca561999d85bb30f64fb`;
  Markdown `d5d26a970982c58b110f215d93be2722ce2bb5175302096c3c5246ea1f3c42f7`.
  These are baseline-only and precede the pending trace/report fixes; do not treat
  determinism of this subset as completion of the full experiment.
- Process 16652 was polled and remained live at 2026-09-23 20:02 UTC. Do not restart
  it merely because no intermediate output appears; the current workflow writes
  reports after completing the entire experiment.

- Fixed both post-run trace findings in current source: explicit `rounded_below_one_share`
  skip; delisting dispositions no longer inflate order counts or traded turnover (lots
  and episodes retained). Focused executor/report/engine suite **27 passed**; added
  dedicated corporate-disposition regression subsequently **3 report tests passed**.
- The still-running full experiment uses modules already imported before these changes.
  Preserve it as pre-fix evidence, not current-source evidence. Its matching wheel is
  preserved at ignored `data/local/phase3_v2/pre_trace_review.whl`. Full current-source
  rerun and wheel rebuild will be required; do not overwrite the old run implicitly.

- Reduced redundant computation without changing any requirement: bootstrap remains
  >=2,000 paths for each capital's baseline, stressed-cost and delayed runs; the 16
  sensitivity neighbors use their specified point-metric viability tests and reference
  ledgers use comparison metrics. These rows explicitly say `not_requested` for
  bootstrap, never PASS. Scope is bound in provenance. Required baseline bootstrap
  gates remain unchanged. Report/workflow tests **6 passed**, Ruff and mypy passed.

### Resume checklist (current)

1. Poll process 16652 (pre-fix full run) until terminal; do not restart on a quiet timeout.
   `/bin/ps` is sandbox-denied, but the process tool handle has repeatedly confirmed live.
2. Inspect complete diagnostics/references and all 38 scenario statuses. Preserve old
   output and matching `pre_trace_review.whl` as pre-fix evidence.
3. Rerun complete experiment into a new directory with current trace/bootstrap-scope fixes.
4. Add a content-derived execution-ledger audit (reconcile actual fills, actions, conversions,
   fees, holdings, NAV and next-session decisions) before claiming native V2 certification;
   current workflow binds hashes but does not yet issue an independently reconciled V2 audit.
5. Close remaining single-change diagnostic semantic review (new long covariance must
   preserve or explicitly disclose V1 allocation-floor treatment) and final independent review.
6. Rebuild wheel after current-source changes and repeat full tests/package/determinism.
7. Expand human-readable report to include mandatory gates, costs, sensitivity/diagnostic
   failure reasons and benchmark tables already available in JSON; update README/version scope.
8. Reassess criteria against actual evidence; candidate failure/input gaps block qualification.

P1 is complete. P2/P3/P4/P5 remain open. No task should infer completion from the green
subset checks or from the earlier baseline-only deterministic report.

## 2026-09-24 current continuation (supersedes prior resume checklist)

- Pre-fix full process 16652 **completed**. All 38 account scenarios executed in
  `data/local/phase3_v2/development_full`; neither capital had any viable fixed
  sensitivity neighbor. Six V1 controls executed. £1,000 benchmark fee failure
  incorrectly suppressed its other references; references now fail independently.
- Added canonical-input ledger reconciliation for raw shares, actions, conversions,
  fees, daily NAV, permanent halt, FIFO populations and independent episodes.
  Independent review found unbound initial USD capital and decision reason/amendment
  fields; both fixed, with adversarial mutations. **12 audit tests pass**.
- Fixed pending safety-plan starvation and escalation from soft reduction to hard
  halt while delayed: preserve original deadline and record later amendment knowledge.
- Human report now includes costs, gates in both currencies, controls, benchmarks,
  bootstrap, annual and stock attribution. README/spec/roadmap describe implemented
  development scope without changing strategy thresholds.
- Current full rerun process 87467 was intentionally interrupted (terminal exit130)
  after review discovered stale monthly buys under missing intermediate SPY data
  and a currency robustness assembly lookup error. It produced no current report;
  do not poll/reuse it. Engine/reference agents are fixing stale pending buys.
- Fixed robustness lookup to use each currency; new real account/audit/report workflow
  integration test exercises both currency gate paths. **4 workflow tests pass**.
- Full pytest without fallback Git PATH: **356 passed, 6 failed** solely on Apple's
  unaccepted Xcode licence when spawning system git. Repeat with documented fallback;
  this command is not a passing full check. No system licence change attempted.
- Remaining identical-cost comparison gap: six V1 controls share USD100k/native
  costs but fixed V2 has only small-account tariff runs. Agent v2_protocol implementing
  explicit USD unit-numeraire V2 attribution control; synthetic FX adapter must be
  labeled diagnostic only, never historical GBP feasibility.

Current next steps: finish/review those fixes, full checks with fallback Git, restart
complete audited CLI into a fresh directory, inspect output/audit statuses, rebuild
package and repeat installed/source determinism, update final criterion matrix.
P2/P3/P4/P5 remain open. No qualification or Phase4 permission.

## 2026-09-26 final verification cycle

Previous goal turn classification: **progress**. It changed authoritative strategy,
execution, audit, report and test state and produced an audited complete experiment.

- Independent reviews closed delayed-order safety defects: missing SPY/risk inputs now
  cancel pending discretionary entries while retaining reductions; monthly exit intent
  merges with same-close cap/volatility reductions without buying; soft reductions can
  escalate to a permanent hard halt without moving their original deadline.
- Mandatory liquidation now processes positive-net-proceeds sales before fee-deficit
  dust sales, eliminating identity-sort dependence without allowing transient borrowing.
  Cash references ignore irrelevant corrupt SPY prices. Regressions cover every finding.
- Independent content audit now binds initial GBP/USD capital, original and amended
  decision provenance, actions, fills, conversions, fees, holdings, daily NAV, permanent
  halt, FIFO lot rows and position-episode rows. Adversarial mutations fail it.
- The matched $100,000 diagnostic now includes fixed V2 on exactly the V1 date/cost basis,
  retaining the V2 actual-fill/raw-whole-share engine and disclosing the unit-numeraire
  adapter and engine differences. It cannot substitute for GBP feasibility.
- Report robustness is assessed separately in GBP and USD. Gross performance is a
  fixed-fill/idle-refund diagnostic, not reoptimized zero-cost trading. Partial FIFO P&L
  cannot allocate all account cash flows, so year/stock concentration gates correctly
  remain unassessable. Exact exclusion rows remain in hashed ledgers; reports publish
  compact counts by reason. Independent review found and fixed a Markdown table break.
- Final verification environment: `/private/tmp/phase3-v2-verify`. Full suite **375 passed
  in 40.54s**; Ruff passed; strict mypy passed all **83 source files**; sdist and wheel
  built. Wheel SHA-256 `872f0cf1b4b59507a8b1600e6b8d6a4f604901051b1c8274a7b873da58d8b8be`;
  sdist `dd7d8668bf938b1b7f0c9a8edeeeeacaa9698e4095102de31e06cc1878af6028`.
  All 83 wheel Python sources exactly match the current source tree. The installed wheel
  CLI starts successfully outside the repository.
- Complete compact final matrix process **17892** exited successfully. Final artifact:
  `data/local/phase3_v2/audited_full_final_v2/`. JSON is 737,750 bytes, SHA-256
  `eff58a1d823f5814cb546f3898eddf625ff7000c079c013213db8bc6f13b6db1`;
  Markdown SHA-256 `15c51fe7edf9ee412588f3833217cff2cf4d4be9f8610740d6a223b154cf4737`.
  All **38/38 scenarios executed and passed independent ledger audit**. There are 43
  exact ledgers (38 scenarios plus five executable references); £1,000 SPY buy-and-hold
  is explicitly unexecutable because GBP cash cannot fund the full modeled fee tail.
- Final baseline: £1,000 CAGR -3.8917%, Sharpe -3.5510, drawdown 18.00%, zero orders/lots/
  episodes, hard halt 2025-08-29. £3,000 CAGR -2.9947%, Sharpe -0.8198, drawdown 15.4473%,
  49 orders, 26 FIFO closures, 23 episodes, hard halt 2026-02-27. Neither capital/currency
  has one viable sensitivity neighbor; 13/16 plus every-axis robustness fails. Both
  development gate assessments deny paper trading. The £3,000 ledger also remains invalid
  qualification evidence because canonical dividend payment dates are unavailable.
- All seven matched USD controls executed, including fixed V2. Fixed V2 CAGR -1.6876%;
  the diagnostic remains inadmissible. The five requested single-change runs and original
  V1 are retained without changing the V1 engine's default behavior.
- Source process **50227** and isolated installed-wheel process **93601** exited successfully.
  Every byte of their four baseline artifacts matches. Compact JSON SHA-256
  `8f5d229b38eda356ccfffd88d935d140137a621961e58eaa989b631cc8cd1780`;
  Markdown `3bf9aa20a52106832224c023c3c89aa44e8488e27981c3de873e324054e7bbcf`;
  baseline ledgers `2b3b894d731b4bebbcc7e8ee0657530a956b31ccf0cff384b7a83b6d70a51232`
  (£1,000) and `58050022095740a032031d11fae140939bc30469d0be8eb75afcc84c4d9d95fd`
  (£3,000).
- Recomputed the report's internal content digest and every scenario/reference ledger
  binding from the files on disk: the report binding and all **43 ledger bindings** match.
  `git diff --check`, Ruff and strict mypy were repeated after documentation closure.

### Acceptance audit

1. **Satisfied:** preserved V1 hashes were verified and the native V1 control rerun differs
   only in provenance. V1 remains available and is included in matched diagnostics.
2. **Satisfied:** strict typed V2 config, exact endpoints/warm-up, PIT membership,
   deterministic ties, calendar scheduling, filled incumbents and weekly SPY state are
   implemented and covered by unit/integration tests.
3. **Satisfied:** equal-weight dual covariance, downward-only daily controls, 10%/15%
   drawdowns, permanent halt, bands and economic-minimum precedence have adversarial tests.
4. **Satisfied for development:** raw-share causal execution, actions, costs, rounding,
   GBP/USD cash and causal FX run at both capital levels. Missing account/vintage evidence
   remains an explicit qualification blocker rather than fabricated support.
5. **Satisfied:** native input/config/spec/source/calendar/cost/FX identities bind reports,
   decisions and ledgers. Audit mutations fail; development and CLI always deny paper trading.
6. **Satisfied:** all 16 neighbors, three core scenarios, matched V1/V2 controls, no-band
   case, references, costs, gross/net metrics, attribution, lots, episodes, annual and
   >=2,000-path bootstrap evidence are published. The one infeasible reference is explicit.
7. **Satisfied:** immutable freeze/fresh-window guards require >freeze dates, a continuous
   756-session account, 150 lots, 150 episodes and the first qualifying year-end. Since the
   candidate failed development, it is rejected; no freeze or historical relabeling occurred.
8. **Satisfied:** 375 tests, Ruff, strict mypy, sdist/wheel, installed CLI, exact wheel-source
   comparison and byte-identical source/installed runs passed. Three independent reviewers'
   material findings were fixed and rechecked.
9. **Satisfied:** README, roadmap, implementation/input documentation and this record separate
   engineering completion, failed development results, absent qualification and external gaps.

## Final delivery decision

The Phase 3 V2 engineering goal is complete. The fixed strategy is **rejected for
qualification** on development evidence; Phase 4 and all broker execution remain blocked.
No implementation blocker remains. A future strategy version would be a new, predeclared
research objective. This V2 may only be reconsidered after a real freeze and at least 756
fresh sessions plus the documented evidence, lot, episode and mandatory performance gates.
