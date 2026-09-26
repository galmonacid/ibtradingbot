from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.cli.historical_build import HistoricalBuildInputError, _exclusions, _sessions


def test_sessions_are_parsed(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.txt"
    sessions_path.write_text("2020-01-02\n2020-01-03\n", encoding="utf-8")
    sessions = _sessions(sessions_path)
    assert sessions == (date(2020, 1, 2), date(2020, 1, 3))


def test_optional_input_records_never_silently_skip_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "exclusions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "security_id": "SEC",
                    "session": "2020-01-02",
                    "reason": "exchange_halt",
                    "unexpected": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(HistoricalBuildInputError, match="invalid fields"):
        _exclusions(path)


def test_session_file_must_be_chronological(tmp_path: Path) -> None:
    path = tmp_path / "sessions.txt"
    path.write_text("2020-01-03\n2020-01-02\n", encoding="utf-8")
    with pytest.raises(HistoricalBuildInputError, match="sorted"):
        _sessions(path)
