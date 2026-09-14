from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.cli.historical_build import (
    HistoricalBuildInputError,
    _exclusions,
    _execution,
    _sessions,
)


def test_sessions_and_execution_audit_are_parsed_and_audited(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.txt"
    sessions_path.write_text("2020-01-02\n2020-01-03\n", encoding="utf-8")
    sessions = _sessions(sessions_path)
    execution_path = tmp_path / "execution.json"
    execution_path.write_text(
        json.dumps(
            [
                {
                    "decision_session": "2020-01-02",
                    "fill_session": "2020-01-03",
                    "security_id": "SEC",
                    "notional": 1000,
                    "fill_price": 10,
                    "baseline_commission": 0.35,
                    "stressed_commission": 0.7,
                    "baseline_slippage_bps": 5,
                    "stressed_slippage_bps": 10,
                }
            ]
        ),
        encoding="utf-8",
    )
    assert sessions == (date(2020, 1, 2), date(2020, 1, 3))
    assert _execution(execution_path, sessions).passed


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
