"""Resumable, immutable Tiingo extract acquisition.

This module acquires raw provider payloads only.  Canonical transformation and
eligibility certification are separate stages, so analytics never calls Tiingo.
"""

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


class TiingoAcquisitionError(RuntimeError):
    """Raised when an immutable Tiingo acquisition cannot be completed safely."""


class TiingoTransport(Protocol):
    """Injectable HTTP boundary used by production and deterministic tests."""

    def get_json(self, endpoint: str, parameters: Mapping[str, str], token: str) -> object: ...


@dataclass(frozen=True)
class UrlLibTiingoTransport:
    """Production HTTP transport with the credential confined to a request header."""

    base_url: str = "https://api.tiingo.com"
    timeout_seconds: float = 30.0

    def get_json(self, endpoint: str, parameters: Mapping[str, str], token: str) -> object:
        query = urllib.parse.urlencode(sorted(parameters.items()))
        url = f"{self.base_url.rstrip('/')}/{endpoint}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Token {token}",
                "User-Agent": "momentum-ml-bot/0.2",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class TiingoRequest:
    security_id: str
    provider_symbol: str
    start: date
    end: date


@dataclass(frozen=True)
class TiingoAcquisitionResult:
    manifest_path: Path
    successful: int
    failed: int
    resumed: int


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _safe_error(error: Exception, token: str) -> str:
    message = " ".join(str(error).replace(token, "[REDACTED]").split())
    return f"{type(error).__name__}: {message}"[:500]


def _request_id(request: TiingoRequest) -> str:
    content = {
        "end": request.end.isoformat(),
        "provider_symbol": request.provider_symbol,
        "security_id": request.security_id,
        "start": request.start.isoformat(),
    }
    return hashlib.sha256(_canonical_json(content)).hexdigest()[:20]


def _safe_symbol(value: str, field: str) -> str:
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
    if not value or any(character not in allowed for character in value):
        raise TiingoAcquisitionError(f"{field} is not a canonical provider symbol")
    return value


def _validate_payload(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not payload:
        raise TiingoAcquisitionError("Tiingo returned an empty or malformed payload")
    rows: list[dict[str, Any]] = []
    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjOpen",
        "adjHigh",
        "adjLow",
        "adjClose",
        "adjVolume",
        "divCash",
        "splitFactor",
    }
    for item in payload:
        if not isinstance(item, dict) or not required.issubset(item):
            raise TiingoAcquisitionError("Tiingo payload lacks required daily-price fields")
        rows.append(dict(item))
    return rows


