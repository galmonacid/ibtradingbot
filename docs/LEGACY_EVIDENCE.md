# Legacy evidence and reproduction register

Reviewed 2026-09-26. This is a factual record of rejected strategies, not an active implementation plan. Historical documents are recoverable from Git commit `090108c4352f41ce2c87a3d4cf6b806e1aa3f9af` (Implement Phase 3 V2 research validation). The working tree was clean before this documentation reset.

The current R3 plan uses initial capital of £3,000 only. £1,000 figures below describe completed historical experiments; they are not current targets or qualification requirements.

## Preserved local evidence

| Candidate | Artifact | SHA-256 checked during reset |
| --- | --- | --- |
| V1 | `data/local/phase3_build_v3/research_report.json` | `19dbd834da6264650a58120255d649c2575d137a7fa992a4f84a84c0f15c7fdb` |
| V2 | `data/local/phase3_v2/audited_full_final_v2/research_report.json` | `eff58a1d823f5814cb546f3898eddf625ff7000c079c013213db8bc6f13b6db1` |

These files remain local/ignored and may be absent in another checkout. The previous delivery record reports 43 content-bound ledgers and 38/38 scenario audits; this reset checked the JSON hashes and read report results, not a new execution of that experiment. No run output or evidence hash was altered.

V1: 2021-07-01–2026-06-30 stitched historical OOS, CAGR -0.17%, Sharpe 0.001, maximum drawdown 15.03%, 242 closed trades; the USD $100,000 research account does not establish small-GBP-account feasibility. All these dates are now inspected development data.

V2 on the same inspected period:

| Capital | GBP CAGR | Sharpe | Max drawdown | Orders | FIFO closures | Episodes | Mean exposure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| £1,000 | -3.8917% | -3.5510 | 18.00% | 0 | 0 | 0 | 0% |
| £3,000 | -2.9947% | -0.8198 | 15.4473% | 49 | 26 | 23 | 4.186% |

£1,000 incurred £180 modeled monthly fees and halted 2025-08-29. £3,000 halted 2026-02-27; fixed-fill gross CAGR was -1.2973%. Neither capital had a viable sensitivity neighbor. The £1,000 baseline recorded 18,413 liquidity exclusions out of 20,888 exclusion events. These are repeated dated events, not unique securities.

Known qualification gaps include dividend payment dates/withholding, dated security classifications, retrospective FX reference vintages, empirical calendar certification, account permissions/tariff and complete profit attribution. Ledger arithmetic certification does not resolve those limitations.

The old V2 account model used fixed-stock commission assumptions, actual conversion charges plus a conservative FX allowance, and the full £3 monthly fee without commission offsets. That conservative fee treatment is not evidence of the exact bill. The £1,000 zero-trade path has no trading commissions to offset.

## Legacy conventions needed to interpret results

V1 used weekly momentum/trend/risk scoring, rank buffering, inverse-volatility sizing and a USD research ledger. Phase 1/2 sample data were synthetic; adjusted-price research fills cannot establish raw-share ISA feasibility. V2 used monthly skipped-month momentum, weekly SPY SMA200 exposure, equal weighting with 20/63-session volatility scaling, whole-share execution, a £150 discretionary floor, $500m liquidity filter, GBP/USD cash and permanently latched account halts.

The original validation gates used 8% CAGR, 0.8 Sharpe, 15% drawdown, stressed 6%/0.6, concentration/150-trade/bootstrap tests. V2 added 150 independent episodes, 16 sensitivity neighbors and a post-freeze 756-session guard. V2 was rejected before a qualifying freeze. R3 adds the user's clarified one-year objective and learned ranking without rewriting this history.

## Reproduction

Restore/check out the original revision in a separate location when reproduction is required. Use its original configs, specification Markdown, source dependencies and local data manifests. The existing `python -m src.cli.v2_validation --help` describes required arguments; its old full command is preserved in `docs/PHASE3_V2_IMPLEMENTATION.md` at the revision above. That path was retired from the current tree, not erased from history.

Do not pass today's QUANT_SPEC to an old experiment and claim hash-identical evidence. Do not overwrite local reports to update their prose. Historical reports bind source/spec/data hashes; a new run is a new artifact and requires a new ignored output directory.

## Documentation consolidation

The old `GOAL.md`, `GOAL-PHASE2.md`, `GOAL-PHASE3.md`, `GOAL-PHASE3-V2.md`, five phase documents (`PHASE1_BASELINE`, `PHASE2_RISK_PORTFOLIO`, `PHASE3_HISTORICAL_VALIDATION`, `PHASE3_V2_IMPLEMENTATION`, `PHASE3_V2_INPUTS`), duplicate `QUANT_SPEC_V1.md` and root synthetic `research_report.md` were removed from the current documentation set. Their applicable evidence is summarized here; current requirements live in the six core specifications and strategy review.

The prior delivery recorded 375 passing tests, Ruff/mypy and package builds. Those are historical checks, not checks performed merely by rewriting documentation. The root synthetic report's 6.75% CAGR/4.68 Sharpe was never investment evidence and is no longer displayed as a project result.
