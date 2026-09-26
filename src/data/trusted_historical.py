"""Offline trust primitives for the Phase 3 historical-data producer.

This module deliberately performs no network access.  It verifies immutable source
snapshots, resolves dated tickers to stable security identities, and converts dated
membership snapshots into identity-based half-open intervals.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath


class TrustedHistoricalError(ValueError):
    """Raised when historical source evidence is incomplete or ambiguous."""


_SECRET_KEY_FRAGMENTS = ("api_key", "apikey", "authorization", "password", "secret", "token")
_VERIFIED_SOURCE_ATTESTATION = object()


def _contains_secret(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            any(fragment in str(key).strip().lower() for fragment in _SECRET_KEY_FRAGMENTS)
            or _contains_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


def _hex(value: object, *, length: int, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TrustedHistoricalError(f"{field} must be {length} lowercase hexadecimal characters")
    return value


@dataclass(frozen=True)
class VerifiedSourceFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class VerifiedSourceSnapshot:
    source_name: str
    repository_url: str
    commit_sha: str
    licence: str
    retrieved_at: datetime
    files: tuple[VerifiedSourceFile, ...]
    manifest_sha256: str
    checkout_verified: bool
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _VERIFIED_SOURCE_ATTESTATION:
            raise TrustedHistoricalError(
                "verified source snapshots must be issued by verify_source_snapshot"
            )


def verify_source_snapshot(manifest_path: Path, snapshot_root: Path) -> VerifiedSourceSnapshot:
    """Verify a source manifest and every immutable file it identifies."""
    try:
        manifest_bytes = manifest_path.read_bytes()
        payload: object = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TrustedHistoricalError(
            f"cannot read source manifest {manifest_path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise TrustedHistoricalError("source manifest must be a mapping")
    if _contains_secret(payload):
        raise TrustedHistoricalError("source manifest must not contain credentials or secrets")
    required = {
        "source_name",
        "repository_url",
        "commit_sha",
        "licence",
        "retrieved_at",
        "files",
    }
    if set(payload) != required:
        raise TrustedHistoricalError("source manifest must contain exactly the canonical fields")

    def text(field: str) -> str:
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise TrustedHistoricalError(f"{field} must be a non-blank string")
        return value.strip()

    commit_sha = _hex(payload["commit_sha"], length=40, field="commit_sha")
    timestamp = text("retrieved_at")
    try:
        retrieved_at = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise TrustedHistoricalError("retrieved_at must be ISO-8601") from error
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise TrustedHistoricalError("retrieved_at must be timezone-aware")
    rows = payload["files"]
    if not isinstance(rows, list) or not rows:
        raise TrustedHistoricalError("files must be a non-empty list")
    root = snapshot_root.resolve()
    verified: list[VerifiedSourceFile] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise TrustedHistoricalError(f"files[{index}] must contain path and sha256")
        relative = row["path"]
        if not isinstance(relative, str) or not relative:
            raise TrustedHistoricalError(f"files[{index}].path must be non-blank")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
            raise TrustedHistoricalError(f"files[{index}].path must be a canonical relative path")
        if relative in seen:
            raise TrustedHistoricalError("source manifest contains duplicate file paths")
        expected = _hex(row["sha256"], length=64, field=f"files[{index}].sha256")
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise TrustedHistoricalError(
                f"source file is missing or outside snapshot root: {relative}"
            )
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            raise TrustedHistoricalError(f"source file hash mismatch: {relative}")
        seen.add(relative)
        verified.append(VerifiedSourceFile(relative, expected))
    return VerifiedSourceSnapshot(
        text("source_name"),
        text("repository_url"),
        commit_sha,
        text("licence"),
        retrieved_at,
        tuple(sorted(verified, key=lambda item: item.path)),
        hashlib.sha256(manifest_bytes).hexdigest(),
        False,
        _VERIFIED_SOURCE_ATTESTATION,
    )


@dataclass(frozen=True, order=True)
class SecurityIdentityInterval:
    security_id: str
    symbol: str
    effective_from: date
    effective_to: date | None

    def __post_init__(self) -> None:
        if not self.security_id.strip():
            raise TrustedHistoricalError("security_id must be non-blank")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise TrustedHistoricalError("identity symbol must be canonical uppercase")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise TrustedHistoricalError("identity effective_to must be after effective_from")

    def contains(self, as_of: date) -> bool:
        return self.effective_from <= as_of and (
            self.effective_to is None or as_of < self.effective_to
        )


class DatedSecurityIdentity:
    """A validated ticker history in which reuse may resolve to a new identity."""

    def __init__(self, intervals: tuple[SecurityIdentityInterval, ...]) -> None:
        if not intervals:
            raise TrustedHistoricalError("security identity history must not be empty")
        ordered = tuple(sorted(intervals, key=lambda item: (item.symbol, item.effective_from)))
        previous_by_symbol: dict[str, SecurityIdentityInterval] = {}
        by_security: dict[str, list[SecurityIdentityInterval]] = {}
        exact: set[tuple[str, str, date, date | None]] = set()
        for interval in ordered:
            key = (
                interval.security_id,
                interval.symbol,
                interval.effective_from,
                interval.effective_to,
            )
            if key in exact:
                raise TrustedHistoricalError("duplicate security identity interval")
            exact.add(key)
            previous = previous_by_symbol.get(interval.symbol)
            if previous is not None and (
                previous.effective_to is None or interval.effective_from < previous.effective_to
            ):
                raise TrustedHistoricalError(
                    f"overlapping identity intervals for symbol {interval.symbol}"
                )
            previous_by_symbol[interval.symbol] = interval
            by_security.setdefault(interval.security_id, []).append(interval)
        for security_id, identity_intervals in by_security.items():
            chronological = sorted(identity_intervals, key=lambda item: item.effective_from)
            for previous, current in zip(chronological, chronological[1:], strict=False):
                if previous.effective_to is None or current.effective_from < previous.effective_to:
                    raise TrustedHistoricalError(
                        f"overlapping ticker identities for security {security_id}"
                    )
        self._intervals = ordered

    def resolve(self, symbol: str, as_of: date) -> str:
        matches = [
            interval.security_id
            for interval in self._intervals
            if interval.symbol == symbol and interval.contains(as_of)
        ]
        if len(matches) != 1:
            raise TrustedHistoricalError(
                f"symbol {symbol} has no unambiguous security identity on {as_of.isoformat()}"
            )
        return matches[0]

    def resolve_snapshot_symbol(self, symbol: str, as_of: date) -> str:
        """Resolve a symbol recorded by an end-of-period membership snapshot.

        The primary reconstruction sometimes labels the final pre-removal snapshot with the
        removal date or a later observation date before the next source snapshot. Normal
        point-in-time resolution stays half-open; this narrower adapter maps a stale snapshot
        symbol to its most recently ended identity only when no active identity exists.
        """
        matches = [
            interval.security_id
            for interval in self._intervals
            if interval.symbol == symbol and interval.contains(as_of)
        ]
        if not matches:
            ended = [
                interval
                for interval in self._intervals
                if interval.symbol == symbol
                and interval.effective_to is not None
                and interval.effective_to <= as_of
            ]
            if ended:
                latest_end = max(
                    interval.effective_to
                    for interval in ended
                    if interval.effective_to is not None
                )
                matches = [
                    interval.security_id
                    for interval in ended
                    if interval.effective_to == latest_end
                ]
        if len(matches) != 1:
            raise TrustedHistoricalError(
                f"symbol {symbol} has no unambiguous snapshot identity on {as_of.isoformat()}"
            )
        return matches[0]


@dataclass(frozen=True, order=True)
class MembershipSnapshot:
    as_of: date
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbols:
            raise TrustedHistoricalError("membership snapshot must not be empty")
        if any(not symbol or symbol != symbol.upper() for symbol in self.symbols):
            raise TrustedHistoricalError("membership symbols must be canonical uppercase")
        if tuple(sorted(set(self.symbols))) != self.symbols:
            raise TrustedHistoricalError("membership symbols must be sorted and unique")


@dataclass(frozen=True, order=True)
class SecurityMembershipInterval:
    source_version: str
    security_id: str
    effective_from: date
    effective_to: date | None


def build_security_membership_intervals(
    snapshots: tuple[MembershipSnapshot, ...],
    identities: DatedSecurityIdentity,
    *,
    source_version: str,
) -> tuple[SecurityMembershipInterval, ...]:
    """Transform dated ticker snapshots into stable-identity membership intervals."""
    if not source_version.strip():
        raise TrustedHistoricalError("source_version must be non-blank")
    if not snapshots:
        raise TrustedHistoricalError("membership snapshots must not be empty")
    dates = [snapshot.as_of for snapshot in snapshots]
    if len(dates) != len(set(dates)):
        raise TrustedHistoricalError("membership snapshots contain duplicate dates")
    ordered = tuple(sorted(snapshots, key=lambda snapshot: snapshot.as_of))
    active: dict[str, date] = {}
    rows: list[SecurityMembershipInterval] = []
    for snapshot in ordered:
        resolved = tuple(
            identities.resolve_snapshot_symbol(symbol, snapshot.as_of)
            for symbol in snapshot.symbols
        )
        if len(resolved) != len(set(resolved)):
            raise TrustedHistoricalError(
                f"multiple member symbols resolve to one security on {snapshot.as_of.isoformat()}"
            )
        current = set(resolved)
        for security_id in sorted(set(active) - current):
            rows.append(
                SecurityMembershipInterval(
                    source_version, security_id, active.pop(security_id), snapshot.as_of
                )
            )
        for security_id in sorted(current - set(active)):
            active[security_id] = snapshot.as_of
    rows.extend(
        SecurityMembershipInterval(source_version, security_id, started, None)
        for security_id, started in active.items()
    )
    return tuple(sorted(rows, key=lambda item: (item.security_id, item.effective_from)))
