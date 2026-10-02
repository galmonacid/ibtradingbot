# AGENTS.md

## Mission and current stage

Develop a research-first, long-only equity system intended for an IBKR UK Stocks & Shares ISA. The user-confirmed objective is **more than 10% total GBP return within one year after trading and recurring operating costs**, starting with £3,000. This is not a guarantee, a multi-year CAGR substitute or financial advice. Valid evidence and account safety take precedence over a favorable backtest.

Current roadmap: R3 research reset. V1/V2 are rejected controls. The user has authorized considering ML immediately; R3 permits offline ML research after the economics/data prerequisites, without waiting for deterministic profitability or live trading. No new model or broker implementation exists merely because the Markdown changed.

## Working agreement

- Before edits, inspect Git status, relevant code/configuration and the applicable specification. State the intended outcome and roadmap stage.
- Follow docs/ROADMAP.md in small, reviewable changes. Do not add live execution, leverage, shorting, derivatives, new asset classes or infrastructure ahead of their stage.
- Do not invent installed dependencies, runnable commands, data availability or completed work. Establish new conventions explicitly and test them.
- Prefer deterministic, typed Python with separate data, features/labels, learning, strategy, portfolio, accounting and execution responsibilities.
- Keep tunable behavior in versioned configuration. Existing YAML/CLI behavior remains legacy; use a separate R3 configuration and evaluator.
- Keep credentials, account identifiers, local datasets, generated run reports and fitted models out of Git. Preserve immutable evidence; update ignore rules for new generated paths.
- No real orders, live-account connection or external broker-state change without the user's explicit request for that exact action and completed paper/safety gates. A request to revise strategy documentation is not trading authorization.

## Research integrity

Use point-in-time membership, stable security identities, source availability timestamps and explicit exchange calendars. Signal after close t executes no earlier than t+1. Never introduce survivorship selection, future corporate-action information, future labels, fitted preprocessing leakage, backfilled returns or fabricated delisting recovery.

All inspected V1/V2 history remains development data. Keep a complete experiment register, including failed candidates. Same-date stock observations stay in one split; purge actual label overlaps and respect maturation. Fit transforms on training only. Model selection uses validation, never untouched test data. ML must demonstrate after-cost incremental value against the shared-policy control.

Evaluate the £3,000 starting account, reporting all-in one-year outcomes and loss/uncertainty evidence. The target is net profit >£300 and terminal wealth >£3,300 without additional funding. Costs include execution, FX, account charges and recurring operation; disclose research costs separately and include them when paid from starting capital. Do not claim target success from an 8% CAGR legacy gate, a synthetic fixture, a large USD account or deposits.

## Hard risk invariants

Long-only; no leverage or margin; gross <=100%; <=5 stocks; <=30% per stock; preserve the configured cash buffer and fee affordability. Keep the 10% soft control and permanent 15% account drawdown halt. The halt cannot guarantee a maximum realized loss and must never be optimized or reset to improve a backtest. Preserve state across folds/refits. Mandatory reductions bypass discretionary minimums/bands and cannot create unrelated buys.

Reconciliation and idempotency precede broker integration. Broker/local state mismatch disables trading, never automatic corrective orders. Derive portfolio state from actual fills, not submissions. Missing/stale data or model failure blocks new risk. Report unresolved held-asset valuation; never invent a fill.

## Development and verification

1. Inspect the tree, status, relevant specification and implementation.
2. Implement the narrowest coherent roadmap change, preserving legacy controls.
3. Add meaningful tests for new calculations, causal timing, model boundaries, risk and failure-state transitions.
4. Run specific checks then the broader configured suite (`pytest`, `ruff check .`, `mypy src`, and package build for implementation work).
5. Review the diff for unintended files, secrets, leakage, weakened limits and unsupported performance claims.
6. Report actual verification, unrun checks and remaining limitations. Never report historical checks as current passes.

For documentation changes verify local links, retired references and implementation/status distinctions. For experiments record Git commit/tree, config/data/universe/calendar/cost/model hashes, dependency environment, seeds and timestamp. Do not overwrite or re-sign old artifacts after specification edits.

## Review and documentation map

Flag leakage, survivorship risk, omitted costs, duplicate orders, unreconciled state, stale data, silent fallback models, weak risk controls and claims of premature deployability. Require integration tests for eventual execution flows and independent risk verification before live work.

- README.md: objective, status, supported commands and document map.
- docs/STRATEGY_REVIEW.md: diagnosis, economics and strategy choices.
- docs/QUANT_SPEC.md: proposed candidates and portfolio rules.
- docs/DATA_AND_FEATURES.md: lineage, causal features, labels and unresolved evidence.
- docs/BACKTEST_AND_VALIDATION.md: one-year target, ML comparison and all deployment gates.
- docs/RISK_AND_EXECUTION.md: hard safety and future execution behavior.
- docs/ARCHITECTURE.md: current code versus proposed additions and migration.
- docs/ROADMAP.md: ordered tasks and stop conditions.
- docs/LEGACY_EVIDENCE.md: rejected results and reproduction revision.

When implementation and specification disagree, surface the discrepancy. The documented legacy/R3 migration is intentional; do not silently apply new requirements to old certified artifacts or weaken safety to reconcile them.
