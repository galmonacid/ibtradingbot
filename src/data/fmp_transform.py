"""Verify immutable FMP extracts and transform them into supplemental observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from src.data.canonical_historical import CanonicalSourceProvenance
from src.data.fmp import FmpRequest, fmp_request_id
from src.data.fmp_reconciliation import (
    FmpDelistingObservation,
    FmpDividendObservation,
    FmpPriceObservation,
)
from src.data.trusted_historical import SecurityIdentityInterval


class FmpTransformError(ValueError):
    """Raised when FMP provenance or payloads cannot be trusted."""


_FMP_TRANSFORM_ATTESTATION = object()


@dataclass(frozen=True)
class FmpTransformResult:
    prices: tuple[FmpPriceObservation, ...]
    dividends: tuple[FmpDividendObservation, ...]
    delistings: tuple[FmpDelistingObservation, ...]
    provenance: CanonicalSourceProvenance
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _FMP_TRANSFORM_ATTESTATION:
            raise FmpTransformError("FMP source results must be issued by the transformer")


def _day(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise FmpTransformError(f"FMP {field} must be a date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise FmpTransformError(f"FMP {field} is invalid") from error
    if parsed.isoformat() != value:
        raise FmpTransformError(f"FMP {field} must use YYYY-MM-DD")
    return parsed


def _number(row: dict[str, Any], field: str, *, nonnegative: bool = False) -> float:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FmpTransformError(f"FMP {field} must be numeric")
    result = float(value)
    if result < 0 if nonnegative else result <= 0:
        raise FmpTransformError(f"FMP {field} has an invalid value")
    return result


def _delisted_identity(
    symbol: str, day: date, identities: tuple[SecurityIdentityInterval, ...]
) -> str:
    matches = {
        row.security_id
        for row in identities
        if row.symbol == symbol
        and row.effective_from <= day
        and (row.effective_to is None or day <= row.effective_to)
    }
    if len(matches) != 1:
        raise FmpTransformError("FMP delisting does not map to one dated identity")
    return next(iter(matches))


def transform_fmp_manifest(
    manifest_path: Path,
    extract_root: Path,
    *,
    identities: tuple[SecurityIdentityInterval, ...],
) -> FmpTransformResult:
    """Verify every complete request and retain only the three documented QA routes."""
    try:
        manifest_bytes = manifest_path.read_bytes()
        payload: object = json.loads(manifest_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise FmpTransformError("FMP manifest must be readable JSON") from error
    required = {
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
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or payload.get("schema_version") != "fmp-extract-manifest-v1"
        or payload.get("provider") != "FMP"
        or payload.get("complete") is not True
        or payload.get("deployment_admissible") is not False
        or payload.get("paper_execution_permitted") is not False
    ):
        raise FmpTransformError("FMP manifest schema, completeness, or safety flags are invalid")
    plan = payload.get("plan")
    api_version = payload.get("api_version")
    licence = payload.get("licence")
    try:
        retrieved_at = datetime.fromisoformat(str(payload["retrieved_at"]))
    except ValueError as error:
        raise FmpTransformError("FMP retrieval timestamp is invalid") from error
    if (
        not all(isinstance(value, str) and value.strip() for value in (plan, api_version, licence))
        or retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() is None
    ):
        raise FmpTransformError("FMP provider provenance is incomplete")
    requests = payload.get("requests")
    if not isinstance(requests, list) or not requests:
        raise FmpTransformError("FMP manifest has no requests")
    root = extract_root.resolve()
    prices: list[FmpPriceObservation] = []
    dividends: list[FmpDividendObservation] = []
    delistings: list[FmpDelistingObservation] = []
    parameter_records: list[dict[str, object]] = []
    endpoints: set[str] = set()
    seen_requests: set[str] = set()
    for request in requests:
        fields = {
            "request_id",
            "endpoint",
            "security_id",
            "provider_symbol",
            "parameters",
            "status",
            "resumed",
            "raw_path",
            "raw_sha256",
            "rows",
        }
        if (
            not isinstance(request, dict)
            or set(request) != fields
            or request.get("status") != "success"
        ):
            raise FmpTransformError("FMP manifest contains a non-success request")
        endpoint = request.get("endpoint")
        request_id = request.get("request_id")
        security_id = request.get("security_id")
        symbol = request.get("provider_symbol")
        parameters = request.get("parameters")
        relative = request.get("raw_path")
        digest = request.get("raw_sha256")
        if (
            endpoint not in {"historical-price-eod/full", "dividends", "delisted-companies"}
            or not isinstance(request_id, str)
            or not isinstance(security_id, str)
            or not security_id
            or not isinstance(symbol, str)
            or not isinstance(parameters, dict)
            or not isinstance(relative, str)
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise FmpTransformError("FMP request identity or provenance is invalid")
        endpoints.add(endpoint)
        if request_id in seen_requests:
            raise FmpTransformError("duplicate FMP request record")
        seen_requests.add(request_id)
        expected_parameters: dict[str, str]
        if endpoint == "delisted-companies":
            expected_parameters = {}
            start = end = None
            if symbol or security_id != "GLOBAL":
                raise FmpTransformError("global FMP delisting request identity is invalid")
        else:
            if set(parameters) != {"symbol", "from", "to"} or parameters.get("symbol") != symbol:
                raise FmpTransformError("FMP request parameters are not canonical")
            try:
                start = date.fromisoformat(str(parameters["from"]))
                end = date.fromisoformat(str(parameters["to"]))
            except ValueError as error:
                raise FmpTransformError("FMP request date bounds are invalid") from error
            if start > end:
                raise FmpTransformError("FMP request date bounds are reversed")
            expected_parameters = {
                "symbol": symbol,
                "from": start.isoformat(),
                "to": end.isoformat(),
            }
            if parameters != expected_parameters:
                raise FmpTransformError("FMP request parameters are not canonical")
        if request_id != fmp_request_id(FmpRequest(endpoint, security_id, symbol, start, end)):
            raise FmpTransformError("FMP request ID does not match its identity and bounds")
        parameter_records.append(
            {"endpoint": endpoint, "security_id": security_id, "parameters": parameters}
        )
        pure = PurePosixPath(relative)
        path = (root / relative).resolve()
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or not path.is_relative_to(root)
            or not path.is_file()
        ):
            raise FmpTransformError("FMP raw path is missing or outside its extract root")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise FmpTransformError("FMP raw extract hash mismatch")
        try:
            rows: object = json.loads(raw)
        except json.JSONDecodeError as error:
            raise FmpTransformError("FMP raw extract is invalid JSON") from error
        if not isinstance(rows, list) or request.get("rows") != len(rows):
            raise FmpTransformError("FMP raw rows contradict the manifest")
        previous_date: date | None = None
        seen_delistings: set[tuple[str, date]] = set()
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                raise FmpTransformError("FMP raw row is malformed")
            row = raw_row
            if endpoint == "historical-price-eod/full":
                row_date = _day(row.get("date"), "date")
                assert start is not None and end is not None
                if not start <= row_date <= end:
                    raise FmpTransformError("FMP price row is outside request bounds")
                if previous_date is not None and row_date <= previous_date:
                    raise FmpTransformError("FMP price rows must be chronological and unique")
                previous_date = row_date
                volume = _number(row, "volume", nonnegative=True)
                if not volume.is_integer():
                    raise FmpTransformError("FMP volume must be integral")
                prices.append(
                    FmpPriceObservation(
                        security_id,
                        row_date,
                        _number(row, "open"),
                        _number(row, "high"),
                        _number(row, "low"),
                        _number(row, "close"),
                        int(volume),
                    )
                )
            elif endpoint == "dividends":
                row_date = _day(row.get("date"), "date")
                assert start is not None and end is not None
                if not start <= row_date <= end:
                    raise FmpTransformError("FMP dividend row is outside request bounds")
                if previous_date is not None and row_date <= previous_date:
                    raise FmpTransformError("FMP dividend rows must be chronological and unique")
                previous_date = row_date
                dividends.append(
                    FmpDividendObservation(
                        security_id,
                        row_date,
                        _number(row, "dividend", nonnegative=True),
                    )
                )
            else:
                row_symbol = row.get("symbol")
                exchange = row.get("exchange")
                if not isinstance(row_symbol, str) or not isinstance(exchange, str):
                    raise FmpTransformError("FMP delisting identity fields are invalid")
                delisted_on = _day(row.get("delistedDate"), "delistedDate")
                delisting_key = (row_symbol, delisted_on)
                if delisting_key in seen_delistings:
                    raise FmpTransformError("duplicate FMP delisting row")
                seen_delistings.add(delisting_key)
                delistings.append(
                    FmpDelistingObservation(
                        _delisted_identity(row_symbol, delisted_on, identities),
                        delisted_on,
                        exchange,
                    )
                )
    if endpoints != {"historical-price-eod/full", "dividends", "delisted-companies"}:
        raise FmpTransformError("FMP manifest omits a required supplemental endpoint")
    parameters_sha = hashlib.sha256(
        json.dumps(parameter_records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    provenance = CanonicalSourceProvenance(
        "FMP",
        "provider",
        hashlib.sha256(manifest_bytes).hexdigest(),
        retrieved_at.isoformat(),
        str(licence),
        plan=str(plan),
        api_version=str(api_version),
        request_parameters_sha256=parameters_sha,
    )
    return FmpTransformResult(
        tuple(sorted(prices)),
        tuple(sorted(dividends)),
        tuple(sorted(delistings)),
        provenance,
        _FMP_TRANSFORM_ATTESTATION,
    )
