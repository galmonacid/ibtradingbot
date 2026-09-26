"""Development protocol composition, deterministic output and rejected inputs."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from src.config.v2 import V2Config
from src.validation.v2_protocol import FIXED_SENSITIVITIES
from src.validation.v2_workflow import development_scenarios, write_v2_development


def test_fixed_scenarios_preserve_cost_and_account_invariants() -> None:
    config = V2Config(cash_buffer=0.05, commission_per_order_usd=1.50)
    scenarios = development_scenarios(config, date(2026, 6, 26))
    assert len(scenarios) == 19
    assert {item.name for item in scenarios[3:]} == {item.name for item in FIXED_SENSITIVITIES}
    assert scenarios[0].costs.commission_min_usd == 1.50
    assert scenarios[1].costs.commission_min_usd == 3.0
    assert scenarios[1].costs.slippage_bps == 10
    assert scenarios[1].costs.fx_friction_bps == 5
    assert scenarios[2].config.execution_delay_sessions == 2
    assert all(
        item.config.hard_drawdown == 0.15 and item.config.cash_buffer == 0.05 for item in scenarios
    )
    assert len(development_scenarios(config, date(2026, 6, 26), baseline_only=True)) == 1
    with pytest.raises(ValueError, match="fixed V2 center"):
        development_scenarios(replace(config, target_positions=5), date(2026, 6, 26))


def test_reports_are_byte_identical_and_preserve_unexecutable_results(tmp_path: Path) -> None:
    report = {
        "run_id": "a" * 64,
        "baseline_only": True,
        "limitations": ["development only"],
        "scenarios": {
            "gbp1000/baseline": {"status": "unexecutable", "reason": "missing held price"}
        },
    }
    ledgers = {"gbp3000/baseline": {"cash_gbp": 3000, "fills": []}}
    write_v2_development(report, ledgers, tmp_path / "first")
    write_v2_development(report, ledgers, tmp_path / "second")
    for relative in (
        "research_report.json",
        "research_report.md",
        "ledgers/gbp3000__baseline.json",
    ):
        assert (tmp_path / "first" / relative).read_bytes() == (
            tmp_path / "second" / relative
        ).read_bytes()
    text = (tmp_path / "first" / "research_report.md").read_text()
    assert "unexecutable" in text
    assert "paper execution remain blocked" in text
    assert "were not executed" in text


def test_null_sharpe_is_reported_unassessable(tmp_path: Path) -> None:
    report = {
        "run_id": "b" * 64,
        "baseline_only": False,
        "limitations": [],
        "scenarios": {
            "gbp1000/baseline": {
                "status": "executed",
                "summary": {
                    "currencies": {
                        "gbp": {
                            "net_metrics": {
                                "cagr": -0.01,
                                "sharpe_ratio": None,
                                "maximum_drawdown": 0.01,
                            }
                        }
                    }
                },
            }
        },
    }
    write_v2_development(report, {}, tmp_path)
    assert "unassessable" in (tmp_path / "research_report.md").read_text()


def test_account_attribution_table_rows_are_contiguous(tmp_path: Path) -> None:
    summary = {
        "currencies": {
            "gbp": {"net_metrics": dict(cagr=0.0, sharpe_ratio=0.0, maximum_drawdown=0.0)}
        },
        "orders": 0,
        "closed_fifo_lots": 0,
        "completed_position_episodes": 0,
        "mean_exposure": 0.0,
        "first_hard_halt": None,
        "exclusion_events": 1,
        "exclusion_counts_by_reason": {"missing": 1},
        "costs": {"gbp": {"commission": 0.0}},
    }
    report = {
        "run_id": "c" * 64,
        "baseline_only": True,
        "limitations": [],
        "scenarios": {
            "gbp1000/baseline": {"status": "executed", "summary": summary},
            "gbp3000/baseline": {"status": "executed", "summary": summary},
        },
    }
    write_v2_development(report, {}, tmp_path)
    lines = (tmp_path / "research_report.md").read_text().splitlines()
    first = lines.index("| gbp1000/baseline | 0 | 0 | 0 | 0.000000 | unassessable |")
    assert lines[first + 1] == "| gbp3000/baseline | 0 | 0 | 0 | 0.000000 | unassessable |"
    assert lines[first + 2] == ""
    assert lines[first + 3].startswith("Exclusions:")


def test_real_workflow_assembles_currency_specific_gates(monkeypatch, tmp_path: Path) -> None:
    """Execute the account/audit/report chain; mock only certified input assembly and CI paths."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from test_v2_backtest import market_fixture

    from src.validation import v2_workflow as workflow
    from src.validation.v2_protocol import RobustnessResult
    from src.validation.v2_report import summarize_v2_run

    market, fx, start, end = market_fixture()
    inputs = SimpleNamespace(
        validation_start=start,
        canonical=SimpleNamespace(manifest_sha256="a" * 64),
        dataset_evidence_sha256="b" * 64,
        universe_policy_sha256="c" * 64,
        identity=V2Config(),
        dataset_certified=True,
    )
    monkeypatch.setattr(workflow, "build_v2_market", lambda *_: market)
    monkeypatch.setattr(
        workflow,
        "summarize_v2_run",
        lambda ledger, **_: summarize_v2_run(ledger, include_bootstrap=False),
    )
    results = iter([RobustnessResult(True, (), ()), RobustnessResult(False, (), ())] * 2)
    monkeypatch.setattr(workflow, "assess_v2_robustness", lambda _: next(results))
    spec = tmp_path / "spec.md"
    spec.write_text("synthetic test protocol")
    report, ledgers = workflow.run_v2_development(
        inputs,
        market.calendar,
        fx,
        V2Config(),
        start=start,
        end=end,
        run_timestamp=datetime(2026, 9, 24, tzinfo=UTC),
        strategy_spec_path=spec,
        baseline_only=True,
    )
    assert len(ledgers) == 2
    assert all(row["execution_audit"]["passed"] for row in report["scenarios"].values())
    for capital in ("1000", "3000"):
        for currency, expected in (("gbp", True), ("usd", False)):
            assessment = report["development_gate_comparisons"][capital][currency]
            gates = {gate["name"]: gate for gate in assessment["gates"]}
            assert gates["parameter_robustness"]["observed"] is expected
            assert not assessment["ready_for_paper_trading"]
    write_v2_development(report, ledgers, tmp_path / "report")
