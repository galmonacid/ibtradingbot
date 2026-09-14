from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from src.data.point_in_time_universe import POINT_IN_TIME_UNIVERSE_COLUMNS
from src.data.public_prices import PublicPriceError, _rows_from_frame, acquire_yahoo_daily_prices


class _Frame:
    def __init__(self, rows: dict[object, dict[object, object]]) -> None:
        self.rows = rows

    @property
    def empty(self) -> bool:
        return not self.rows

    def to_dict(self, orient: str) -> dict[object, dict[object, object]]:
        assert orient == "index"
        return self.rows


class _YFinance(ModuleType):
    def __init__(self) -> None:
        super().__init__("yfinance")
        self.calls: list[str] = []

    def download(self, ticker: str, **kwargs: object) -> _Frame:
        self.calls.append(ticker)
        assert kwargs["auto_adjust"] is False
        if ticker == "MISSING":
            return _Frame({})
        return _Frame(
            {
                date(2007, 1, 2): {
                    "Open": 10.0,
                    "High": 11.0,
                    "Low": 9.0,
                    "Close": 10.5,
                    "Adj Close": 10.25,
                    "Volume": 100,
                }
            }
        )


def _membership(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(POINT_IN_TIME_UNIVERSE_COLUMNS)
        writer.writerows(
            [
                ("public-v1", "AAA", "2007-01-01", ""),
                ("public-v1", "MISSING", "2007-01-01", ""),
            ]
        )
    manifest = path.with_name("membership_manifest.json")
    manifest.write_text(
        json.dumps(
            {
                "mode": "public_reconstructed",
                "membership_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "requested_start": "2007-01-01",
                "requested_end": "2007-01-02",
                "source_available_through": "2007-01-05",
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_acquisition_writes_canonical_bars_and_retains_failed_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _YFinance()
    monkeypatch.setitem(sys.modules, "yfinance", provider)
    monkeypatch.setattr("src.data.public_prices.importlib.metadata.version", lambda _: "1.7.0")
    membership = tmp_path / "membership.csv"
    membership_manifest = _membership(membership)

    result = acquire_yahoo_daily_prices(
        membership,
        membership_manifest,
        tmp_path / "output",
        start=date(2007, 1, 1),
        end=date(2007, 1, 2),
    )

    rows = list(csv.DictReader(result.bars_path.open(encoding="utf-8")))
    assert {row["symbol"] for row in rows} == {"AAA", "SPY"}
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["coverage_complete"] is False
    assert manifest["deployment_admissible"] is False
    assert manifest["failed_symbols"] == [
        {"provider_symbol": "MISSING", "reason": "provider returned no rows", "symbol": "MISSING"}
    ]
    assert result.fetched_symbols == 2
    assert result.failed_symbols == 1


def test_acquisition_rejects_invalid_date_range(tmp_path: Path) -> None:
    membership = tmp_path / "membership.csv"
    membership_manifest = _membership(membership)
    with pytest.raises(PublicPriceError, match="start must not be after"):
        acquire_yahoo_daily_prices(
            membership,
            membership_manifest,
            tmp_path / "output",
            start=date(2007, 1, 2),
            end=date(2007, 1, 1),
        )


def test_acquisition_rejects_out_of_range_provider_rows() -> None:
    frame = _Frame(
        {
            date(2007, 1, 3): {
                "Open": 10.0,
                "High": 11.0,
                "Low": 9.0,
                "Close": 10.5,
                "Adj Close": 10.25,
                "Volume": 100,
            }
        }
    )
    with pytest.raises(PublicPriceError, match="outside the requested"):
        _rows_from_frame("AAA", frame, start=date(2007, 1, 1), end=date(2007, 1, 2))


def test_acquisition_rejects_range_beyond_membership_manifest(tmp_path: Path) -> None:
    membership = tmp_path / "membership.csv"
    membership_manifest = _membership(membership)
    with pytest.raises(PublicPriceError, match="exceeds the membership"):
        acquire_yahoo_daily_prices(
            membership,
            membership_manifest,
            tmp_path / "output",
            start=date(2007, 1, 1),
            end=date(2007, 1, 3),
        )
