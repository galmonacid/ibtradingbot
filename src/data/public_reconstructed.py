"""Export a clearly non-admissible public reconstruction from ``pitindex``.

The export is intentionally a research input, not a trading-data certification.
It turns the package's sparse S&P 500 membership snapshots into the repository's
canonical half-open membership intervals and records every material limitation in
an immutable manifest.  Daily bars remain a separately supplied public snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from src.data.historical_security_master import HISTORICAL_SECURITY_MASTER_COLUMNS
from src.data.point_in_time_universe import POINT_IN_TIME_UNIVERSE_COLUMNS


class PublicReconstructedError(ValueError):
    """Raised when a public PIT reconstruction cannot be exported safely."""


class _HistoryFrame(Protocol):
    def to_dict(self, orient: str) -> list[dict[str, object]]: ...


class _Pitindex(Protocol):
    def get_constituents_history(self, start: str, end: str, *, index: str) -> _HistoryFrame: ...

    def info(self, *, index: str) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class PublicReconstructedExport:
    """Paths and provenance for one public, explicitly non-admissible export."""

    source_version: str
    membership_path: Path
    security_master_path: Path
    manifest_path: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_pitindex() -> tuple[_Pitindex, str]:
    try:
        import pitindex  # type: ignore[import-not-found]
    except ImportError as error:
        raise PublicReconstructedError(
            "pitindex is required; install the project with the public-data extra"
        ) from error
    try:
        version = importlib.metadata.version("pitindex")
    except importlib.metadata.PackageNotFoundError as error:
        raise PublicReconstructedError("pitindex version metadata is unavailable") from error
    return cast(_Pitindex, pitindex), version


def _as_date(value: object, field: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise PublicReconstructedError(f"pitindex {field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise PublicReconstructedError(f"pitindex {field} must be an ISO date") from error


def _snapshots(records: Iterable[Mapping[str, object]]) -> tuple[tuple[date, frozenset[str]], ...]:
    grouped: dict[date, set[str]] = {}
    for record in records:
        as_of = _as_date(record.get("as_of"), "as_of")
        ticker = record.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise PublicReconstructedError("pitindex membership contains a blank ticker")
        grouped.setdefault(as_of, set()).add(ticker.strip().upper())
    if not grouped:
        raise PublicReconstructedError("pitindex returned no membership snapshots")
    return tuple((as_of, frozenset(symbols)) for as_of, symbols in sorted(grouped.items()))


def _snapshot_sha256(snapshots: tuple[tuple[date, frozenset[str]], ...]) -> str:
    canonical = [
        {"as_of": as_of.isoformat(), "symbols": sorted(symbols)} for as_of, symbols in snapshots
    ]
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _interval_rows(
    snapshots: tuple[tuple[date, frozenset[str]], ...], source_version: str, end: date
) -> tuple[tuple[str, str, str, str], ...]:
    active: dict[str, date] = {}
    rows: list[tuple[str, str, str, str]] = []
    previous: frozenset[str] = frozenset()
    for as_of, current in snapshots:
        for symbol in sorted(previous - current):
            rows.append((source_version, symbol, active.pop(symbol).isoformat(), as_of.isoformat()))
        for symbol in sorted(current - previous):
            active[symbol] = as_of
        previous = current
    exclusive_end = (end + timedelta(days=1)).isoformat()
    rows.extend(
        (source_version, symbol, started.isoformat(), exclusive_end)
        for symbol, started in active.items()
    )
    return tuple(sorted(rows, key=lambda row: (row[1], row[2], row[3])))


def _write_csv(path: Path, header: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def export_pitindex_sp500(
    output_directory: Path, *, start: date, end: date
) -> PublicReconstructedExport:
    """Export public S&P 500 membership and heuristic metadata for research only.

    ``pitindex`` documents S&P 500 coverage from 2005-01-03.  The exporter
    preserves the supplied package snapshot and never calls its mutable refresh
    operation, so a run can be reproduced from the manifest's version/hash.
    """
    if start > end:
        raise PublicReconstructedError("start must not be after end")
    pitindex, package_version = _load_pitindex()
    info = dict(pitindex.info(index="sp500"))
    available_through = _as_date(info.get("end_date"), "info.end_date")
    if end > available_through:
        raise PublicReconstructedError(
            f"pitindex data ends {available_through.isoformat()}, before requested end "
            f"{end.isoformat()}"
        )
    records = pitindex.get_constituents_history(start.isoformat(), end.isoformat(), index="sp500")
    snapshots = _snapshots(records.to_dict("records"))
    if snapshots[0][0] != start:
        raise PublicReconstructedError("pitindex did not return a membership snapshot at start")
    snapshot_sha256 = _snapshot_sha256(snapshots)
    source_version = f"public-reconstructed-pitindex-{package_version}-sp500-{snapshot_sha256[:12]}"
    intervals = _interval_rows(snapshots, source_version, end)
    if not intervals:
        raise PublicReconstructedError("pitindex export produced no membership intervals")

    output_directory.mkdir(parents=True, exist_ok=True)
    membership_path = output_directory / "pitindex_sp500_membership.csv"
    security_master_path = output_directory / "pitindex_sp500_security_master.csv"
    manifest_path = output_directory / "pitindex_sp500_manifest.json"
    _write_csv(membership_path, POINT_IN_TIME_UNIVERSE_COLUMNS, intervals)

    symbols = sorted({row[1] for row in intervals})
    metadata_version = f"{source_version}-heuristic-metadata"
    master_rows = [
        (metadata_version, "SPY", "true", "true", "true", "false", "false", "true"),
        *(
            (metadata_version, symbol, "false", "true", "true", "false", "false", "true")
            for symbol in symbols
        ),
    ]
    _write_csv(security_master_path, HISTORICAL_SECURITY_MASTER_COLUMNS, master_rows)
    manifest: dict[str, Any] = {
        "mode": "public_reconstructed",
        "deployment_admissible": False,
        "paper_execution_permitted": False,
        "source": "pitindex",
        "package_version": package_version,
        "source_version": source_version,
        "snapshot_sha256": snapshot_sha256,
        "index": "sp500",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "source_available_through": available_through.isoformat(),
        "membership_sha256": _sha256(membership_path),
        "security_master_sha256": _sha256(security_master_path),
        "pitindex_info": info,
        "limitations": [
            "Public reconstruction; membership events may be incomplete or conservatively dated.",
            "No corporate-action or delisting-return provenance is supplied by pitindex.",
            "Ticker identity and historical security metadata can be incomplete for"
            " delisted members.",
            "Generated security metadata is a research heuristic, not historical"
            " eligibility evidence.",
            "Public daily bars must be independently imported, hashed, and treated"
            " as incomplete until audited.",
            "This export must not enable paper or live execution.",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return PublicReconstructedExport(
        source_version=source_version,
        membership_path=membership_path,
        security_master_path=security_master_path,
        manifest_path=manifest_path,
    )
