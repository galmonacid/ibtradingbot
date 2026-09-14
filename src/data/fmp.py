"""Immutable, resumable acquisition for supplemental FMP validation extracts."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol


class FmpAcquisitionError(RuntimeError):
    """Raised when supplemental FMP acquisition cannot complete safely."""


class FmpTransport(Protocol):
    def get_json(self, endpoint: str, parameters: Mapping[str, str], token: str) -> object: ...


@dataclass(frozen=True)
class UrlLibFmpTransport:
    base_url: str = "https://financialmodelingprep.com/stable"
    timeout_seconds: float = 30.0

    def get_json(self, endpoint: str, parameters: Mapping[str, str], token: str) -> object:
        query = urllib.parse.urlencode(sorted({**parameters, "apikey": token}.items()))
        url = f"{self.base_url.rstrip('/')}/{endpoint}?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "momentum-ml-bot/0.2"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


_ENDPOINTS = {"historical-price-eod/full", "dividends", "delisted-companies"}


@dataclass(frozen=True, order=True)
class FmpRequest:
    endpoint: str
    security_id: str
    provider_symbol: str
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class FmpAcquisitionResult:
    manifest_path: Path
    successful: int
    failed: int
    resumed: int


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def fmp_request_id(request: FmpRequest) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "endpoint": request.endpoint,
                "security_id": request.security_id,
                "provider_symbol": request.provider_symbol,
                "start": request.start.isoformat() if request.start else None,
                "end": request.end.isoformat() if request.end else None,
            }
        )
    ).hexdigest()[:20]


def _safe_error(error: Exception, token: str) -> str:
    message = " ".join(str(error).replace(token, "[REDACTED]").split())
    return f"{type(error).__name__}: {message}"[:500]


def _payload(value: object) -> list[dict[str, Any]]:
    rows: object = value
    if isinstance(value, dict) and set(value) == {"data"}:
        rows = value["data"]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise FmpAcquisitionError("FMP returned a malformed payload")
    return [dict(row) for row in rows]


def acquire_fmp_extracts(
    requests: tuple[FmpRequest, ...],
    output_directory: Path,
    *,
    token: str,
    transport: FmpTransport,
    plan: str,
    api_version: str,
    licence: str,
    retrieved_at: datetime | None = None,
    minimum_interval_seconds: float = 0.0,
    maximum_attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> FmpAcquisitionResult:
    """Acquire exact supplemental endpoints with immutable raw files and checkpoints."""
    if not token.strip():
        raise FmpAcquisitionError("a non-blank FMP token is required for acquisition")
    if not plan.strip() or not api_version.strip() or not licence.strip():
        raise FmpAcquisitionError("FMP plan, API version, and licence/terms must be recorded")
    if not requests or {row.endpoint for row in requests} != _ENDPOINTS:
        raise FmpAcquisitionError("FMP plan must include all required supplemental endpoints")
    if maximum_attempts < 1 or minimum_interval_seconds < 0:
        raise FmpAcquisitionError("retry and throttle settings are invalid")
    when = retrieved_at or datetime.now(UTC)
    if when.tzinfo is None or when.utcoffset() is None:
        raise FmpAcquisitionError("retrieved_at must be timezone-aware")

    raw_directory = output_directory / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "fmp_manifest.json"
    prior_successes: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        try:
            prior: object = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FmpAcquisitionError("existing FMP manifest is invalid") from error
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
            not isinstance(prior, dict)
            or set(prior) != required
            or prior.get("schema_version") != "fmp-extract-manifest-v1"
            or prior.get("provider") != "FMP"
            or prior.get("plan") != plan
            or prior.get("api_version") != api_version
            or prior.get("licence") != licence
        ):
            raise FmpAcquisitionError("existing FMP manifest is incompatible")
        prior_when = datetime.fromisoformat(str(prior["retrieved_at"]))
        if retrieved_at is not None and prior_when != when.astimezone(UTC):
            raise FmpAcquisitionError("existing FMP manifest has a different retrieval timestamp")
        when = prior_when
        rows = prior.get("requests")
        if not isinstance(rows, list):
            raise FmpAcquisitionError("existing FMP request records are invalid")
        prior_successes = {
            str(row.get("request_id")): row
            for row in rows
            if isinstance(row, dict) and row.get("status") == "success"
        }

    records: list[dict[str, Any]] = []
    successful = failed = resumed = 0
    seen: set[str] = set()

    def checkpoint() -> None:
        manifest = {
            "schema_version": "fmp-extract-manifest-v1",
            "provider": "FMP",
            "plan": plan,
            "api_version": api_version,
            "licence": licence,
            "retrieved_at": when.astimezone(UTC).isoformat(),
            "requests": records,
            "complete": len(records) == len(requests)
            and all(row["status"] == "success" for row in records),
            "deployment_admissible": False,
            "paper_execution_permitted": False,
        }
        temporary = manifest_path.with_name(f".{manifest_path.name}.tmp")
        temporary.write_bytes(_canonical_json(manifest))
        temporary.replace(manifest_path)

    checkpoint()
    for request in sorted(requests):
        if request.endpoint not in _ENDPOINTS or not request.security_id.strip():
            raise FmpAcquisitionError("FMP request identity or endpoint is invalid")
        if request.endpoint != "delisted-companies" and not request.provider_symbol.strip():
            raise FmpAcquisitionError("symbol-scoped FMP request lacks a provider symbol")
        if (request.start is None) != (request.end is None) or (
            request.start is not None and request.end is not None and request.start > request.end
        ):
            raise FmpAcquisitionError("FMP request date bounds are invalid")
        identifier = fmp_request_id(request)
        if identifier in seen:
            raise FmpAcquisitionError("duplicate FMP request")
        seen.add(identifier)
        parameters: dict[str, str] = {}
        if request.provider_symbol:
            parameters["symbol"] = request.provider_symbol
        if request.start is not None and request.end is not None:
            parameters.update({"from": request.start.isoformat(), "to": request.end.isoformat()})
        common: dict[str, Any] = {
            "request_id": identifier,
            "endpoint": request.endpoint,
            "security_id": request.security_id,
            "provider_symbol": request.provider_symbol,
            "parameters": parameters,
        }
        raw_path = raw_directory / f"{identifier}.json"
        if raw_path.exists():
            raw = raw_path.read_bytes()
            prior_record = prior_successes.get(identifier)
            digest = hashlib.sha256(raw).hexdigest()
            if prior_record is None or prior_record.get("raw_sha256") != digest:
                raise FmpAcquisitionError("existing FMP extract is not bound to its prior manifest")
            try:
                existing_rows = _payload(json.loads(raw))
            except (json.JSONDecodeError, FmpAcquisitionError) as error:
                raise FmpAcquisitionError("existing immutable FMP extract is invalid") from error
            records.append(
                {
                    **common,
                    "status": "success",
                    "resumed": True,
                    "raw_path": str(raw_path.relative_to(output_directory)),
                    "raw_sha256": digest,
                    "rows": len(existing_rows),
                }
            )
            successful += 1
            resumed += 1
            checkpoint()
            continue
        payload_rows: list[dict[str, Any]] | None = None
        error_message = ""
        for attempt in range(1, maximum_attempts + 1):
            try:
                payload_rows = _payload(transport.get_json(request.endpoint, parameters, token))
                break
            except (OSError, TimeoutError, ValueError, FmpAcquisitionError) as error:
                error_message = _safe_error(error, token)
                if attempt < maximum_attempts:
                    sleeper(minimum_interval_seconds)
        if payload_rows is None:
            records.append(
                {**common, "status": "failed", "attempts": maximum_attempts, "error": error_message}
            )
            failed += 1
        else:
            raw = _canonical_json(payload_rows)
            temporary = raw_path.with_name(f".{raw_path.name}.tmp")
            temporary.write_bytes(raw)
            temporary.replace(raw_path)
            records.append(
                {
                    **common,
                    "status": "success",
                    "resumed": False,
                    "raw_path": str(raw_path.relative_to(output_directory)),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "rows": len(payload_rows),
                }
            )
            successful += 1
        checkpoint()
        sleeper(minimum_interval_seconds)
    return FmpAcquisitionResult(manifest_path, successful, failed, resumed)
