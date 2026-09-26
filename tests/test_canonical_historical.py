from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.data.canonical_historical import (
    CanonicalCorporateAction,
    CanonicalDailyBar,
    CanonicalHistoricalError,
    CanonicalSourceProvenance,
    VerifiedCanonicalInputs,
    load_verified_canonical_inputs,
    verify_canonical_parquet,
    write_canonical_parquet,
)
from src.data.trusted_historical import SecurityIdentityInterval, SecurityMembershipInterval

pytest.importorskip("pyarrow")


def _inputs() -> dict[str, object]:
    return {
        "bars": (
            CanonicalDailyBar(
                "SEC-1",
                "AAA",
                date(2020, 1, 2),
                10,
                11,
                9,
                10,
                10,
                100,
                10,
                11,
                9,
                100,
            ),
        ),
        "identities": (SecurityIdentityInterval("SEC-1", "AAA", date(2020, 1, 1), None),),
        "memberships": (SecurityMembershipInterval("pit-v1", "SEC-1", date(2020, 1, 1), None),),
        "actions": (CanonicalCorporateAction("SEC-1", "AAA", date(2020, 1, 2), "dividend", 0.1),),
        "source_provenance": (
            CanonicalSourceProvenance(
                "membership",
                "git",
                "a" * 64,
                "2026-09-13T00:00:00+00:00",
                "MIT",
                repository_url="https://example.test/repo",
                commit_sha="b" * 40,
            ),
        ),
        "transformation_version": "test-transform-v1",
    }


def test_writes_explicit_canonical_tables_and_manifest(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    result = write_canonical_parquet(tmp_path / "canonical", **_inputs())  # type: ignore[arg-type]
    payload = json.loads(result.manifest_path.read_text())
    assert {item["path"] for item in payload["files"]} == {
        "daily_bars.parquet",
        "security_master.parquet",
        "membership.parquet",
        "corporate_actions.parquet",
    }
    assert all(len(item["sha256"]) == 64 for item in payload["files"])
    assert payload["deployment_admissible"] is False
    assert payload["transformation_version"] == "test-transform-v1"
    assert payload["source_provenance"][0]["commit_sha"] == "b" * 40
    assert verify_canonical_parquet(result.manifest_path).files == result.files
    loaded = load_verified_canonical_inputs(result.manifest_path)
    assert loaded.bars == _inputs()["bars"]
    assert loaded.manifest_sha256
    assert (
        str(pq.read_schema(result.output_directory / "daily_bars.parquet").field("date").type)
        == "date32[day]"
    )


def test_verified_canonical_inputs_cannot_be_caller_constructed() -> None:
    with pytest.raises(CanonicalHistoricalError, match="canonical loader"):
        VerifiedCanonicalInputs(  # type: ignore[arg-type]
            object(), "a" * 64, "v1", (), (), (), (), ()
        )


def test_refuses_overwrite_and_duplicate_or_invalid_bars(tmp_path: Path) -> None:
    output = tmp_path / "canonical"
    write_canonical_parquet(output, **_inputs())  # type: ignore[arg-type]
    with pytest.raises(CanonicalHistoricalError, match="new or empty"):
        write_canonical_parquet(output, **_inputs())  # type: ignore[arg-type]
    values = _inputs()
    bar = values["bars"][0]  # type: ignore[index]
    values["bars"] = (bar, bar)
    with pytest.raises(CanonicalHistoricalError, match="duplicate"):
        write_canonical_parquet(tmp_path / "bad", **values)  # type: ignore[arg-type]


def test_verifier_rejects_tampered_parquet(tmp_path: Path) -> None:
    result = write_canonical_parquet(tmp_path / "canonical", **_inputs())  # type: ignore[arg-type]
    path = result.output_directory / "daily_bars.parquet"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(CanonicalHistoricalError, match="hash mismatch"):
        verify_canonical_parquet(result.manifest_path)
