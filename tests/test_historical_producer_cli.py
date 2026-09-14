from __future__ import annotations

import json
import sys
from pathlib import Path

from src.cli import historical_producer
from src.data.tiingo import TiingoAcquisitionResult


def test_cli_uses_named_environment_without_printing_token(
    tmp_path: Path, monkeypatch: object, capsys: object
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

    monkeypatch.setenv("SAFE_TOKEN_NAME", "secret-value")  # type: ignore[attr-defined]
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
            "--plan",
            "paid",
            "--licence",
            "terms-reviewed",
        ],
    )
    assert historical_producer.main() == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "secret-value" not in captured.out
    assert seen["token"] == "secret-value"
