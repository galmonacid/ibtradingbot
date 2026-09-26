"""Create immutable manifests from approved, clean Git source checkouts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from src.data.trusted_historical import VerifiedSourceSnapshot, verify_source_snapshot


class GitSourceError(ValueError):
    """Raised when a checkout cannot establish an approved source identity."""


APPROVED_SOURCE_ORIGINS = {
    "historical_sp500_constituents": "https://github.com/chinobing/historical_sp500_constituents",
    "unliftedq/index-constitution": "https://github.com/unliftedq/index-constitution",
    "riazarbi/sp500-scraper": "https://github.com/riazarbi/sp500-scraper",
    "historical-index-etf-holdings": "https://github.com/riazarbi/sp500-scraper",
}
APPROVED_SOURCE_COMMITS = {
    "historical_sp500_constituents": "6e06d3a2fdb81105a55edd3f33a460ca997d8316",
    "unliftedq/index-constitution": "dd1604c5176176f6cf6418c2a4bab0277b51d4ff",
    "riazarbi/sp500-scraper": "016212b68791b6ca476b34c63634719115080d40",
    "historical-index-etf-holdings": "016212b68791b6ca476b34c63634719115080d40",
}
APPROVED_SOURCE_LICENCES = {
    "historical_sp500_constituents": "MIT",
    "unliftedq/index-constitution": "MIT",
    "riazarbi/sp500-scraper": (
        "NO-LICENSE-FILE; user-authorized local research only; no redistribution"
    ),
    "historical-index-etf-holdings": (
        "NO-LICENSE-FILE; user-authorized local research only; no redistribution"
    ),
}


def _git(checkout: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(checkout), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitSourceError(f"Git source verification failed: {' '.join(arguments)}") from error


def _canonical_origin(value: str) -> str:
    origin = value.removesuffix(".git").rstrip("/")
    if origin.startswith("git@github.com:"):
        origin = "https://github.com/" + origin.removeprefix("git@github.com:")
    return origin


def tracked_files_under(checkout: Path, relative_directories: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve selected repository directories to their complete tracked-file population."""
    files: set[str] = set()
    for relative in relative_directories:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
            raise GitSourceError("source tree paths must be canonical and relative")
        files.update(
            line
            for line in _git(checkout.resolve(), "ls-files", "--", relative).splitlines()
            if line
        )
    if relative_directories and not files:
        raise GitSourceError("selected source trees contain no tracked files")
    return tuple(sorted(files))


def create_git_source_manifest(
    checkout: Path,
    output_path: Path,
    *,
    source_name: str,
    licence: str,
    relative_files: tuple[str, ...],
    retrieved_at: datetime | None = None,
) -> Path:
    """Hash selected tracked files and bind them to the checkout's actual origin and HEAD."""
    root = checkout.resolve()
    expected_origin = APPROVED_SOURCE_ORIGINS.get(source_name)
    if expected_origin is None:
        raise GitSourceError("source role is not approved")
    actual_origin = _canonical_origin(_git(root, "remote", "get-url", "origin"))
    if actual_origin != expected_origin:
        raise GitSourceError("checkout origin does not match the approved source role")
    commit = _git(root, "rev-parse", "HEAD")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise GitSourceError("checkout HEAD is not a canonical commit SHA")
    if commit != APPROVED_SOURCE_COMMITS[source_name]:
        raise GitSourceError("checkout HEAD is not the approved pinned source commit")
    if licence.strip() != APPROVED_SOURCE_LICENCES[source_name]:
        raise GitSourceError("source licence/terms label is not the approved recorded value")
    if not relative_files or len(relative_files) != len(set(relative_files)):
        raise GitSourceError("source files must be non-empty and unique")
    rows: list[dict[str, str]] = []
    for relative in sorted(relative_files):
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
            raise GitSourceError("source file paths must be canonical and relative")
        _git(root, "ls-files", "--error-unmatch", "--", relative)
        if _git(root, "status", "--porcelain", "--", relative):
            raise GitSourceError(f"source file differs from pinned commit: {relative}")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise GitSourceError(f"source file is missing: {relative}")
        rows.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    when = retrieved_at or datetime.now(UTC)
    if when.tzinfo is None or when.utcoffset() is None:
        raise GitSourceError("retrieval timestamp must be timezone-aware")
    payload = {
        "source_name": source_name,
        "repository_url": actual_origin,
        "commit_sha": commit,
        "licence": licence.strip(),
        "retrieved_at": when.astimezone(UTC).isoformat(),
        "files": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def verify_git_source_snapshot(manifest_path: Path, checkout: Path) -> VerifiedSourceSnapshot:
    """Revalidate manifest identity against the checkout's actual approved origin and HEAD."""
    snapshot = verify_source_snapshot(manifest_path, checkout)
    expected_origin = APPROVED_SOURCE_ORIGINS.get(snapshot.source_name)
    if expected_origin is None:
        raise GitSourceError("source role is not approved")
    root = checkout.resolve()
    if _canonical_origin(_git(root, "remote", "get-url", "origin")) != expected_origin:
        raise GitSourceError("checkout origin does not match the approved source role")
    if _canonical_origin(snapshot.repository_url) != expected_origin:
        raise GitSourceError("source manifest repository does not match the approved origin")
    if snapshot.commit_sha != APPROVED_SOURCE_COMMITS[snapshot.source_name]:
        raise GitSourceError("source manifest commit is not the approved pinned commit")
    if snapshot.licence != APPROVED_SOURCE_LICENCES[snapshot.source_name]:
        raise GitSourceError("source manifest licence/terms label is not approved")
    if _git(root, "rev-parse", "HEAD") != snapshot.commit_sha:
        raise GitSourceError("source manifest commit does not match checkout HEAD")
    for row in snapshot.files:
        _git(root, "ls-files", "--error-unmatch", "--", row.path)
        if _git(root, "status", "--porcelain", "--", row.path):
            raise GitSourceError(f"source file differs from pinned commit: {row.path}")
    return replace(snapshot, checkout_verified=True)
