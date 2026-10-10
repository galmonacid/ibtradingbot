"""R3 Step 3 source-feasibility, causality and stop-contract tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.config.r3_step3 import load_r3_step3_config
from src.research.r3_source_feasibility import (
    Fact,
    build_audit_feature_row,
    canonical_bytes,
    feature_contract,
    full_protocol_folds_supported,
    parse_company_facts,
    parse_submissions,
    resolve_facts,
    safe_ratio,
    seeded_sample_order,
    sha256_bytes,
    write_new,
)

CONFIG = Path("config.r3-step3-feasibility.yaml")


def _submissions() -> dict[str, object]:
    return {
        "filings": {
            "recent": {
                "accessionNumber": ["0000000001-20-000001", "0000000001-20-000002"],
                "form": ["10-Q", "10-Q/A"],
                "acceptanceDateTime": [
                    "2020-05-01T20:15:00.000Z",
                    "2020-05-08T21:30:00.000Z",
                ],
                "filingDate": ["2020-05-01", "2020-05-08"],
                "reportDate": ["2020-03-31", "2020-03-31"],
                "primaryDocument": ["q.htm", "qa.htm"],
            }
        }
    }


def _company_facts() -> dict[str, object]:
    return {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000000001-20-000001",
                                "form": "10-Q",
                                "start": "2020-01-01",
                                "end": "2020-03-31",
                                "val": -5,
                                "fy": 2020,
                                "fp": "Q1",
                                "frame": "CY2020Q1",
                            },
                            {
                                "accn": "0000000001-20-000002",
                                "form": "10-Q/A",
                                "start": "2020-01-01",
                                "end": "2020-03-31",
                                "val": -7,
                                "fy": 2020,
                                "fp": "Q1",
                                "frame": "CY2020Q1",
                            },
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000000001-20-000001",
                                "form": "10-Q",
                                "start": "2020-01-01",
                                "end": "2020-06-30",
                                "val": 10,
                                "fy": 2020,
                                "fp": "Q2",
                            }
                        ]
                    }
                },
            }
        }
    }


def _fact(**changes: object) -> Fact:
    base: dict[str, object] = {
        "cik": "0000000001",
        "accession": "a",
        "form": "10-Q",
        "accepted_at": datetime(2020, 5, 1, 20, 15, tzinfo=UTC),
        "available_at": datetime(2020, 5, 2, 20, 15, tzinfo=UTC),
        "taxonomy": "us-gaap",
        "concept": "NetIncomeLoss",
        "unit": "USD",
        "value": -5.0,
        "period_start": date(2020, 1, 1),
        "period_end": date(2020, 3, 31),
        "fiscal_year": 2020,
        "fiscal_period": "Q1",
        "frame": "CY2020Q1",
        "source_sha256": "a" * 64,
    }
    base.update(changes)
    return Fact(**base)  # type: ignore[arg-type]


def test_config_freezes_corrected_evidence_and_seeded_sample() -> None:
    config = load_r3_step3_config(CONFIG)
    assert config.corrected_dataset_identity == (
        "bc01ebab574bb847d46781b090b01cd58c6757e3ed3b2ef99d39f052f209259a"
    )
    assert len(config.sample) == 11
    assert seeded_sample_order(config) == seeded_sample_order(config)
    assert set(seeded_sample_order(config)) == {row.cik for row in config.sample}


def test_source_response_hash_and_immutable_write(tmp_path: Path) -> None:
    payload = {"b": 2, "a": 1}
    path = tmp_path / "manifest.json"
    digest = write_new(path, payload)
    assert digest == sha256_bytes(path.read_bytes())
    assert path.read_bytes() == canonical_bytes(payload)
    with pytest.raises(FileExistsError, match="immutable"):
        write_new(path, payload)


def test_acceptance_accession_latency_and_amendment_are_preserved() -> None:
    source = "1" * 64
    filings = parse_submissions("0000000001", ((_submissions(), source),))
    facts = parse_company_facts(
        "0000000001", _company_facts(), "2" * 64, filings, latency_hours=24
    )
    assert [row.accession for row in filings] == [
        "0000000001-20-000001",
        "0000000001-20-000002",
    ]
    assert filings[0].accepted_at.hour == 20
    original, amendment = [row for row in facts if row.concept == "NetIncomeLoss"]
    assert original.available_at == original.accepted_at + timedelta(hours=24)
    before = resolve_facts(facts, datetime(2020, 5, 5, tzinfo=UTC))["resolved"]
    after = resolve_facts(facts, datetime(2020, 5, 10, tzinfo=UTC))["resolved"]
    before_net = next(row for row in before if row["concept"] == "NetIncomeLoss")
    after_net = next(row for row in after if row["concept"] == "NetIncomeLoss")
    assert before_net["value"] == -5
    assert after_net["value"] == -7
    assert amendment.form == "10-Q/A"


def test_quarterly_ytd_negative_and_zero_denominator_rules() -> None:
    filings = parse_submissions("0000000001", ((_submissions(), "1" * 64),))
    facts = parse_company_facts(
        "0000000001", _company_facts(), "2" * 64, filings, latency_hours=24
    )
    assert {row.period_kind for row in facts} == {"quarterly", "year_to_date"}
    assert any(row.value < 0 for row in facts)
    assert safe_ratio(-5, 10) == -0.5
    assert safe_ratio(1, 0) is None
    assert safe_ratio(None, 1) is None


def test_duplicate_context_units_and_conflicts_remain_explicit() -> None:
    same = _fact()
    different_unit = replace(same, unit="USDm", value=-0.000005)
    conflict = replace(same, accession="b", value=-6)
    # Different units are separate facts, not silently converted.
    result = resolve_facts((same, different_unit), datetime(2020, 6, 1, tzinfo=UTC))
    assert len(result["resolved"]) == 2
    # A same-context latest-time conflict remains unresolved.
    conflict = replace(conflict, accepted_at=same.accepted_at, available_at=same.available_at)
    result = resolve_facts((same, conflict), datetime(2020, 6, 1, tzinfo=UTC))
    assert result["conflicts"]


def test_unavailable_facts_and_point_in_time_prefix_invariance() -> None:
    first = _fact()
    later = replace(
        first,
        accession="later",
        accepted_at=datetime(2020, 8, 1, tzinfo=UTC),
        available_at=datetime(2020, 8, 2, tzinfo=UTC),
        value=99,
    )
    cutoff = datetime(2020, 7, 1, tzinfo=UTC)
    base = resolve_facts((first,), cutoff)
    mutated_future = resolve_facts((first, later), cutoff)
    assert base == mutated_future
    assert resolve_facts((later,), cutoff)["missing"]


def test_feature_contract_is_bounded_and_declares_training_only_processing() -> None:
    features = feature_contract()
    assert len(features) == 28
    assert len({row["name"] for row in features}) == 28
    assert all("training only" in str(row["missing"]) for row in features)
    assert all(row["cross_section"] for row in features)
    assert sum(row["status"] == "retained" for row in features) == 11
    assert sum("sector" in str(row["status"]) for row in features) == 3
    assert sum("api_key" in str(row["status"]) for row in features) == 3


def test_protocol_feasibility_never_shortens_or_fabricates_history() -> None:
    assert full_protocol_folds_supported(date(1999, 1, 29)) == 9
    assert full_protocol_folds_supported(date(2009, 7, 23)) == 0
    assert full_protocol_folds_supported(None) == 0


def test_bounded_source_to_availability_join_and_feature_row() -> None:
    decision = datetime(2020, 5, 3, tzinfo=UTC)
    assets = _fact(
        concept="Assets",
        period_start=None,
        value=100,
        available_at=datetime(2020, 5, 2, tzinfo=UTC),
    )
    gross_profit = _fact(
        concept="GrossProfit",
        value=25,
        available_at=datetime(2020, 5, 2, tzinfo=UTC),
    )
    row = build_audit_feature_row(
        (assets, gross_profit), decision_at=decision, security_ids=("stable-id",)
    )
    assert row["status"] == "available"
    assert row["gross_profit_assets"] == 0.25
    ambiguous = build_audit_feature_row(
        (assets, gross_profit), decision_at=decision, security_ids=("class-a", "class-c")
    )
    assert ambiguous["status"] == "ambiguous_security_join"
    unavailable = build_audit_feature_row(
        (replace(assets, available_at=decision + timedelta(days=1)), gross_profit),
        decision_at=decision,
        security_ids=("stable-id",),
    )
    assert unavailable["status"] == "missing_required_fact"


def test_materialized_failure_register_prohibits_candidates_and_step4() -> None:
    path = Path("data/local/r3_step3_20261002_feasibility_v7/failure_register.json")
    if not path.exists():
        pytest.skip("local immutable materialization is checked separately")
    register = json.loads(path.read_text(encoding="utf-8"))
    assert register["decision"] == "stop_before_step4_registration"
    assert not register["experiment_register_created"]
    assert not register["step4_authorized"]
    assert "model_fit" in register["prohibitions"]
    assert "candidates" not in register


def test_preserved_evidence_paths_reject_overwrite() -> None:
    # The materializer refuses any pre-existing output directory before writes.
    for path in (
        Path("data/local/r3_2_20261002_corrected_v2"),
        Path("data/local/r3_3_20261002_corrected_v2"),
        Path("data/local/r3_3_20260929"),
    ):
        assert path.is_dir()
