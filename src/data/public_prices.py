"""Acquire public daily bars with an explicit incomplete-coverage manifest."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from src.data.ingest import CANONICAL_COLUMNS
from src.data.point_in_time_universe import load_membership_intervals


class PublicPriceError(ValueError):
    """Raised when public-price acquisition cannot create an auditable snapshot."""


class _Frame(Protocol):
    @property
    def empty(self) -> bool: ...

    def to_dict(self, orient: str) -> dict[object, Mapping[object, object]]: ...


class _YFinance(Protocol):
    def download(self, ticker: str, **kwargs: object) -> _Frame: ...


@dataclass(frozen=True)
class PublicPriceExport:
    """Paths produced by one public-price acquisition attempt."""

    bars_path: Path
    manifest_path: Path
    fetched_symbols: int
    failed_symbols: int


def _load_yfinance() -> tuple[_YFinance, str]:
    try:
        import yfinance  # type: ignore[import-not-found]
    except ImportError as error:
        raise PublicPriceError(
            "yfinance is required; install the project with the public-data extra"
        ) from error
    try:
        version = importlib.metadata.version("yfinance")
    except importlib.metadata.PackageNotFoundError as error:
        raise PublicPriceError("yfinance version metadata is unavailable") from error
    return cast(_YFinance, yfinance), version


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    candidate = getattr(value, "date", None)
    if callable(candidate):
        result = candidate()
        if isinstance(result, date):
            return result
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise PublicPriceError("provider returned an unparseable bar date")


def _column(row: Mapping[object, object], name: str) -> object:
    if name in row:
        return row[name]
    for key, value in row.items():
        if isinstance(key, tuple) and key and key[0] == name:
            return value
    raise PublicPriceError(f"provider response lacks {name}")


def _number(row: Mapping[object, object], name: str) -> float:
    value = _column(row, name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PublicPriceError(f"provider {name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise PublicPriceError(f"provider {name} must be finite and positive")
    return numeric


def _provider_symbol(symbol: str) -> str:
    """Map the most common US share-class spelling without changing canonical identity."""
    return symbol.replace(".", "-")


def _rows_from_frame(
    symbol: str, frame: _Frame, *, start: date, end: date
) -> list[tuple[str, str, str, str, str, str, str, str]]:
    if frame.empty:
        raise PublicPriceError("provider returned no rows")
    rows: list[tuple[str, str, str, str, str, str, str, str]] = []
    for raw_date, raw_row in frame.to_dict("index").items():
        bar_date = _as_date(raw_date)
        if not start <= bar_date <= end:
            raise PublicPriceError("provider returned a bar outside the requested date range")
        if not isinstance(raw_row, Mapping):
            raise PublicPriceError("provider returned malformed bar row")
        opening = _number(raw_row, "Open")
        high = _number(raw_row, "High")
        low = _number(raw_row, "Low")
        close = _number(raw_row, "Close")
        adjusted = _number(raw_row, "Adj Close")
        volume = _number(raw_row, "Volume")
        if low > min(opening, close) or high < max(opening, close):
            raise PublicPriceError("provider returned impossible OHLC")
        if not volume.is_integer():
            raise PublicPriceError("provider volume must be integral")
        rows.append(
            (
                bar_date.isoformat(),
                symbol,
                repr(opening),
                repr(high),
                repr(low),
                repr(close),
                repr(adjusted),
                str(int(volume)),
            )
        )
    return rows


def acquire_yahoo_daily_prices(
    membership_path: Path,
    membership_manifest_path: Path,
    output_directory: Path,
    *,
    start: date,
    end: date,
    benchmark: str = "SPY",
) -> PublicPriceExport:
    """Download public Yahoo daily bars for the historical membership union.

    Any failed or empty symbol is retained in the manifest.  The resulting
    snapshot is always incomplete for deployment purposes, even if every call
    succeeds, because public Yahoo responses do not prove delisting/corporate
    action completeness or historical identity continuity.
    """
    if start > end:
        raise PublicPriceError("start must not be after end")
    try:
        membership_manifest = json.loads(membership_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicPriceError("membership manifest must be readable JSON") from error
    if not isinstance(membership_manifest, dict):
        raise PublicPriceError("membership manifest must be a mapping")
    if membership_manifest.get("mode") != "public_reconstructed":
        raise PublicPriceError("membership manifest must describe a public reconstruction")
    membership_hash = hashlib.sha256(membership_path.read_bytes()).hexdigest()
    if membership_manifest.get("membership_sha256") != membership_hash:
        raise PublicPriceError("membership file does not match its manifest hash")
    try:
        coverage_start = date.fromisoformat(str(membership_manifest["requested_start"]))
        membership_end = date.fromisoformat(str(membership_manifest["requested_end"]))
        source_available_through = date.fromisoformat(
            str(membership_manifest["source_available_through"])
        )
    except (KeyError, ValueError) as error:
        raise PublicPriceError("membership manifest lacks canonical coverage dates") from error
    if membership_end > source_available_through:
        raise PublicPriceError("membership manifest exceeds its source availability horizon")
    coverage_end = membership_end
    if start < coverage_start or end > coverage_end:
        raise PublicPriceError(
            "requested price range exceeds the membership reconstruction horizon"
        )
    intervals = load_membership_intervals(membership_path)
    symbols = tuple(sorted({interval.symbol for interval in intervals} | {benchmark}))
    provider, provider_version = _load_yfinance()
    output_directory.mkdir(parents=True, exist_ok=True)
    bars_path = output_directory / "yahoo_public_daily_bars.csv"
    manifest_path = output_directory / "yahoo_public_daily_bars_manifest.json"
    all_rows: list[tuple[str, str, str, str, str, str, str, str]] = []
    fetched: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for symbol in symbols:
        provider_symbol = _provider_symbol(symbol)
        try:
            frame = provider.download(
                provider_symbol,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
            )
            rows = _rows_from_frame(symbol, frame, start=start, end=end)
        except (KeyError, TypeError, ValueError, PublicPriceError) as error:
            failures.append(
                {"symbol": symbol, "provider_symbol": provider_symbol, "reason": str(error)}
            )
            continue
        all_rows.extend(rows)
        fetched.append(
            {"symbol": symbol, "provider_symbol": provider_symbol, "rows": str(len(rows))}
        )
    all_rows.sort(key=lambda row: (row[0], row[1]))
    with bars_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CANONICAL_COLUMNS)
        writer.writerows(all_rows)
    manifest: dict[str, Any] = {
        "mode": "public_reconstructed",
        "provider": "yfinance_yahoo",
        "provider_version": provider_version,
        "deployment_admissible": False,
        "paper_execution_permitted": False,
        "coverage_complete": False,
        "membership_sha256": membership_hash,
        "membership_manifest_sha256": hashlib.sha256(
            membership_manifest_path.read_bytes()
        ).hexdigest(),
        "bars_sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "fetched_symbols": fetched,
        "failed_symbols": failures,
        "limitations": [
            "Provider availability is not proof of historical listing identity or coverage.",
            "No delisting-return, corporate-action, or ticker-reuse completeness is asserted.",
            "Any failed symbol is retained above and must not be silently excluded.",
            "This output must not enable paper or live execution.",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return PublicPriceExport(bars_path, manifest_path, len(fetched), len(failures))
