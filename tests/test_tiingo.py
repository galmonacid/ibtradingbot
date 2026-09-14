from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.data.tiingo import (
    TiingoAcquisitionError,
    TiingoRequest,
    acquire_tiingo_extracts,
)


class _Transport:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[str] = []

    def get_json(self, endpoint: str, parameters: object, token: str) -> object:
        self.calls.append(token)
        if len(self.calls) <= self.failures:
            raise TimeoutError("temporary")
        return [
            {
                "date": "2020-01-02T00:00:00Z",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "adjClose": 10.4,
                "adjOpen": 9.9,
                "adjHigh": 10.9,
                "adjLow": 8.9,
                "adjVolume": 100,
                "volume": 100,
                "divCash": 0,
                "splitFactor": 1,
            }
        ]


def _request() -> tuple[TiingoRequest, ...]:
    return (TiingoRequest("sec-1", "AAA", date(2020, 1, 1), date(2020, 1, 3)),)


def test_acquisition_retries_records_lineage_and_never_serializes_token(tmp_path: Path) -> None:
    transport = _Transport(failures=1)
    result = acquire_tiingo_extracts(
        _request(),
        tmp_path,
        token="top-secret",
        transport=transport,
        plan="paid",
        api_version="v1",
        licence="terms-reviewed",
        maximum_attempts=2,
        retrieved_at=datetime(2020, 1, 4, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    manifest_text = result.manifest_path.read_text()
    manifest = json.loads(manifest_text)
    assert result.successful == 1 and result.failed == 0
    assert "top-secret" not in manifest_text
    assert manifest["complete"] is True
    assert manifest["requests"][0]["status"] == "success"
    assert manifest["deployment_admissible"] is False


def test_acquisition_resumes_valid_extract_without_provider_call(tmp_path: Path) -> None:
    first = _Transport()
    kwargs = dict(
        token="secret",
        plan="paid",
        api_version="v1",
        licence="terms-reviewed",
        retrieved_at=datetime(2020, 1, 4, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    acquire_tiingo_extracts(_request(), tmp_path, transport=first, **kwargs)
    second = _Transport()
    result = acquire_tiingo_extracts(_request(), tmp_path, transport=second, **kwargs)
    assert result.resumed == 1
    assert second.calls == []


def test_acquisition_records_permanent_failure_and_rejects_bad_inputs(tmp_path: Path) -> None:
    result = acquire_tiingo_extracts(
        _request(),
        tmp_path,
        token="secret",
        transport=_Transport(failures=3),
        plan="paid",
        api_version="v1",
        licence="terms-reviewed",
        maximum_attempts=2,
        retrieved_at=datetime(2020, 1, 4, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    assert result.failed == 1
    assert json.loads(result.manifest_path.read_text())["complete"] is False
    with pytest.raises(TiingoAcquisitionError, match="token"):
        acquire_tiingo_extracts(
            _request(),
            tmp_path / "x",
            token="",
            transport=_Transport(),
            plan="paid",
            api_version="v1",
            licence="terms-reviewed",
        )


def test_unmanifested_existing_extract_is_rejected(tmp_path: Path) -> None:
    result = acquire_tiingo_extracts(
        _request(),
        tmp_path,
        token="secret",
        transport=_Transport(),
        plan="paid",
        api_version="v1",
        licence="terms-reviewed",
        sleeper=lambda _: None,
    )
    result.manifest_path.unlink()
    with pytest.raises(TiingoAcquisitionError, match="not bound"):
        acquire_tiingo_extracts(
            _request(),
            tmp_path,
            token="secret",
            transport=_Transport(),
            plan="paid",
            api_version="v1",
            licence="terms-reviewed",
            sleeper=lambda _: None,
        )
