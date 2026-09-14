"""Transform verified immutable Tiingo extracts into canonical records."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from src.data.canonical_historical import (
    CanonicalCorporateAction,
    CanonicalDailyBar,
    CanonicalSourceProvenance,
)
from src.data.tiingo import TiingoRequest


class TiingoTransformError(ValueError):
    """Raised when a Tiingo extract or manifest cannot be trusted."""


_TIINGO_TRANSFORM_ATTESTATION = object()


@dataclass(frozen=True)
class TiingoTransformResult:
    bars: tuple[CanonicalDailyBar, ...]
    actions: tuple[CanonicalCorporateAction, ...]
    provenance: CanonicalSourceProvenance
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _TIINGO_TRANSFORM_ATTESTATION:
            raise TiingoTransformError("Tiingo source results must be issued by the transformer")


def _request_id(request: TiingoRequest) -> str:
    value = {
        "end": request.end.isoformat(),
        "provider_symbol": request.provider_symbol,
        "security_id": request.security_id,
        "start": request.start.isoformat(),
    }
    raw = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _number(row: dict[str, Any], field: str, *, positive: bool = True) -> float:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TiingoTransformError(f"Tiingo {field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise TiingoTransformError(f"Tiingo {field} has an invalid value")
    return result


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise TiingoTransformError("Tiingo date must be a string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as error:
        raise TiingoTransformError("Tiingo date is invalid") from error


def transform_tiingo_manifest(
    manifest_path: Path, extract_root: Path
) -> tuple[tuple[CanonicalDailyBar, ...], tuple[CanonicalCorporateAction, ...]]:
    """Verify and transform every successful request; any failed request fails closed."""
    try:
        payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TiingoTransformError("Tiingo manifest must be readable JSON") from error
    top_level = {
        "schema_version",
        "provider",
        "plan",
        "api_version",
        "licence",
        "retrieved_at",
        "requests",
        "complete",
        "deployment_admissible",
        "paper_execution_permitted",
    }
    if not isinstance(payload, dict) or set(payload) != top_level:
        raise TiingoTransformError("unsupported Tiingo manifest schema")
    if (
        payload.get("schema_version") != "tiingo-extract-manifest-v1"
        or payload.get("provider") != "Tiingo"
        or not isinstance(payload.get("plan"), str)
        or not payload.get("plan")
        or not isinstance(payload.get("api_version"), str)
        or not payload.get("api_version")
        or not isinstance(payload.get("licence"), str)
        or not payload.get("licence")
        or payload.get("deployment_admissible") is not False
        or payload.get("paper_execution_permitted") is not False
    ):
        raise TiingoTransformError("Tiingo manifest provenance or safety flags are invalid")
    try:
        retrieved_at = datetime.fromisoformat(str(payload["retrieved_at"]))
    except ValueError as error:
        raise TiingoTransformError("Tiingo retrieval timestamp is invalid") from error
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise TiingoTransformError("Tiingo retrieval timestamp must be timezone-aware")
    if payload.get("complete") is not True:
        raise TiingoTransformError("Tiingo manifest contains failed or incomplete requests")
    requests = payload.get("requests")
    if not isinstance(requests, list) or not requests:
        raise TiingoTransformError("Tiingo manifest has no requests")
    root = extract_root.resolve()
    bars: list[CanonicalDailyBar] = []
    actions: list[CanonicalCorporateAction] = []
    seen_requests: set[str] = set()
    for request in requests:
        success_fields = {
            "request_id",
            "security_id",
            "provider_symbol",
            "endpoint",
            "parameters",
            "status",
            "resumed",
            "raw_path",
            "raw_sha256",
            "rows",
        }
        if (
            not isinstance(request, dict)
            or set(request) != success_fields
            or request.get("status") != "success"
            or not isinstance(request.get("resumed"), bool)
        ):
            raise TiingoTransformError("Tiingo manifest contains a non-success request")
        request_id = request.get("request_id")
        security_id = request.get("security_id")
        symbol = request.get("provider_symbol")
        relative = request.get("raw_path")
        expected_hash = request.get("raw_sha256")
        parameters = request.get("parameters")
        if not all(
            isinstance(value, str) and value
            for value in (request_id, security_id, symbol, relative, expected_hash)
        ):
            raise TiingoTransformError("Tiingo success record lacks immutable identity")
        assert isinstance(request_id, str)
        assert isinstance(security_id, str)
        assert isinstance(symbol, str)
        assert isinstance(relative, str)
        assert isinstance(expected_hash, str)
        if len(expected_hash) != 64 or any(
            character not in "0123456789abcdef" for character in expected_hash
        ):
            raise TiingoTransformError("Tiingo raw hash is not canonical SHA-256")
        if (
            not isinstance(parameters, dict)
            or set(parameters) != {"startDate", "endDate", "resampleFreq"}
            or parameters.get("resampleFreq") != "daily"
        ):
            raise TiingoTransformError("Tiingo request parameters are not canonical daily bounds")
        try:
            request_start = date.fromisoformat(str(parameters["startDate"]))
            request_end = date.fromisoformat(str(parameters["endDate"]))
        except ValueError as error:
            raise TiingoTransformError("Tiingo request bounds are invalid") from error
        expected_request_id = _request_id(
            TiingoRequest(security_id, symbol, request_start, request_end)
        )
        if request_id != expected_request_id:
            raise TiingoTransformError("Tiingo request ID does not match its identity and bounds")
        if request.get("endpoint") != f"tiingo/daily/{symbol}/prices":
            raise TiingoTransformError("Tiingo endpoint does not match its provider symbol")
        if request_id in seen_requests:
            raise TiingoTransformError("duplicate Tiingo request record")
        seen_requests.add(request_id)
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
            raise TiingoTransformError("Tiingo raw path is not canonical and confined")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise TiingoTransformError("Tiingo raw extract is missing")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise TiingoTransformError("Tiingo raw extract hash mismatch")
        try:
            rows: object = json.loads(raw)
        except json.JSONDecodeError as error:
            raise TiingoTransformError("Tiingo raw extract is invalid JSON") from error
        if not isinstance(rows, list) or not rows:
            raise TiingoTransformError("Tiingo raw extract is empty")
        previous_date: date | None = None
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                raise TiingoTransformError("Tiingo raw row is malformed")
            row = raw_row
            bar_date = _date(row.get("date"))
            if not request_start <= bar_date <= request_end:
                raise TiingoTransformError("Tiingo row date is outside its request bounds")
            if previous_date is not None and bar_date <= previous_date:
                raise TiingoTransformError("Tiingo rows must be strictly chronological and unique")
            previous_date = bar_date
            volume = _number(row, "volume", positive=False)
            if not volume.is_integer():
                raise TiingoTransformError("Tiingo volume must be integral")
            adjusted_volume = _number(row, "adjVolume", positive=False)
            if not adjusted_volume.is_integer():
                raise TiingoTransformError("Tiingo adjusted volume must be integral")
            bar = CanonicalDailyBar(
                security_id,
                symbol,
                bar_date,
                _number(row, "open"),
                _number(row, "high"),
                _number(row, "low"),
                _number(row, "close"),
                _number(row, "adjClose"),
                int(volume),
                _number(row, "adjOpen"),
                _number(row, "adjHigh"),
                _number(row, "adjLow"),
                int(adjusted_volume),
            )
            bars.append(bar)
            dividend = _number(row, "divCash", positive=False) if "divCash" in row else 0.0
            split = _number(row, "splitFactor") if "splitFactor" in row else 1.0
            if dividend > 0:
                actions.append(
                    CanonicalCorporateAction(security_id, symbol, bar_date, "dividend", dividend)
                )
            if not math.isclose(split, 1.0, abs_tol=1e-12):
                actions.append(
                    CanonicalCorporateAction(security_id, symbol, bar_date, "split", split)
                )
        recorded_rows = request.get("rows")
        if recorded_rows is not None and recorded_rows != len(rows):
            raise TiingoTransformError("Tiingo raw row count contradicts its manifest")
    ordered_bars = tuple(sorted(bars))
    if len({(bar.security_id, bar.date) for bar in ordered_bars}) != len(ordered_bars):
        raise TiingoTransformError("overlapping Tiingo requests produced duplicate bars")
    return ordered_bars, tuple(sorted(actions))


def transform_tiingo_source(manifest_path: Path, extract_root: Path) -> TiingoTransformResult:
    """Return verified records together with manifest-bound provider provenance."""
    bars, actions = transform_tiingo_manifest(manifest_path, extract_root)
    manifest_bytes = manifest_path.read_bytes()
    payload: object = json.loads(manifest_bytes)
    if not isinstance(payload, dict):  # already checked above; keeps this boundary typed
        raise TiingoTransformError("Tiingo manifest must be a mapping")
    requests = payload["requests"]
    assert isinstance(requests, list)
    parameter_records = [
        {
            "security_id": request["security_id"],
            "endpoint": request["endpoint"],
            "parameters": request["parameters"],
        }
        for request in requests
        if isinstance(request, dict)
    ]
    parameters_sha = hashlib.sha256(
        json.dumps(parameter_records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    provenance = CanonicalSourceProvenance(
        "Tiingo",
        "provider",
        hashlib.sha256(manifest_bytes).hexdigest(),
        str(payload["retrieved_at"]),
        str(payload["licence"]),
        plan=str(payload["plan"]),
        api_version=str(payload["api_version"]),
        request_parameters_sha256=parameters_sha,
    )
    return TiingoTransformResult(bars, actions, provenance, _TIINGO_TRANSFORM_ATTESTATION)
