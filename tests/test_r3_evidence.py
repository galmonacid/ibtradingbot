from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.data.r3_evidence import (
    acquire_nasdaq_dividend_evidence,
    build_independent_xnys_calendar,
    load_cash_action_evidence,
    rebuild_ecb_gbp_usd,
)


class _Response:
    def __init__(self, payload: object) -> None:
        self._content = json.dumps(payload).encode()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._content


def test_public_dividend_evidence_uses_payment_not_ex_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "data": {
            "dividends": {
                "rows": [
                    {
                        "exOrEffDate": "02/09/2024",
                        "amount": "$0.24",
                        "declarationDate": "02/01/2024",
                        "recordDate": "02/12/2024",
                        "paymentDate": "02/15/2024",
                        "currency": "USD",
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(
        "src.data.r3_evidence.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    manifest = acquire_nasdaq_dividend_evidence(
        (("SEC-AAPL", "AAPL", date(2024, 2, 9), 0.24),),
        tmp_path,
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
        retrieved_at=datetime(2026, 9, 28, tzinfo=UTC),
        maximum_workers=1,
    )
    evidence = load_cash_action_evidence(
        tmp_path / "cash_action_evidence.csv",
        tmp_path / "cash_action_evidence_manifest.json",
    )

    assert manifest["matched_rows"] == 1
    assert evidence.rows[0].effective_date == date(2024, 2, 9)
    assert evidence.rows[0].payment_date == date(2024, 2, 15)
    assert evidence.rows[0].withholding_fraction == 0.15
    assert evidence.rows[0].source_available_at.date() == date(2024, 2, 1)


def test_spdr_dividend_evidence_uses_official_payable_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook_path = tmp_path / "spdr.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "dividend"
    worksheet.append(
        ["FUND NAME", "TICKER", "CUSIP", "EX-DATE", "RECORD DATE", "PAYABLE DATE", "DIVIDEND ($)"]
    )
    worksheet.append(
        [
            "SPDR S&P 500 ETF Trust",
            "SPY",
            "78462F103",
            "03/15/2024",
            "03/18/2024",
            "04/30/2024",
            "1.594937",
        ]
    )
    workbook.save(workbook_path)
    monkeypatch.setattr(
        "src.data.r3_evidence.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response({"data": None}),
    )

    manifest = acquire_nasdaq_dividend_evidence(
        (("SEC-SPY", "SPY", date(2024, 3, 15), 1.59494),),
        tmp_path / "evidence",
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
        retrieved_at=datetime(2026, 9, 28, tzinfo=UTC),
        maximum_workers=1,
        spdr_distributions_path=workbook_path,
    )
    evidence = load_cash_action_evidence(
        tmp_path / "evidence" / "cash_action_evidence.csv",
        tmp_path / "evidence" / "cash_action_evidence_manifest.json",
    )

    assert manifest["spdr_distributions_sha256"]
    assert manifest["unmatched_rows"] == 0
    assert evidence.rows[0].payment_date == date(2024, 4, 30)
    assert evidence.rows[0].source_id == "state-street-spdr-historical-distributions"


def test_full_ecb_rebuild_preserves_causal_availability_and_archive_hash(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "ecb.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "eurofxref-hist.csv",
            "Date,USD,GBP\n2024-01-03,1.25,.875\n2024-01-02,1.20,.84\n",
        )
    output_csv = tmp_path / "fx.csv"
    output_manifest = tmp_path / "fx-manifest.json"
    manifest = rebuild_ecb_gbp_usd(
        archive,
        output_csv,
        output_manifest,
        retrieved_at=datetime(2026, 9, 28, tzinfo=UTC),
    )

    assert manifest["rows"] == 2
    assert manifest["start"] == "2024-01-02"
    assert manifest["vintage_certified"] is False
    assert manifest["source_archive_sha256"]
    lines = output_csv.read_text().splitlines()
    assert "2024-01-02T14:10:00+01:00,2024-01-03T00:00:00+00:00" in lines[1]


def test_independent_xnys_evidence_round_trips_through_calendar_loader(
    tmp_path: Path,
) -> None:
    pytest.importorskip("exchange_calendars")
    from src.data.calendar import load_trading_calendar

    csv_path = tmp_path / "xnys.csv"
    manifest_path = tmp_path / "xnys-manifest.json"
    manifest = build_independent_xnys_calendar(
        csv_path,
        manifest_path,
        start=date(2024, 1, 2),
        end=date(2024, 1, 12),
        retrieved_at=datetime(2026, 9, 28, tzinfo=UTC),
    )
    calendar = load_trading_calendar(csv_path)

    assert manifest["independent_of_price_rows"] is True
    assert manifest["sha256"] == calendar.source_sha256
    assert date(2024, 1, 6) not in calendar.sessions
    assert calendar.exchange == "XNYS"
