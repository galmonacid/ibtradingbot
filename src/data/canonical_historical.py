"""Explicit canonical Parquet schemas for trusted historical datasets."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.data.trusted_historical import (
    DatedSecurityIdentity,
    SecurityIdentityInterval,
    SecurityMembershipInterval,
    TrustedHistoricalError,
)


class CanonicalHistoricalError(ValueError):
    """Raised when canonical historical data is unsafe or cannot be written."""


@dataclass(frozen=True, order=True)
class CanonicalDailyBar:
    security_id: str
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    adjusted_open: float
    adjusted_high: float
    adjusted_low: float
    adjusted_volume: int


@dataclass(frozen=True, order=True)
class CanonicalCorporateAction:
    security_id: str
    symbol: str
    action_date: date
    action_type: str
    value: float


@dataclass(frozen=True)
class CanonicalFile:
    path: str
    sha256: str
    rows: int
    schema_version: str
    minimum_date: str | None
    maximum_date: str | None


@dataclass(frozen=True)
class CanonicalDataset:
    output_directory: Path
    files: tuple[CanonicalFile, ...]
    manifest_path: Path


@dataclass(frozen=True, order=True)
class CanonicalSourceProvenance:
    source_name: str
    source_type: str
    manifest_sha256: str
    retrieved_at: str
    licence: str
    repository_url: str | None = None
    commit_sha: str | None = None
    plan: str | None = None
    api_version: str | None = None
    request_parameters_sha256: str | None = None


def _sha256(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_provenance(rows: tuple[CanonicalSourceProvenance, ...]) -> None:
    if not rows or len({row.source_name for row in rows}) != len(rows):
        raise CanonicalHistoricalError("source provenance must be non-empty and uniquely named")
    for row in rows:
        try:
            retrieved_at = datetime.fromisoformat(row.retrieved_at)
        except ValueError as error:
            raise CanonicalHistoricalError("source retrieval timestamp is invalid") from error
        if (
            not row.source_name.strip()
            or not row.licence.strip()
            or retrieved_at.tzinfo is None
            or retrieved_at.utcoffset() is None
            or not _sha256(row.manifest_sha256)
        ):
            raise CanonicalHistoricalError("source provenance is incomplete")
        if row.source_type == "git":
            if (
                not row.repository_url
                or row.commit_sha is None
                or len(row.commit_sha) != 40
                or any(character not in "0123456789abcdef" for character in row.commit_sha)
                or any((row.plan, row.api_version, row.request_parameters_sha256))
            ):
                raise CanonicalHistoricalError("Git source provenance is invalid")
        elif row.source_type == "provider":
            if (
                row.repository_url is not None
                or row.commit_sha is not None
                or not row.plan
                or not row.api_version
                or not _sha256(row.request_parameters_sha256)
            ):
                raise CanonicalHistoricalError("provider source provenance is invalid")
        else:
            raise CanonicalHistoricalError("unsupported source provenance type")


def _arrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as error:
        raise CanonicalHistoricalError(
            "pyarrow is required; install the historical-data extra"
        ) from error
    return pa, pq


def _validate_bars(bars: tuple[CanonicalDailyBar, ...]) -> None:
    keys: set[tuple[str, date]] = set()
    for bar in bars:
        if not bar.security_id or not bar.symbol or bar.symbol != bar.symbol.upper():
            raise CanonicalHistoricalError("bar identity and symbol must be canonical")
        values = (
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.adjusted_close,
            bar.adjusted_open,
            bar.adjusted_high,
            bar.adjusted_low,
        )
        if any(not math.isfinite(value) or value <= 0 for value in values) or bar.volume < 0:
            raise CanonicalHistoricalError(
                "bar prices must be finite/positive and volume nonnegative"
            )
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            raise CanonicalHistoricalError("bar has impossible OHLC relationships")
        if (
            bar.adjusted_low > min(bar.adjusted_open, bar.adjusted_close)
            or bar.adjusted_high < max(bar.adjusted_open, bar.adjusted_close)
            or bar.adjusted_volume < 0
        ):
            raise CanonicalHistoricalError("bar has impossible adjusted OHLCV relationships")
        key = (bar.security_id, bar.date)
        if key in keys:
            raise CanonicalHistoricalError("duplicate security/date bar")
        keys.add(key)


def _validate_actions(actions: tuple[CanonicalCorporateAction, ...]) -> None:
    keys: set[tuple[str, date, str]] = set()
    for action in actions:
        if not action.security_id or not action.symbol or action.symbol != action.symbol.upper():
            raise CanonicalHistoricalError("corporate action identity and symbol must be canonical")
        if action.action_type not in {"dividend", "split", "delisting"}:
            raise CanonicalHistoricalError("unsupported corporate action type")
        if not math.isfinite(action.value) or action.value < 0:
            raise CanonicalHistoricalError("corporate action value must be finite and nonnegative")
        if action.action_type == "split" and action.value <= 0:
            raise CanonicalHistoricalError("split factor must be positive")
        key = (action.security_id, action.action_date, action.action_type)
        if key in keys:
            raise CanonicalHistoricalError("duplicate corporate action")
        keys.add(key)


def _rows(values: tuple[Any, ...]) -> list[dict[str, object]]:
    return [asdict(value) for value in values]


def _contains(interval: SecurityIdentityInterval, day: date) -> bool:
    return interval.effective_from <= day and (
        interval.effective_to is None or day < interval.effective_to
    )


def _validate_relationships(
    bars: tuple[CanonicalDailyBar, ...],
    identities: tuple[SecurityIdentityInterval, ...],
    memberships: tuple[SecurityMembershipInterval, ...],
    actions: tuple[CanonicalCorporateAction, ...],
) -> None:
    try:
        DatedSecurityIdentity(identities)
    except TrustedHistoricalError as error:
        raise CanonicalHistoricalError(f"invalid security identity intervals: {error}") from error
    identity_by_security: dict[str, list[SecurityIdentityInterval]] = {}
    for identity in identities:
        identity_by_security.setdefault(identity.security_id, []).append(identity)
    versions = {membership.source_version for membership in memberships}
    if len(versions) != 1 or "" in versions:
        raise CanonicalHistoricalError("memberships must share one non-blank source version")
    ordered_memberships = sorted(
        memberships, key=lambda item: (item.security_id, item.effective_from)
    )
    previous_by_security: dict[str, SecurityMembershipInterval] = {}
    membership_keys: set[tuple[str, date, date | None]] = set()
    for membership in ordered_memberships:
        if (
            not membership.security_id
            or membership.effective_to is not None
            and membership.effective_to <= membership.effective_from
        ):
            raise CanonicalHistoricalError("membership intervals must be valid and identified")
        key = (membership.security_id, membership.effective_from, membership.effective_to)
        if key in membership_keys:
            raise CanonicalHistoricalError("duplicate membership interval")
        membership_keys.add(key)
        previous = previous_by_security.get(membership.security_id)
        if previous is not None and (
            previous.effective_to is None or membership.effective_from < previous.effective_to
        ):
            raise CanonicalHistoricalError("overlapping membership intervals")
        previous_by_security[membership.security_id] = membership
        identity_rows = sorted(
            identity_by_security.get(membership.security_id, ()),
            key=lambda item: item.effective_from,
        )
        if not identity_rows:
            raise CanonicalHistoricalError("membership references an unknown security identity")
        cursor = membership.effective_from
        for identity in identity_rows:
            if identity.effective_to is not None and identity.effective_to <= cursor:
                continue
            if identity.effective_from > cursor:
                break
            if identity.effective_to is None:
                cursor = membership.effective_to or date.max
                break
            cursor = max(cursor, identity.effective_to)
            if membership.effective_to is not None and cursor >= membership.effective_to:
                break
        target = membership.effective_to or date.max
        if cursor < target:
            raise CanonicalHistoricalError(
                "membership is not covered by continuous identity history"
            )

    def matching_identity(security_id: str, symbol: str, day: date) -> bool:
        return any(
            identity.symbol == symbol and _contains(identity, day)
            for identity in identity_by_security.get(security_id, ())
        )

    for bar in bars:
        if not matching_identity(bar.security_id, bar.symbol, bar.date):
            raise CanonicalHistoricalError("bar is outside its dated security identity")
    for action in actions:
        active = matching_identity(action.security_id, action.symbol, action.action_date)
        ends_on_action = action.action_type == "delisting" and any(
            identity.symbol == action.symbol and identity.effective_to == action.action_date
            for identity in identity_by_security.get(action.security_id, ())
        )
        if not active and not ends_on_action:
            raise CanonicalHistoricalError(
                "corporate action is outside its dated security identity"
            )


def _schemas(pa: Any) -> dict[str, Any]:
    string = pa.string()
    day = pa.date32()
    return {
        "daily-bars-v1": pa.schema(
            [
                ("security_id", string),
                ("symbol", string),
                ("date", day),
                ("open", pa.float64()),
                ("high", pa.float64()),
                ("low", pa.float64()),
                ("close", pa.float64()),
                ("adjusted_close", pa.float64()),
                ("volume", pa.int64()),
                ("adjusted_open", pa.float64()),
                ("adjusted_high", pa.float64()),
                ("adjusted_low", pa.float64()),
                ("adjusted_volume", pa.int64()),
            ]
        ),
        "security-master-v1": pa.schema(
            [
                ("security_id", string),
                ("symbol", string),
                ("effective_from", day),
                ("effective_to", day),
            ]
        ),
        "membership-v1": pa.schema(
            [
                ("source_version", string),
                ("security_id", string),
                ("effective_from", day),
                ("effective_to", day),
            ]
        ),
        "corporate-actions-v1": pa.schema(
            [
                ("security_id", string),
                ("symbol", string),
                ("action_date", day),
                ("action_type", string),
                ("value", pa.float64()),
            ]
        ),
    }


def write_canonical_parquet(
    output_directory: Path,
    *,
    bars: tuple[CanonicalDailyBar, ...],
    identities: tuple[SecurityIdentityInterval, ...],
    memberships: tuple[SecurityMembershipInterval, ...],
    actions: tuple[CanonicalCorporateAction, ...],
    source_provenance: tuple[CanonicalSourceProvenance, ...],
    transformation_version: str,
) -> CanonicalDataset:
    """Write an immutable, deterministic set of canonical Parquet tables."""
    if output_directory.exists() and any(output_directory.iterdir()):
        raise CanonicalHistoricalError("canonical output directory must be new or empty")
    if not bars or not identities or not memberships or not transformation_version.strip():
        raise CanonicalHistoricalError("canonical dataset inputs and lineage must be non-empty")
    _validate_provenance(source_provenance)
    _validate_bars(bars)
    _validate_actions(actions)
    _validate_relationships(bars, identities, memberships, actions)
    pa, pq = _arrow()
    schemas = _schemas(pa)
    specifications = (
        ("daily_bars.parquet", tuple(sorted(bars)), "daily-bars-v1", "date"),
        (
            "security_master.parquet",
            tuple(sorted(identities)),
            "security-master-v1",
            "effective_from",
        ),
        ("membership.parquet", tuple(sorted(memberships)), "membership-v1", "effective_from"),
        (
            "corporate_actions.parquet",
            tuple(sorted(actions)),
            "corporate-actions-v1",
            "action_date",
        ),
    )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}.", dir=output_directory.parent)
    )
    try:
        files: list[CanonicalFile] = []
        for filename, records, schema_version, date_field in specifications:
            path = staging / filename
            table = pa.Table.from_pylist(_rows(records), schema=schemas[schema_version])
            pq.write_table(
                table, path, compression="zstd", use_dictionary=False, write_statistics=True
            )
            dates = [getattr(record, date_field) for record in records]
            files.append(
                CanonicalFile(
                    filename,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    len(records),
                    schema_version,
                    min(dates).isoformat() if dates else None,
                    max(dates).isoformat() if dates else None,
                )
            )
        manifest: dict[str, object] = {
            "schema_version": "canonical-historical-dataset-v2",
            "transformation_version": transformation_version,
            "source_provenance": [
                asdict(item)
                for item in sorted(source_provenance, key=lambda item: item.source_name)
            ],
            "files": [asdict(item) for item in files],
            "deployment_admissible": False,
            "paper_execution_permitted": False,
        }
        (staging / "canonical_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output_directory.exists():
            output_directory.rmdir()
        staging.replace(output_directory)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return CanonicalDataset(
        output_directory, tuple(files), output_directory / "canonical_manifest.json"
    )


def verify_canonical_parquet(manifest_path: Path) -> CanonicalDataset:
    """Re-read and fully verify a canonical dataset before analytics consumption."""
    try:
        payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CanonicalHistoricalError("canonical manifest must be readable JSON") from error
    required = {
        "schema_version",
        "transformation_version",
        "source_provenance",
        "files",
        "deployment_admissible",
        "paper_execution_permitted",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or payload.get("schema_version") != "canonical-historical-dataset-v2"
        or payload.get("deployment_admissible") is not False
        or payload.get("paper_execution_permitted") is not False
    ):
        raise CanonicalHistoricalError("canonical manifest schema or safety flags are invalid")
    transformation_version = payload.get("transformation_version")
    raw_provenance = payload.get("source_provenance")
    if not isinstance(transformation_version, str) or not transformation_version.strip():
        raise CanonicalHistoricalError("canonical transformation version is invalid")
    if not isinstance(raw_provenance, list):
        raise CanonicalHistoricalError("canonical source provenance is invalid")
    try:
        provenance = tuple(CanonicalSourceProvenance(**row) for row in raw_provenance)
    except (TypeError, ValueError) as error:
        raise CanonicalHistoricalError("canonical source provenance is invalid") from error
    _validate_provenance(provenance)
    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != 4:
        raise CanonicalHistoricalError("canonical manifest must list four files")
    pa, pq = _arrow()
    schemas = _schemas(pa)
    root = manifest_path.parent.resolve()
    expected_versions = {
        "daily_bars.parquet": "daily-bars-v1",
        "security_master.parquet": "security-master-v1",
        "membership.parquet": "membership-v1",
        "corporate_actions.parquet": "corporate-actions-v1",
    }
    verified_files: list[CanonicalFile] = []
    tables: dict[str, Any] = {}
    for raw_file in raw_files:
        if not isinstance(raw_file, dict) or set(raw_file) != {
            "path",
            "sha256",
            "rows",
            "schema_version",
            "minimum_date",
            "maximum_date",
        }:
            raise CanonicalHistoricalError("canonical file record has invalid fields")
        filename = raw_file.get("path")
        schema_version = raw_file.get("schema_version")
        if (
            not isinstance(filename, str)
            or expected_versions.get(filename) != schema_version
            or Path(filename).name != filename
        ):
            raise CanonicalHistoricalError("canonical file name or schema version is invalid")
        path = root / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != raw_file.get(
            "sha256"
        ):
            raise CanonicalHistoricalError(f"canonical file hash mismatch: {filename}")
        table = pq.read_table(path)
        if table.schema != schemas[str(schema_version)]:
            raise CanonicalHistoricalError(f"canonical Parquet schema mismatch: {filename}")
        if raw_file.get("rows") != table.num_rows:
            raise CanonicalHistoricalError(f"canonical row count mismatch: {filename}")
        tables[filename] = table
        verified_files.append(
            CanonicalFile(
                filename,
                str(raw_file["sha256"]),
                int(raw_file["rows"]),
                str(schema_version),
                raw_file.get("minimum_date")
                if isinstance(raw_file.get("minimum_date"), str)
                else None,
                raw_file.get("maximum_date")
                if isinstance(raw_file.get("maximum_date"), str)
                else None,
            )
        )
    if set(tables) != set(expected_versions):
        raise CanonicalHistoricalError("canonical manifest file set is incomplete")
    bars = tuple(CanonicalDailyBar(**row) for row in tables["daily_bars.parquet"].to_pylist())
    identities = tuple(
        SecurityIdentityInterval(**row) for row in tables["security_master.parquet"].to_pylist()
    )
    memberships = tuple(
        SecurityMembershipInterval(**row) for row in tables["membership.parquet"].to_pylist()
    )
    actions = tuple(
        CanonicalCorporateAction(**row) for row in tables["corporate_actions.parquet"].to_pylist()
    )
    _validate_bars(bars)
    _validate_actions(actions)
    _validate_relationships(bars, identities, memberships, actions)
    return CanonicalDataset(root, tuple(verified_files), manifest_path)
