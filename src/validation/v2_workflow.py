"""Content-bound development runs for certified native data and the fixed V2 design.

Dataset certification and research execution are separate. This workflow never
qualifies inspected history or grants broker/paper permission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.backtest.v2 import V2Market, run_v2_backtest
from src.backtest.v2_execution import FeeModel
from src.config.v2 import V2Config, sensitivity_configs
from src.data.calendar import TradingCalendar
from src.data.fx import FXHistory
from src.strategy.v2 import completed_week_dates
from src.validation.gates import DeploymentGateInputs, assess_deployment_gates
from src.validation.native_inputs import NativeValidationInputs
from src.validation.v2_audit import audit_v2_ledger
from src.validation.v2_benchmarks import run_v2_benchmarks
from src.validation.v2_diagnostics import run_v1_single_change_diagnostics
from src.validation.v2_protocol import SensitivityMetrics, assess_v2_robustness
from src.validation.v2_report import summarize_v2_run


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, default=str, allow_nan=False) + "\n"


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def build_v2_market(inputs: NativeValidationInputs, calendar: TradingCalendar) -> V2Market:
    """Use every PIT membership, stable identity and verified canonical bar.

    The calendar must be independently pinned, never synthesized from price rows.
    Native common-stock/primary-listing metadata is not available; the resulting
    limitation is mandatory in the workflow report.
    """
    if not inputs.dataset_certified:
        raise ValueError("V2 native workflow requires certified dataset evidence")
    if calendar.exchange != "XNYS":
        raise ValueError("V2 requires XNYS")
    completed_week_dates(calendar)  # Validates sorted/unique pinned calendar.
    benchmark_ids = {
        row.security_id for row in inputs.canonical.bars if row.symbol == inputs.config.benchmark
    }
    if len(benchmark_ids) != 1:
        raise ValueError("benchmark must resolve to one stable security ID")
    bars: dict[str, dict[date, Any]] = {}
    for row in inputs.canonical.bars:
        bars.setdefault(row.security_id, {})[row.date] = row
    active = {
        day: frozenset(
            row.security_id
            for row in inputs.canonical.memberships
            if row.effective_from <= day and (row.effective_to is None or day < row.effective_to)
        )
        for day in calendar.sessions
    }
    return V2Market(calendar, benchmark_ids.pop(), bars, active, inputs.canonical.actions)


@dataclass(frozen=True)
class DevelopmentScenario:
    name: str
    config: V2Config
    costs: FeeModel


def development_scenarios(
    config: V2Config,
    anchor: date,
    *,
    baseline_only: bool = False,
) -> tuple[DevelopmentScenario, ...]:
    """One fixed baseline, cost stress, extra-session delay and 16 OAT variants."""
    baseline = FeeModel(
        commission_min_usd=max(1.0, config.commission_per_order_usd),
        slippage_bps=config.slippage_bps,
        fx_friction_bps=config.fx_buffer_bps,
    )
    result = [DevelopmentScenario("baseline", config, baseline)]
    if baseline_only:
        return tuple(result)
    result.extend(
        (
            DevelopmentScenario(
                "stressed_costs",
                config,
                replace(
                    baseline,
                    commission_min_usd=baseline.commission_min_usd * 2,
                    commission_per_share=baseline.commission_per_share * 2,
                    slippage_bps=max(10.0, baseline.slippage_bps * 2),
                ),
            ),
            DevelopmentScenario(
                "extra_session_delay",
                replace(config, execution_delay_sessions=config.execution_delay_sessions + 1),
                baseline,
            ),
        )
    )
    # The center may not silently drift while sensitivity results retain fixed names.
    default = V2Config()
    axes = (
        "target_positions",
        "numerator_offset",
        "stock_sma",
        "spy_sma",
        "selection_schedule",
        "volatility_ceiling",
        "long_covariance_window",
        "discretionary_band",
    )
    if any(getattr(config, axis) != getattr(default, axis) for axis in axes):
        raise ValueError("complete protocol requires the predeclared fixed V2 center")
    for name, alternative in sensitivity_configs(anchor):
        axis = name.split("=", 1)[0]
        changes: dict[str, Any] = {axis: getattr(alternative, axis)}
        if axis == "selection_schedule" and alternative.selection_schedule == "biweekly":
            changes["biweekly_anchor"] = anchor
        result.append(DevelopmentScenario(name, replace(config, **changes), baseline))
    return tuple(result)


LIMITATIONS = (
    "Previously inspected history is development evidence; no untouched qualification.",
    "Canonical identity schema lacks dated US-primary/common-stock status; eligibility unverified.",
    "Public broker tariff is modeled; account-specific tariff and permissions are unverified.",
    "Historical FX publication timestamps/vintages require independent certification.",
    "Dividend payment dates are unavailable; receivables cannot fund purchases.",
    "Single-change V1 controls retain the V1 USD ledger and are not small-account comparisons.",
    "FIFO attribution excludes account/conversion fees and dividends; concentration gates "
    "remain unassessable without a reconciled allocation bridge.",
)


def run_v2_development(
    inputs: NativeValidationInputs,
    calendar: TradingCalendar,
    fx: FXHistory,
    config: V2Config,
    *,
    start: date,
    end: date,
    run_timestamp: datetime,
    strategy_spec_path: Path,
    baseline_only: bool = False,
    bootstrap_iterations: int = 2000,
    v1_anchor_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Execute actual ledgers; record failed variants without manufacturing returns."""
    if run_timestamp.utcoffset() is None:
        raise ValueError("run timestamp must include timezone")
    if type(bootstrap_iterations) is not int or bootstrap_iterations < 2000:
        raise ValueError("V2 reports require at least 2000 bootstrap paths")
    market = build_v2_market(inputs, calendar)
    if start not in calendar.sessions or end not in calendar.sessions or start > end:
        raise ValueError("run endpoints must be ordered pinned sessions")
    if inputs.validation_start is None or start < inputs.validation_start:
        raise ValueError("run starts before certified validation coverage")
    # A subsequent pinned session proves final weekly/monthly boundaries.
    if end >= calendar.sessions[-1]:
        raise ValueError("calendar must extend beyond the final run session")
    dates = tuple(day for day in calendar.sessions if start <= day <= end)
    if any(day not in market.bars[market.benchmark_id] for day in dates):
        raise ValueError("benchmark missing a pinned run session")
    anchors = tuple(day for day in completed_week_dates(calendar) if day <= start)
    if not anchors:
        raise ValueError("calendar needs a completed week to anchor sensitivity")
    scenarios = development_scenarios(config, anchors[-1], baseline_only=baseline_only)
    market_hash = _digest(
        {
            "canonical_manifest": inputs.canonical.manifest_sha256,
            "calendar": calendar.source_sha256,
            "dataset_evidence": inputs.dataset_evidence_sha256,
            "universe_policy": inputs.universe_policy_sha256,
        }
    )
    anchor_report = json.loads(v1_anchor_path.read_text()) if v1_anchor_path else None
    identities = {
        "v1_anchor_sha256": hashlib.sha256(v1_anchor_path.read_bytes()).hexdigest()
        if v1_anchor_path
        else None,
        "native_input": asdict(inputs.identity),
        "config": config.sha256,
        "strategy_spec": hashlib.sha256(strategy_spec_path.read_bytes()).hexdigest(),
        "calendar": calendar.source_sha256,
        "calendar_version": calendar.version,
        "fx": fx.sha256,
        "fx_source": fx.source,
        "fx_licence": fx.licence,
        "fx_synthetic": fx.synthetic,
        "market": market_hash,
        "run_timestamp": run_timestamp.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bootstrap_iterations": bootstrap_iterations,
        "bootstrap_seed": 20260909,
        "bootstrap_scenarios": ["baseline", "stressed_costs", "extra_session_delay"],
        "monthly_fee_gbp": 3.0,
        "fractional": False,
        "biweekly_anchor": anchors[-1].isoformat(),
        "scenarios": [
            {"name": item.name, "config": asdict(item.config), "costs": asdict(item.costs)}
            for item in scenarios
        ],
    }
    result: dict[str, Any] = {
        "run_id": _digest(identities),
        "identities": identities,
        "evidence_class": "development",
        "dataset_certified": inputs.dataset_certified,
        "deployment_admissible": False,
        "paper_execution_permitted": False,
        "baseline_only": baseline_only,
        "protocol_complete": False,
        "limitations": list(LIMITATIONS)
        + (
            [
                "Calendar derives from observed SPY sessions; "
                "independent XNYS calendar completeness is unverified."
            ]
            if "empirical" in calendar.version
            else []
        ),
        "scenarios": {},
        "robustness": {},
        "v1_anchor": anchor_report,
        "unsupported_diagnostics": {
            name: "unexecutable: supporting interfaces missing"
            for name in (
                "v1_only_monthly",
                "v1_only_score",
                "v1_only_equal_weight",
                "v1_only_regime",
                "v1_only_covariance",
                "spy_buy_hold",
                "spy_v2_risk_budget",
            )
        },
    }
    ledgers: dict[str, dict[str, Any]] = {}
    for capital in (1000, 3000):
        metrics: dict[str, dict[str, SensitivityMetrics]] = {"gbp": {}, "usd": {}}
        for scenario in scenarios:
            key = f"gbp{capital}/{scenario.name}"
            try:
                ledger = run_v2_backtest(
                    market,
                    fx,
                    scenario.config,
                    start=start,
                    end=end,
                    initial_capital_gbp=capital,
                    fractional=False,
                    costs=scenario.costs,
                    monthly_fee_gbp=3.0,
                )
                audit = audit_v2_ledger(
                    ledger,
                    market,
                    fx,
                    scenario.config,
                    scenario.costs,
                    initial_capital_gbp=capital,
                    start=start,
                    end=end,
                )
                ledgers[key] = ledger
                if not audit.passed:
                    raise ValueError("execution audit failed: " + "; ".join(audit.findings[:10]))
                summary = summarize_v2_run(
                    ledger,
                    bootstrap_iterations=bootstrap_iterations,
                    include_bootstrap=scenario.name
                    in {"baseline", "stressed_costs", "extra_session_delay"},
                )
                ledgers[key] = ledger
                result["scenarios"][key] = {
                    "status": "executed",
                    "summary": summary,
                    "ledger_sha256": _digest(ledger),
                    "config_sha256": scenario.config.sha256,
                    "cost_sha256": _digest(asdict(scenario.costs)),
                    "invalid_evidence": ledger["invalid_evidence"],
                    "execution_audit": asdict(audit),
                }
                for currency in ("gbp", "usd"):
                    net = summary["currencies"][currency]["net_metrics"]
                    metrics[currency][scenario.name] = SensitivityMetrics(
                        net["cagr"] if net["cagr"] is not None else float("nan"),
                        net["sharpe_ratio"] if net["sharpe_ratio"] is not None else float("nan"),
                        abs(net["maximum_drawdown"])
                        if net["maximum_drawdown"] is not None
                        else float("nan"),
                        executable=not ledger["invalid_evidence"],
                    )
            except (ValueError, ArithmeticError) as error:
                result["scenarios"][key] = {
                    "status": "unexecutable",
                    "reason": str(error),
                    "config_sha256": scenario.config.sha256,
                    "cost_sha256": _digest(asdict(scenario.costs)),
                }
        result["robustness"][str(capital)] = {
            currency: asdict(assess_v2_robustness(metrics[currency])) for currency in ("gbp", "usd")
        }
    result["development_gate_comparisons"] = {}
    for capital in (1000, 3000):
        baseline_row = result["scenarios"].get(f"gbp{capital}/baseline", {})
        stressed_row = result["scenarios"].get(f"gbp{capital}/stressed_costs", {})
        baseline_summary = baseline_row.get("summary", {})
        stress_summary = stressed_row.get("summary", {})
        comparisons = {}
        for currency in ("gbp", "usd"):
            baseline_currency = baseline_summary.get("currencies", {}).get(currency, {})
            metric = baseline_currency.get("net_metrics", {})
            stress = stress_summary.get("currencies", {}).get(currency, {}).get("net_metrics", {})
            bootstrap = baseline_summary.get("bootstrap", {}).get(currency, {})

            def tail(
                name: str,
                quantile: str,
                worst: str,
                distribution: dict[str, Any] = bootstrap,
            ) -> float | None:
                values = [
                    (distribution.get(kind, {}).get(name) or {}).get(quantile)
                    for kind in ("daily", "regime")
                ]
                if any(value is None for value in values):
                    return None
                numeric = [float(value) for value in values if value is not None]
                return min(numeric) if worst == "min" else max(numeric)

            drawdown = metric.get("maximum_drawdown")
            gates = assess_deployment_gates(
                DeploymentGateInputs(
                    admissible_point_in_time_evidence=False,
                    out_of_sample_cagr=metric.get("cagr"),
                    out_of_sample_sharpe=metric.get("sharpe_ratio"),
                    out_of_sample_maximum_drawdown=abs(drawdown) if drawdown is not None else None,
                    stressed_cagr=stress.get("cagr"),
                    stressed_sharpe=stress.get("sharpe_ratio"),
                    closed_trades=baseline_summary.get("closed_fifo_lots"),
                    realized_profit_loss_by_year=None,
                    realized_profit_loss_by_stock=None,
                    nearby_parameters_economically_viable=result["robustness"][str(capital)][
                        currency
                    ]["passed"],
                    bootstrap_cagr_q05=tail("cagr", "q05", "min"),
                    bootstrap_sharpe_q05=tail("sharpe", "q05", "min"),
                    bootstrap_maximum_drawdown_q95=tail("maximum_drawdown", "q95", "max"),
                )
            )
            comparisons[currency] = asdict(gates)
        comparisons["completed_episode_gate"] = {
            "observed": baseline_summary.get("completed_position_episodes"),
            "threshold": 150,
            "passed": baseline_summary.get("episode_minimum_met", False),
        }
        result["development_gate_comparisons"][str(capital)] = comparisons
    if not baseline_only:
        result["single_change_diagnostics"] = run_v1_single_change_diagnostics(
            inputs, start=start, end=end, v2_market=market
        )
        result["benchmarks"] = {}
        for capital in (1000, 3000):
            for name in ("cash", "spy_buy_hold", "spy_risk_budget"):
                key = f"gbp{capital}/reference_{name}"
                try:
                    ledger = run_v2_benchmarks(
                        market,
                        fx,
                        config,
                        start=start,
                        end=end,
                        initial_capital_gbp=capital,
                        modes=(name,),
                    )[name]
                    ledgers[key] = ledger
                    result["benchmarks"][key] = {
                        "status": "executed",
                        "summary": summarize_v2_run(ledger, include_bootstrap=False),
                        "ledger_sha256": _digest(ledger),
                    }
                except (ValueError, ArithmeticError) as error:
                    result["benchmarks"][key] = {"status": "unexecutable", "reason": str(error)}
        result["unsupported_diagnostics"] = {}
    result["report_sha256"] = _digest(result)
    return result, ledgers


