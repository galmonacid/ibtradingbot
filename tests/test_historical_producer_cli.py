from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.cli import historical_producer
from src.data.tiingo import TiingoAcquisitionResult


@pytest.mark.parametrize("source", ["environment", "file"])
def test_cli_uses_credentials_without_printing_token(
    tmp_path: Path, monkeypatch: object, capsys: object, source: str
) -> None:
    plan = tmp_path / "requests.json"
    plan.write_text(
        json.dumps(
            [
                {
                    "security_id": "SEC-1",
                    "provider_symbol": "AAA",
                    "start": "2020-01-01",
                    "end": "2020-01-02",
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir()
    manifest = output / "tiingo_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake(*args: object, **kwargs: object) -> TiingoAcquisitionResult:
        seen.update(kwargs)
        return TiingoAcquisitionResult(manifest, 1, 0, 0)

    credentials = tmp_path / "credentials.local.toml"
    credentials.write_text('[tiingo]\napi_token = "secret-value"\n')
    if source == "environment":
        monkeypatch.setenv("SAFE_TOKEN_NAME", "secret-value")  # type: ignore[attr-defined]
    else:
        monkeypatch.delenv("SAFE_TOKEN_NAME", raising=False)  # type: ignore[attr-defined]
    monkeypatch.setattr(historical_producer, "acquire_tiingo_extracts", fake)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sys,
        "argv",
        [
            "producer",
            "--request-plan",
            str(plan),
            "--output-directory",
            str(output),
            "--token-environment",
            "SAFE_TOKEN_NAME",
            "--credentials-file",
            str(credentials),
            "--plan",
            "paid",
            "--licence",
            "terms-reviewed",
        ],
    )
    assert historical_producer.main() == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "secret-value" not in captured.out
    assert "secret-value" not in captured.err
    assert seen["token"] == "secret-value"
