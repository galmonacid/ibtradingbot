from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from src.data.historical_security_master import load_historical_security_master
from src.data.point_in_time_universe import load_membership_intervals, resolve_membership
from src.data.public_reconstructed import PublicReconstructedError, export_pitindex_sp500


class _Frame:
    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return [
            {"as_of": "2007-01-01", "ticker": "AAA"},
            {"as_of": "2007-01-01", "ticker": "BBB"},
            {"as_of": "2007-02-01", "ticker": "BBB"},
            {"as_of": "2007-02-01", "ticker": "CCC"},
        ]


class _Pitindex(ModuleType):
    def __init__(self) -> None:
        super().__init__("pitindex")

    def get_constituents_history(self, start: str, end: str, *, index: str) -> _Frame:
        assert (start, end, index) == ("2007-01-01", "2007-02-01", "sp500")
        return _Frame()

    def info(self, *, index: str) -> dict[str, object]:
        assert index == "sp500"
        return {
            "start_date": "2004-12-30",
            "end_date": "2007-02-01",
            "build_timestamp_utc": "2026-09-12T00:00:00Z",
        }


def test_export_creates_canonical_pit_inputs_and_non_admissible_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "pitindex", _Pitindex())
    monkeypatch.setattr(
        "src.data.public_reconstructed.importlib.metadata.version", lambda _: "0.2.1"
    )

    result = export_pitindex_sp500(tmp_path, start=date(2007, 1, 1), end=date(2007, 2, 1))

    membership = load_membership_intervals(
        result.membership_path, expected_source_version=result.source_version
    )
    assert resolve_membership(membership, date(2007, 1, 31)).symbols == ("AAA", "BBB")
    assert resolve_membership(membership, date(2007, 2, 1)).symbols == ("BBB", "CCC")
    assert resolve_membership(membership, date(2007, 2, 2)).symbols == ()
    master = load_historical_security_master(
        result.security_master_path,
        benchmark="SPY",
        expected_metadata_version=f"{result.source_version}-heuristic-metadata",
    )
    assert [security.symbol for security in master] == ["AAA", "BBB", "CCC", "SPY"]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["deployment_admissible"] is False
    assert manifest["paper_execution_permitted"] is False
    assert manifest["membership_sha256"]
    assert len(manifest["snapshot_sha256"]) == 64


def test_export_rejects_a_request_beyond_the_pitindex_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "pitindex", _Pitindex())
    monkeypatch.setattr(
        "src.data.public_reconstructed.importlib.metadata.version", lambda _: "0.2.1"
    )

    with pytest.raises(PublicReconstructedError, match="data ends"):
        export_pitindex_sp500(tmp_path, start=date(2007, 1, 1), end=date(2007, 2, 2))


def test_export_requires_pitindex_and_valid_dates(tmp_path: Path) -> None:
    with pytest.raises(PublicReconstructedError, match="start must not be after"):
        export_pitindex_sp500(tmp_path, start=date(2007, 2, 1), end=date(2007, 1, 1))