def write_v2_development(
    report: dict[str, Any],
    ledgers: dict[str, dict[str, Any]],
    output_directory: Path,
) -> None:
    """Write stable bytes with fixed caller provenance, and preserve exact ledgers."""
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "research_report.json").write_text(_json(report))
    lines = [
        "# V2 development research",
        "",
        f"Run: `{report['run_id']}`",
        "",
        "Development only. Qualification and paper execution remain blocked.",
        "",
        "| Scenario | Status | GBP CAGR | GBP Sharpe | GBP max drawdown |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for name, item in sorted(report["scenarios"].items()):
        if item["status"] == "executed":
            net = item["summary"]["currencies"]["gbp"]["net_metrics"]
            displayed = [
                "unassessable" if net[key] is None else f"{net[key]:.6f}"
                for key in ("cagr", "sharpe_ratio", "maximum_drawdown")
            ]
            lines.append(f"| {name} | executed | " + " | ".join(displayed) + " |")
        else:
            lines.append(f"| {name} | unexecutable | — | — | — |")

    def cell(value: Any) -> str:
        if value is None:
            return "unassessable"
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value).replace("|", "/").replace("\n", " ")

    failures = [
        (name, item["reason"])
        for name, item in report["scenarios"].items()
        if item["status"] != "executed"
    ]
    if failures:
        lines.extend(["", "## Unexecutable scenarios", ""])
        lines.extend(f"- {cell(name)}: {cell(reason)}" for name, reason in failures)
    lines.extend(
        [
            "",
            "## Account attribution",
            "",
            "| Scenario | Orders | FIFO closures | Episodes | Mean exposure | First hard halt |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    attribution_rows: list[tuple[str, dict[str, Any]]] = []
    for name, item in sorted(report["scenarios"].items()):
        if item["status"] != "executed" or not name.endswith(
            ("baseline", "stressed_costs", "extra_session_delay")
        ):
            continue
        summary = item["summary"]
        attribution_rows.append((name, summary))
        fields = [
            summary.get(k)
            for k in (
                "orders",
                "closed_fifo_lots",
                "completed_position_episodes",
                "mean_exposure",
                "first_hard_halt",
            )
        ]
        lines.append(f"| {cell(name)} | " + " | ".join(cell(v) for v in fields) + " |")
    for name, summary in attribution_rows:
        lines.append("")
        lines.append(
            f"Exclusions: {cell(summary.get('exclusion_events'))}; by reason: "
            + ", ".join(
                f"{reason}={count}"
                for reason, count in summary.get("exclusion_counts_by_reason", {}).items()
            )
            + ". Exact rows are retained in the content-bound scenario ledger."
        )
        for currency, costs in summary.get("costs", {}).items():
            lines.append(
                f"{name} {currency.upper()} costs: "
                + ", ".join(f"{key}={cell(value)}" for key, value in costs.items())
                + "."
            )
    for capital, currencies in sorted(report.get("development_gate_comparisons", {}).items()):
        lines.extend(
            [
                "",
                f"## £{capital} development gate comparisons",
                "",
                "Development metrics are compared to unchanged thresholds; "
                "this is not OOS qualification.",
                "",
                "| Currency | Gate | Status | Observed | Required threshold |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for currency in ("gbp", "usd"):
            for gate in currencies[currency]["gates"]:
                lines.append(
                    "| "
                    + " | ".join(
                        cell(v)
                        for v in (
                            currency.upper(),
                            gate["name"],
                            gate["status"],
                            gate["observed"],
                            gate["threshold"],
                        )
                    )
                    + " |"
                )
        episode = currencies["completed_episode_gate"]
        lines.extend(
            ["", f"Independent completed episodes: {cell(episode['observed'])}; required 150."]
        )
    lines.extend(["", "## Fixed sensitivity robustness", ""])
    for capital, currencies in sorted(report.get("robustness", {}).items()):
        for currency, assessment in currencies.items():
            lines.append(
                f"- £{capital} {currency.upper()}: {len(assessment['viable_variants'])}/16 viable "
                f"(required 13 and a neighbor on every axis); passed={assessment['passed']}. "
                f"Failed axes: {', '.join(assessment['failed_axes']) or 'none'}."
            )
    controls = report.get("single_change_diagnostics", {})
    if controls:
        lines.extend(
            [
                "",
                "## Matched USD controls",
                "",
                "USD $100,000 V1/single-change/V2 diagnostics on the same dates and cost rates; "
                "engine differences are disclosed below. These are not GBP small-account results.",
                "",
                "| Control | Status | CAGR | Sharpe | Drawdown | Orders |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, row in sorted(controls.get("runs", {}).items()):
            metric = row.get("metrics", {})
            lines.append(
                "| "
                + " | ".join(
                    cell(v)
                    for v in (
                        name,
                        row["status"],
                        metric.get("cagr"),
                        metric.get("sharpe_ratio"),
                        metric.get("maximum_drawdown"),
                        row.get("orders"),
                    )
                )
                + " |"
            )
        lines.extend(["", *[f"- {item}" for item in controls.get("limitations", [])]])
    if report.get("benchmarks"):
        lines.extend(
            [
                "",
                "## References",
                "",
                "SPY is a cap-exempt diagnostic, not a tradable stock-strategy holding.",
                "",
                "| Reference | Status | GBP CAGR | GBP Sharpe | GBP drawdown |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for name, row in sorted(report["benchmarks"].items()):
            metric = (
                row.get("summary", {}).get("currencies", {}).get("gbp", {}).get("net_metrics", {})
            )
            lines.append(
                "| "
                + " | ".join(
                    cell(v)
                    for v in (
                        name,
                        row.get("status"),
                        metric.get("cagr"),
                        metric.get("sharpe_ratio"),
                        metric.get("maximum_drawdown"),
                    )
                )
                + " |"
            )
            if row.get("reason"):
                lines.extend(["", f"{cell(name)}: {cell(row['reason'])}", ""])
    for name, item in sorted(report["scenarios"].items()):
        if item["status"] != "executed" or not name.endswith("baseline"):
            continue
        summary = item["summary"]
        lines.extend(["", f"## {name} bootstrap and annual evidence", ""])
        for currency, bootstrap in summary.get("bootstrap", {}).items():
            lines.append(f"{currency.upper()} bootstrap: {bootstrap['status']}.")
            if bootstrap["status"] == "available":
                lines.extend(
                    [
                        "",
                        "| Method | Metric | q05 | q50 | q95 |",
                        "| --- | --- | ---: | ---: | ---: |",
                    ]
                )
                for method in ("daily", "regime"):
                    for metric, values in bootstrap[method].items():
                        lines.append(
                            "| "
                            + " | ".join(
                                cell(v)
                                for v in (
                                    method,
                                    metric,
                                    *[(values or {}).get(q) for q in ("q05", "q50", "q95")],
                                )
                            )
                            + " |"
                        )
            else:
                lines.append(cell(bootstrap.get("reason")))
        for currency, years in summary.get("annual_returns", {}).items():
            lines.extend(
                [
                    "",
                    f"{currency.upper()} annual returns: "
                    + ", ".join(f"{year}={cell(value)}" for year, value in sorted(years.items()))
                    + ".",
                ]
            )
        for currency, evidence in summary.get("currencies", {}).items():
            if "gross_fixed_fill_metrics" in evidence:
                lines.extend(
                    [
                        "",
                        f"{currency.upper()} fixed-fill gross CAGR: "
                        f"{cell(evidence['gross_fixed_fill_metrics'].get('cagr'))}; "
                        f"net CAGR: {cell(evidence['net_metrics'].get('cagr'))}.",
                        evidence["gross_fixed_fill_note"],
                        evidence["realized_attribution_note"],
                        f"Account P&L outside closed FIFO attribution: "
                        f"{cell(evidence['unallocated_account_profit'])} {currency.upper()}.",
                    ]
                )
            stocks = evidence.get("realized_profit_loss_by_stock", {})
            lines.extend(["", f"{currency.upper()} realized stock contributions:", ""])
            lines.extend(f"- {stock}: {cell(value)}" for stock, value in sorted(stocks.items()))
    lines.extend(
        ["", "Full daily ledgers and detailed attribution are preserved alongside the JSON report."]
    )
    lines.extend(["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]])
    if report["baseline_only"]:
        lines.extend(["", "Baseline-only diagnostic: stress/delay/sensitivity were not executed."])
    (output_directory / "research_report.md").write_text("\n".join(lines) + "\n")
    ledger_directory = output_directory / "ledgers"
    ledger_directory.mkdir(exist_ok=True)
    for name, ledger in sorted(ledgers.items()):
        safe_name = name.replace("/", "__").replace("=", "-")
        (ledger_directory / f"{safe_name}.json").write_text(_json(ledger))
