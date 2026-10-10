"""Post-Step-3 evidence-preservation and governance-package tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.config.r3_post_step3 import load_r3_post_step3_config
from src.research.r3_post_step3_decision import (
    blocker_traceability,
    build_decision_artifacts,
    canonical_bytes,
    governance_options,
    identity_requirements,
    prospective_date_support,
    source_permission_cost_decisions,
    validate_decision_artifacts,
    verify_preserved_evidence,
    write_new,
)

CONFIG = Path("config.r3-post-step3-decision.yaml")


def _config():  # type: ignore[no-untyped-def]
    return load_r3_post_step3_config(CONFIG)


def _fixed_provenance() -> dict[str, object]:
    return {
        "run_timestamp": "2026-10-03T09:00:00+00:00",
        "seed": 20261003,
        "git_revision": "a" * 40,
        "git_committed_tree": "b" * 40,
        "git_dirty": True,
        "dirty_state_identity": "c" * 64,
        "implementation_tree_sha256": "d" * 64,
        "config_file_sha256": "e" * 64,
        "dependencies": {"PyYAML": "fixed"},
    }


def test_preserved_evidence_hashes_and_manifests_validate() -> None:
    result = verify_preserved_evidence(_config())
    assert result["all_verified"] is True
    assert result["step3_package_identity"] == _config().step3_package_identity
    assert result["corrected_dataset_identity"] == _config().corrected_dataset_identity
    assert [row["entries"] for row in result["model_manifests"]] == [541, 541]


def test_immutable_output_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "decision.json"
    write_new(path, {"decision": "bounded"})
    with pytest.raises(FileExistsError, match="immutable"):
        write_new(path, {"decision": "changed"})


def test_governance_register_is_exact_and_deterministic() -> None:
    first = governance_options()
    second = governance_options()
    assert canonical_bytes(first) == canonical_bytes(second)
    assert [row["option"] for row in first] == ["A", "B", "C"]
    assert first[1]["solves_sec_history_blocker"] is False
    assert first[0]["can_proceed_without_new_authority"] is True
    assert first[1]["can_proceed_without_new_authority"] is False
    assert first[2]["can_proceed_without_new_authority"] is False


def test_identity_requirements_cover_ticker_changes_and_multiple_classes() -> None:
    requirements = identity_requirements()
    cases = requirements["known_cases"]
    assert cases["multiple_classes"]
    assert cases["ticker_and_name_changes"]
    assert cases["mergers_and_delistings"]
    tests = " ".join(requirements["validation_tests"])
    assert "ticker change" in tests
    assert "multiple simultaneously active security classes" in tests
    assert (
        requirements["decision"]
        == "current local master cannot be repaired from existing evidence alone"
    )


def test_present_day_metadata_substitution_is_explicitly_rejected() -> None:
    requirements = identity_requirements()
    assert requirements["present_day_metadata_substitution"]["allowed"] is False
    artifacts = build_decision_artifacts(_config(), provenance=_fixed_provenance())
    sector = artifacts["sector_macro_decision_records.json"]["sector"]
    assert sector["present_day_sector_backfill_allowed"] is False


def test_sec_history_support_calculation_does_not_treat_imputation_as_history() -> None:
    support = prospective_date_support(_config())
    assert support["frozen_protocol"]["supported_complete_enriched_folds"] == 0
    assert support["sec_sample"]["precoverage_gap_days"] == 3828
    assert (
        support["prospective_lower_bound_only"]["earliest_possible_enriched_training_start"]
        == "2009-07-23"
    )
    assert (
        support["prospective_lower_bound_only"]["nominal_eight_year_training_end"] == "2017-07-23"
    )
    distinction = support["missingness_distinction"]
    assert "cannot make a frozen fold enriched" in distinction["not_genuine_enriched_evaluation"]


def test_protocol_change_and_step4_registration_are_prohibited() -> None:
    artifacts = build_decision_artifacts(_config(), provenance=_fixed_provenance())
    validate_decision_artifacts(artifacts)
    amendment = artifacts["no_protocol_amendment_executed.json"]
    step4 = artifacts["no_step4_registration_created.json"]
    assert amendment["protocol_amendment_executed"] is False
    assert step4["step4_authorized"] is False
    assert step4["step4_registration_created"] is False
    assert "experiment_register.json" not in artifacts


def test_decision_code_cannot_import_learning_scoring_simulation_or_backtests() -> None:
    paths = [
        Path("src/research/r3_post_step3_decision.py"),
        Path("src/cli/r3_post_step3_decision.py"),
    ]
    imported: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    prohibited = {
        "src.learning",
        "src.strategy",
        "src.portfolio",
        "src.backtest",
        "src.research.r3_development",
    }
    assert not any(
        any(name == root or name.startswith(f"{root}.") for root in prohibited) for name in imported
    )
    actions = build_decision_artifacts(_config(), provenance=_fixed_provenance())[
        "no_step4_registration_created.json"
    ]["prohibited_actions_performed"]
    assert actions and not any(actions.values())


def test_unknown_costs_remain_unknown() -> None:
    rows = source_permission_cost_decisions()
    by_path = {row["path"]: row for row in rows}
    assert by_path["issuer-security identity"]["observed_cost_gbp"] is None
    assert by_path["dated sector metadata"]["observed_cost_gbp"] is None
    assert by_path["ALFRED vintages"]["observed_cost_gbp"] is None
    assert by_path["local storage/CPU/no hosting"]["assumed_cost_gbp"] == 0
    assert blocker_traceability()[-1]["disposition"] == "unknowns preserved; no affordability claim"


def test_fixed_inputs_timestamp_and_seed_reproduce_every_artifact_byte_for_byte() -> None:
    first = build_decision_artifacts(_config(), provenance=_fixed_provenance())
    second = build_decision_artifacts(_config(), provenance=_fixed_provenance())
    assert first.keys() == second.keys()
    assert {name: canonical_bytes(value) for name, value in first.items()} == {
        name: canonical_bytes(value) for name, value in second.items()
    }


def test_materialized_local_package_contains_no_registration_or_performance_artifact() -> None:
    package = Path("data/local/r3_post_step3_20261003_decision_v1")
    if not package.exists():
        pytest.skip("local immutable materialization is checked separately")
    names = {path.name for path in package.iterdir()}
    assert "no_protocol_amendment_executed.json" in names
    assert "no_step4_registration_created.json" in names
    assert not any("experiment_register" in name for name in names)
    manifest = json.loads((package / "artifact_hash_manifest.json").read_text())
    assert len(manifest["artifacts"]) == 11
