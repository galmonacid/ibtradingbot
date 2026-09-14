from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.validation.gates import DeploymentGateInputs, assess_deployment_gates
from src.validation.report import (
    AblationSummary,
    BootstrapSummary,
    DatasetSummary,
    FoldSummary,
    SensitivitySummary,
    ValidationReport,
    render_markdown,
    write_report_files,
)


def _report(*, admissible: bool = False) -> ValidationReport:
    gates = assess_deployment_gates(
        DeploymentGateInputs(admissible_point_in_time_evidence=admissible)
    )
    return ValidationReport(
        title="Phase 3 Research Report",
        provenance=(("git_revision", "abc123"), ("config_sha256", "c0ffee")),
        dataset=DatasetSummary(
            "fixture", "fixture-v1", False, True, "2024-01-02", "2024-12-31", 252
        ),
        admissible_evidence=admissible,
        folds=(
            FoldSummary(
                0,
                "2007-2014",
                "2015-2016",
                "2017",
                (("positions", 4),),
                252,
            ),
        ),
        sensitivity=(SensitivitySummary(0, (("positions", 4),), 0.91, True, True),),
        bootstrap=(BootstrapSummary("daily", "cagr", 0.01, 0.09, 0.18),),
        ablations=(AblationSummary("momentum_only", (("sharpe", 0.7),), (("sharpe", -0.1),)),),
        strategy_metrics=(("cagr", None),),
        stressed_metrics=(("cagr", None),),
        benchmark_metrics=(("excess_cagr", -0.01), ("information_ratio", None)),
        gates=gates,
        limitations=("Synthetic fixture is not deployment evidence.",),
    )


def test_markdown_contains_required_sections_and_fail_closed_decision() -> None:
    rendered = render_markdown(_report())

    for heading in (
        "## Overall decision",
        "## Provenance",
        "## Dataset and admissibility",
        "## Walk-forward folds",
        "## Sensitivity analysis",
        "## Bootstrap summaries",
        "## Ablation testing",
        "## OOS strategy metrics",
        "## Stressed OOS metrics",
        "## Benchmark metrics",
        "## Mandatory deployment gates",
        "## Limitations",
    ):
        assert heading in rendered
    assert "FAIL CLOSED — not ready for paper trading" in rendered
    assert "abc123" in rendered
    assert "NOT_ASSESSABLE" in rendered


def test_writer_produces_stable_json_and_markdown(tmp_path: Path) -> None:
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "research_report.md"
    report = _report()

    write_report_files(report, json_path=json_path, markdown_path=markdown_path)
    first_json = json_path.read_bytes()
    first_markdown = markdown_path.read_bytes()
    write_report_files(report, json_path=json_path, markdown_path=markdown_path)

    assert json_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_markdown
    payload = json.loads(first_json)
    assert payload["provenance"]["git_revision"] == "abc123"
    assert payload["decision"] == {
        "admissible_evidence": False,
        "ready_for_paper_trading": False,
    }
    assert payload["folds"][0]["selected_parameters"] == {"positions": 4}
    assert payload["sensitivity"][0]["fold_index"] == 0
    assert payload["ablations"][0]["deltas_vs_full"] == {"sharpe": -0.1}


def test_report_states_pass_only_when_admissible_and_every_gate_passes() -> None:
    base = _report(admissible=True)
    gates = assess_deployment_gates(
        DeploymentGateInputs(
            admissible_point_in_time_evidence=True,
            out_of_sample_cagr=0.08,
            out_of_sample_sharpe=0.8,
            out_of_sample_maximum_drawdown=0.15,
            stressed_cagr=0.06,
            stressed_sharpe=0.6,
            closed_trades=150,
            realized_profit_loss_by_year={2020: 34.0, 2021: 33.0, 2022: 33.0},
            realized_profit_loss_by_stock={
                "A": 20.0,
                "B": 20.0,
                "C": 20.0,
                "D": 20.0,
                "E": 20.0,
            },
            nearby_parameters_economically_viable=True,
            bootstrap_cagr_q05=0.0,
            bootstrap_sharpe_q05=0.0,
            bootstrap_maximum_drawdown_q95=0.25,
        )
    )
    passing = replace(base, gates=gates)

    assert "PASS — ready for paper trading" in render_markdown(passing)
