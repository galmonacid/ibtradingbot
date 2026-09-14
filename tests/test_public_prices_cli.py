from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from src.cli import public_prices
from src.data.public_prices import PublicPriceExport


def test_cli_invokes_acquisition_with_manifest(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def acquire(*args: object, **kwargs: object) -> PublicPriceExport:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return PublicPriceExport(tmp_path / "bars.csv", tmp_path / "manifest.json", 2, 1)

    monkeypatch.setattr(public_prices, "acquire_yahoo_daily_prices", acquire)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "momentum-public-daily-prices",
            "--membership",
            "membership.csv",
            "--membership-manifest",
            "membership.json",
            "--output-directory",
            "output",
            "--start",
            "2007-01-01",
            "--end",
            "2007-01-02",
        ],
    )

    assert public_prices.main() == 0
    assert captured["kwargs"] == {
        "start": date(2007, 1, 1),
        "end": date(2007, 1, 2),
        "benchmark": "SPY",
    }
