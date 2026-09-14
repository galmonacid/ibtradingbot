from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.data.tiingo_transform import (
    TiingoTransformError,
    transform_tiingo_manifest,
    transform_tiingo_source,
)


def _fixture(root: Path) -> Path:
    raw_path = root / "raw" / "one.json"
    raw_path.parent.mkdir()
    raw_path.write_text(
        json.dumps(
            [
                {
                    "date": "2020-01-02T00:00:00Z",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "adjClose": 9.9,
                    "adjOpen": 9.8,
                    "adjHigh": 10.8,
                    "adjLow": 8.8,
                    "adjVolume": 200,
                    "volume": 100,
                    "divCash": 0.1,
                    "splitFactor": 2,
                }
            ]
        ),
        encoding="utf-8",
    )
    request_value = {
        "end": "2020-01-03",
        "provider_symbol": "AAA",
        "security_id": "SEC-1",
        "start": "2020-01-01",
    }
    request_id = hashlib.sha256(
        (json.dumps(request_value, separators=(",", ":"), sort_keys=True) + "\n").encode()
    ).hexdigest()[:20]
    manifest = {
        "schema_version": "tiingo-extract-manifest-v1",
        "provider": "Tiingo",
        "plan": "paid",
        "api_version": "v1",
        "licence": "terms-reviewed",
        "retrieved_at": "2020-01-04T00:00:00+00:00",
        "complete": True,
        "deployment_admissible": False,
        "paper_execution_permitted": False,
        "requests": [
            {
                "request_id": request_id,
                "security_id": "SEC-1",
                "provider_symbol": "AAA",
                "endpoint": "tiingo/daily/AAA/prices",
                "status": "success",
                "resumed": False,
                "raw_path": "raw/one.json",
                "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "parameters": {
                    "startDate": "2020-01-01",
                    "endDate": "2020-01-03",
                    "resampleFreq": "daily",
                },
                "rows": 1,
            }
        ],
    }
    path = root / "tiingo_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_transforms_verified_prices_dividends_and_splits(tmp_path: Path) -> None:
    bars, actions = transform_tiingo_manifest(_fixture(tmp_path), tmp_path)
    assert bars[0].security_id == "SEC-1"
    assert {(action.action_type, action.value) for action in actions} == {
        ("dividend", 0.1),
        ("split", 2.0),
    }
    source = transform_tiingo_source(tmp_path / "tiingo_manifest.json", tmp_path)
    assert source.provenance.source_name == "Tiingo"
    assert source.provenance.manifest_sha256


def test_hash_or_incomplete_request_fails_closed(tmp_path: Path) -> None:
    manifest_path = _fixture(tmp_path)
    (tmp_path / "raw" / "one.json").write_text("[]", encoding="utf-8")
    with pytest.raises(TiingoTransformError, match="hash mismatch"):
        transform_tiingo_manifest(manifest_path, tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["complete"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(TiingoTransformError, match="incomplete"):
        transform_tiingo_manifest(manifest_path, tmp_path)