def acquire_tiingo_extracts(
    requests: tuple[TiingoRequest, ...],
    output_directory: Path,
    *,
    token: str,
    transport: TiingoTransport,
    plan: str,
    api_version: str,
    licence: str,
    retrieved_at: datetime | None = None,
    minimum_interval_seconds: float = 0.0,
    maximum_attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> TiingoAcquisitionResult:
    """Acquire immutable raw JSON, resuming verified successes deterministically.

    Tokens are used only at the transport boundary and are never serialized.
    Every request has a manifest record, including terminal failures.
    """
    if not token.strip():
        raise TiingoAcquisitionError("a non-blank Tiingo token is required for acquisition")
    if not plan.strip() or not api_version.strip() or not licence.strip():
        raise TiingoAcquisitionError("Tiingo plan, API version, and licence/terms must be recorded")
    if maximum_attempts < 1 or minimum_interval_seconds < 0:
        raise TiingoAcquisitionError("retry and throttle settings are invalid")
    if not requests:
        raise TiingoAcquisitionError("at least one Tiingo request is required")
    when = retrieved_at or datetime.now(UTC)
    if when.tzinfo is None or when.utcoffset() is None:
        raise TiingoAcquisitionError("retrieved_at must be timezone-aware")

    raw_directory = output_directory / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "tiingo_manifest.json"
    prior_successes: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        try:
            prior: object = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TiingoAcquisitionError("existing Tiingo manifest is invalid") from error
        if (
            not isinstance(prior, dict)
            or set(prior)
            != {
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
            or prior.get("schema_version") != "tiingo-extract-manifest-v1"
        ):
            raise TiingoAcquisitionError("existing Tiingo manifest schema is invalid")
        if (
            prior.get("provider") != "Tiingo"
            or prior.get("plan") != plan
            or prior.get("api_version") != api_version
            or prior.get("licence") != licence
        ):
            raise TiingoAcquisitionError(
                "existing Tiingo manifest is incompatible with requested plan"
            )
        try:
            prior_when = datetime.fromisoformat(str(prior["retrieved_at"]))
        except ValueError as error:
            raise TiingoAcquisitionError(
                "existing Tiingo retrieval timestamp is invalid"
            ) from error
        if retrieved_at is not None and prior_when != when.astimezone(UTC):
            raise TiingoAcquisitionError(
                "existing Tiingo manifest has a different retrieval timestamp"
            )
        when = prior_when
        prior_rows = prior.get("requests")
        if not isinstance(prior_rows, list):
            raise TiingoAcquisitionError("existing Tiingo manifest requests are invalid")
        prior_successes = {
            str(row.get("request_id")): row
            for row in prior_rows
            if isinstance(row, dict) and row.get("status") == "success"
        }
    records: list[dict[str, Any]] = []
    successful = failed = resumed = 0
    seen: set[str] = set()

    def checkpoint() -> None:
        manifest = {
            "schema_version": "tiingo-extract-manifest-v1",
            "provider": "Tiingo",
            "plan": plan,
            "api_version": api_version,
            "licence": licence,
            "retrieved_at": when.astimezone(UTC).isoformat(),
            "requests": records,
            "complete": len(records) == len(requests)
            and all(r["status"] == "success" for r in records),
            "deployment_admissible": False,
            "paper_execution_permitted": False,
        }
        _atomic_write(manifest_path, _canonical_json(manifest))

    checkpoint()
    for request in sorted(requests, key=lambda item: (item.security_id, item.start, item.end)):
        if request.start > request.end:
            raise TiingoAcquisitionError("Tiingo request start must not exceed end")
        _safe_symbol(request.provider_symbol, "provider_symbol")
        if not request.security_id.strip():
            raise TiingoAcquisitionError("security_id must be non-blank")
        identifier = _request_id(request)
        if identifier in seen:
            raise TiingoAcquisitionError("duplicate Tiingo request")
        seen.add(identifier)
        raw_path = raw_directory / f"{identifier}.json"
        parameters = {
            "startDate": request.start.isoformat(),
            "endDate": request.end.isoformat(),
            "resampleFreq": "daily",
        }
        common: dict[str, Any] = {
            "request_id": identifier,
            "security_id": request.security_id,
            "provider_symbol": request.provider_symbol,
            "endpoint": f"tiingo/daily/{request.provider_symbol}/prices",
            "parameters": parameters,
        }
        if raw_path.exists():
            payload_bytes = raw_path.read_bytes()
            prior_record = prior_successes.get(identifier)
            digest = hashlib.sha256(payload_bytes).hexdigest()
            if prior_record is None:
                raise TiingoAcquisitionError(
                    f"existing extract {raw_path.name} is not bound to a prior manifest"
                )
            if prior_record is not None and prior_record.get("raw_sha256") != digest:
                raise TiingoAcquisitionError(f"existing extract {raw_path.name} hash changed")
            try:
                _validate_payload(json.loads(payload_bytes))
            except (json.JSONDecodeError, TiingoAcquisitionError) as error:
                raise TiingoAcquisitionError(
                    f"existing immutable extract {raw_path.name} is invalid"
                ) from error
            records.append(
                {
                    **common,
                    "status": "success",
                    "resumed": True,
                    "raw_path": str(raw_path.relative_to(output_directory)),
                    "raw_sha256": hashlib.sha256(payload_bytes).hexdigest(),
                    "rows": len(json.loads(payload_bytes)),
                }
            )
            successful += 1
            resumed += 1
            checkpoint()
            continue

        error_message = ""
        payload_rows: list[dict[str, Any]] | None = None
        for attempt in range(1, maximum_attempts + 1):
            try:
                payload_rows = _validate_payload(
                    transport.get_json(common["endpoint"], parameters, token)
                )
                break
            except (OSError, TimeoutError, ValueError, TiingoAcquisitionError) as error:
                error_message = _safe_error(error, token)
                if attempt < maximum_attempts:
                    sleeper(minimum_interval_seconds)
        if payload_rows is None:
            records.append(
                {**common, "status": "failed", "attempts": maximum_attempts, "error": error_message}
            )
            failed += 1
        else:
            payload_bytes = _canonical_json(payload_rows)
            _atomic_write(raw_path, payload_bytes)
            records.append(
                {
                    **common,
                    "status": "success",
                    "resumed": False,
                    "raw_path": str(raw_path.relative_to(output_directory)),
                    "raw_sha256": hashlib.sha256(payload_bytes).hexdigest(),
                    "rows": len(payload_rows),
                }
            )
            successful += 1
        checkpoint()
        sleeper(minimum_interval_seconds)
    checkpoint()
    return TiingoAcquisitionResult(manifest_path, successful, failed, resumed)
