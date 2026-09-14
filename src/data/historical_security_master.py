"""Canonical instrument metadata for long-horizon point-in-time universes."""

from __future__ import annotations

import csv
from pathlib import Path

from src.data.universe import UniverseSecurity

HISTORICAL_SECURITY_MASTER_COLUMNS = (
    "metadata_version",
    "symbol",
    "is_benchmark",
    "is_common_stock",
    "primary_listing_us",
    "is_otc",
    "is_leveraged_or_inverse_etf",
    "isa_eligible",
)


class HistoricalSecurityMasterError(ValueError):
    """Raised when historical instrument metadata is incomplete or inconsistent."""


def _flag(value: str, field: str, line_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise HistoricalSecurityMasterError(f"{field} must be true or false on line {line_number}")


def load_historical_security_master(
    path: Path,
    *,
    benchmark: str,
    expected_metadata_version: str | None = None,
) -> tuple[UniverseSecurity, ...]:
    """Load an uncapped historical security master with exactly one benchmark."""
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise HistoricalSecurityMasterError(
            f"cannot read historical security master {path}: {error}"
        ) from error
    securities: list[UniverseSecurity] = []
    with handle:
        reader = csv.DictReader(handle)
        if (
            reader.fieldnames is None
            or tuple(reader.fieldnames) != HISTORICAL_SECURITY_MASTER_COLUMNS
        ):
            raise HistoricalSecurityMasterError(
                "historical security master must use the exact canonical column order"
            )
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise HistoricalSecurityMasterError(f"malformed metadata row on line {line_number}")
            version = row["metadata_version"].strip()
            symbol = row["symbol"].strip()
            if not version:
                raise HistoricalSecurityMasterError(f"blank metadata_version on line {line_number}")
            if not symbol or symbol != symbol.upper():
                raise HistoricalSecurityMasterError(
                    f"symbol must be non-blank canonical uppercase on line {line_number}"
                )
            securities.append(
                UniverseSecurity(
                    version,
                    symbol,
                    _flag(row["is_benchmark"], "is_benchmark", line_number),
                    _flag(row["is_common_stock"], "is_common_stock", line_number),
                    _flag(row["primary_listing_us"], "primary_listing_us", line_number),
                    _flag(row["is_otc"], "is_otc", line_number),
                    _flag(
                        row["is_leveraged_or_inverse_etf"],
                        "is_leveraged_or_inverse_etf",
                        line_number,
                    ),
                    _flag(row["isa_eligible"], "isa_eligible", line_number),
                )
            )
    if not securities:
        raise HistoricalSecurityMasterError("historical security master contains no rows")
    if len({security.symbol for security in securities}) != len(securities):
        raise HistoricalSecurityMasterError("historical security master contains duplicate symbols")
    versions = {security.version for security in securities}
    if len(versions) != 1:
        raise HistoricalSecurityMasterError("metadata rows must share exactly one metadata_version")
    version = next(iter(versions))
    if expected_metadata_version is not None and version != expected_metadata_version:
        raise HistoricalSecurityMasterError("metadata_version does not match the expected version")
    benchmarks = [security for security in securities if security.is_benchmark]
    if len(benchmarks) != 1 or benchmarks[0].symbol != benchmark:
        raise HistoricalSecurityMasterError(
            "historical security master must contain exactly the configured benchmark"
        )
    return tuple(sorted(securities, key=lambda security: security.symbol))
