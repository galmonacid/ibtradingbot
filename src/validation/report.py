"""Deterministic machine-readable and Markdown Phase 3 report rendering."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.validation.gates import DeploymentGateAssessment

Scalar = str | int | float | bool | None
NamedValues = tuple[tuple[str, Scalar], ...]


@dataclass(frozen=True)
class DatasetSummary:
    name: str
    version: str
    point_in_time: bool
    synthetic: bool
    start: str
    end: str
    sessions: int


@dataclass(frozen=True)
class FoldSummary:
    index: int
    train: str
    validation: str
    test: str
    selected_parameters: NamedValues
    test_observations: int


@dataclass(frozen=True)
class SensitivitySummary:
    fold_index: int
    parameters: NamedValues
    validation_score: float
    selected: bool
    viable: bool


@dataclass(frozen=True)
class BootstrapSummary:
    source: str
    metric: str
    q05: float
    q50: float
    q95: float


@dataclass(frozen=True)
class AblationSummary:
    name: str
    metrics: NamedValues
    deltas_vs_full: NamedValues


@dataclass(frozen=True)
class ValidationReport:
    title: str
    provenance: NamedValues
    dataset: DatasetSummary
    admissible_evidence: bool
    folds: tuple[FoldSummary, ...]
    sensitivity: tuple[SensitivitySummary, ...]
    bootstrap: tuple[BootstrapSummary, ...]
    ablations: tuple[AblationSummary, ...]
    strategy_metrics: NamedValues
    stressed_metrics: NamedValues
    benchmark_metrics: NamedValues
    gates: DeploymentGateAssessment
    limitations: tuple[str, ...]


def _display(value: Scalar) -> str:
    if value is None:
        return "NOT ASSESSABLE"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _named_values(values: NamedValues) -> dict[str, Scalar]:
    return dict(values)


def report_as_dict(report: ValidationReport) -> dict[str, object]:
    """Convert a report to a JSON-ready structure with stable field names."""

    return {
        "title": report.title,
        "decision": {
            "ready_for_paper_trading": (
                report.gates.ready_for_paper_trading and report.admissible_evidence
            ),
            "admissible_evidence": report.admissible_evidence,
        },
        "provenance": _named_values(report.provenance),
        "dataset": asdict(report.dataset),
        "folds": [
            {
                **asdict(fold),
                "selected_parameters": _named_values(fold.selected_parameters),
            }
            for fold in report.folds
        ],
        "sensitivity": [
            {
                **asdict(item),
                "parameters": _named_values(item.parameters),
            }
            for item in report.sensitivity
        ],
        "bootstrap": [asdict(item) for item in report.bootstrap],
        "ablations": [
            {
                **asdict(item),
                "metrics": _named_values(item.metrics),
                "deltas_vs_full": _named_values(item.deltas_vs_full),
            }
            for item in report.ablations
        ],
        "strategy_metrics": _named_values(report.strategy_metrics),
        "stressed_metrics": _named_values(report.stressed_metrics),
        "benchmark_metrics": _named_values(report.benchmark_metrics),
        "gates": [
            {
                "name": gate.name,
                "status": gate.status.value,
                "observed": gate.observed,
                "threshold": gate.threshold,
                "detail": gate.detail,
            }
            for gate in report.gates.gates
        ],
        "limitations": list(report.limitations),
    }


def _values_table(values: NamedValues) -> list[str]:
    if not values:
        return ["_None available._"]
    lines = ["| Field | Value |", "|---|---|"]
    lines.extend(f"| {name} | {_display(value)} |" for name, value in values)
    return lines


def render_markdown(report: ValidationReport) -> str:
    """Render a stable, human-readable Phase 3 report."""

    ready = report.gates.ready_for_paper_trading and report.admissible_evidence
    decision = (
        "PASS — ready for paper trading." if ready else "FAIL CLOSED — not ready for paper trading."
    )
    lines = [f"# {report.title}", "", "## Overall decision", "", f"**{decision}**", ""]
    lines.extend(["## Provenance", "", *_values_table(report.provenance), ""])
    lines.extend(
        [
            "## Dataset and admissibility",
            "",
            f"- Name: {report.dataset.name}",
            f"- Version: {report.dataset.version}",
            f"- Period: {report.dataset.start} to {report.dataset.end}",
            f"- Sessions: {report.dataset.sessions}",
            f"- Point-in-time: {_display(report.dataset.point_in_time)}",
            f"- Synthetic: {_display(report.dataset.synthetic)}",
            f"- Admissible deployment evidence: {_display(report.admissible_evidence)}",
            "",
            "## Walk-forward folds",
            "",
        ]
    )
    if report.folds:
        lines.extend(
            [
                "| Fold | Train | Validation | Test | OOS observations | Parameters |",
                "|---:|---|---|---|---:|---|",
            ]
        )
        for fold in report.folds:
            parameters = ", ".join(
                f"{name}={_display(value)}" for name, value in fold.selected_parameters
            )
            lines.append(
                f"| {fold.index} | {fold.train} | {fold.validation} | {fold.test} | "
                f"{fold.test_observations} | {parameters} |"
            )
    else:
        lines.append("_No admissible walk-forward folds available._")
    lines.extend(["", "## Sensitivity analysis", ""])
    if report.sensitivity:
        lines.extend(
            [
                "| Fold | Parameters | Validation score | Selected | Viable |",
                "|---:|---|---:|---|---|",
            ]
        )
        for sensitivity_item in report.sensitivity:
            parameters = ", ".join(
                f"{name}={_display(value)}" for name, value in sensitivity_item.parameters
            )
            lines.append(
                f"| {sensitivity_item.fold_index} | {parameters} | "
                f"{_display(sensitivity_item.validation_score)} | "
                f"{_display(sensitivity_item.selected)} | "
                f"{_display(sensitivity_item.viable)} |"
            )
    else:
        lines.append("_No sensitivity evidence available._")
    lines.extend(["", "## Bootstrap summaries", ""])
    if report.bootstrap:
        lines.extend(["| Source | Metric | q05 | q50 | q95 |", "|---|---|---:|---:|---:|"])
        lines.extend(
            f"| {item.source} | {item.metric} | {_display(item.q05)} | "
            f"{_display(item.q50)} | {_display(item.q95)} |"
            for item in report.bootstrap
        )
    else:
        lines.append("_No bootstrap evidence available._")
    lines.extend(["", "## Ablation testing", ""])
    if report.ablations:
        lines.extend(["| Scenario | Metrics | Delta vs full |", "|---|---|---|"])
        for ablation_item in report.ablations:
            metrics = ", ".join(
                f"{name}={_display(value)}" for name, value in ablation_item.metrics
            )
            deltas = ", ".join(
                f"{name}={_display(value)}" for name, value in ablation_item.deltas_vs_full
            )
            lines.append(f"| {ablation_item.name} | {metrics} | {deltas} |")
    else:
        lines.append("_No ablation evidence available._")
    lines.extend(["", "## OOS strategy metrics", "", *_values_table(report.strategy_metrics), ""])
    lines.extend(["## Stressed OOS metrics", "", *_values_table(report.stressed_metrics), ""])
    lines.extend(["## Benchmark metrics", "", *_values_table(report.benchmark_metrics), ""])
    lines.extend(
        [
            "## Mandatory deployment gates",
            "",
            "| Gate | Status | Observed | Requirement | Detail |",
            "|---|---|---:|---:|---|",
        ]
    )
    lines.extend(
        f"| {gate.name} | {gate.status.value} | {_display(gate.observed)} | "
        f"{_display(gate.threshold)} | {gate.detail} |"
        for gate in report.gates.gates
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    if not report.limitations:
        lines.append("_None recorded._")
    return "\n".join(lines) + "\n"


def write_report_files(report: ValidationReport, *, json_path: Path, markdown_path: Path) -> None:
    """Write deterministic JSON and Markdown representations of ``report``."""

    json_path.write_text(
        json.dumps(report_as_dict(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
