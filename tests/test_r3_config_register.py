from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.cli.r3_contract import main
from src.config.r3 import EXPECTED_CANDIDATES, EXPECTED_SENSITIVITIES, load_r3_config
from src.validation.r3_register import assess_r3_readiness, preregister_r3

ROOT = Path(__file__).parents[1]


def test_r3_config_fixes_candidate_and_sensitivity_budgets() -> None:
    config = load_r3_config(ROOT / "config.r3.yaml")

    assert config.candidates == EXPECTED_CANDIDATES
    assert config.sensitivities == EXPECTED_SENSITIVITIES
    assert config.initial_capital_gbp == 3000
    assert config.hard_drawdown == 0.15
    assert config.r3_2_scope_decision == "proceed_with_open_label_evidence"
    assert config.r3_2_scope_decision_recorded_at == "2026-09-28"
    assert len(config.sha256) == 64


def test_config_rejects_candidate_search_expansion(tmp_path: Path) -> None:
    content = (ROOT / "config.r3.yaml").read_text(encoding="utf-8")
    path = tmp_path / "expanded.yaml"
    path.write_text(
        content.replace(
            "  - {candidate_id: R3-T-l15, family: hist_gradient_boosting, max_leaf_nodes: 15}\n",
            "  - {candidate_id: R3-T-l15, family: hist_gradient_boosting, max_leaf_nodes: 15}\n"
            "  - {candidate_id: forbidden, family: ridge, alpha: 1.0}\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly the six"):
        load_r3_config(path)


def test_preregistered_contract_carries_evidence_blockers() -> None:
    config = load_r3_config(ROOT / "config.r3.yaml")
    timestamp = datetime(2026, 9, 27, tzinfo=UTC)
    register = preregister_r3(config, timestamp)

    readiness = assess_r3_readiness(config, register)

    assert [row.candidate_id for row in register.trials] == [
        row.candidate_id for row in EXPECTED_CANDIDATES
    ]
    assert all(row.status == "pre_registered" for row in register.trials)
    assert [(row.candidate_id, row.status) for row in register.legacy_controls] == [
        ("V1", "rejected"),
        ("V2", "rejected"),
    ]
    assert readiness.ready is False
    assert readiness.research_scope == "development_only"
    assert set(readiness.blockers) == {
        "r3_1_research_not_accepted",
        "account_tariff_unverified",
        "account_permissions_unverified",
        "operating_costs_unverified",
        "data_qualification_gaps_open",
    }


def test_contract_cli_is_reproducible(capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        "--config",
        str(ROOT / "config.r3.yaml"),
        "--run-timestamp",
        "2026-09-27T15:00:00+00:00",
    ]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out

    assert first == second
    payload = json.loads(first)
    assert payload["readiness"]["ready"] is False
    assert len(payload["candidate_ids"]) == 6
    assert len(payload["sensitivity_ids"]) == 8
