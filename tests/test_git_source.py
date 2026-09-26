from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.data.git_source import (
    APPROVED_SOURCE_COMMITS,
    APPROVED_SOURCE_LICENCES,
    GitSourceError,
    create_git_source_manifest,
    tracked_files_under,
    verify_git_source_snapshot,
)
from src.data.trusted_historical import verify_source_snapshot


def _checkout(tmp_path: Path, *, origin: str | None = None) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(checkout), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (checkout / "LICENSE").write_text("MIT\n")
    (checkout / "data.csv").write_text("date,tickers\n")
    subprocess.run(["git", "-C", str(checkout), "add", "LICENSE", "data.csv"], check=True)
    subprocess.run(["git", "-C", str(checkout), "commit", "-qm", "fixture"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "remote",
            "add",
            "origin",
            origin or "https://github.com/chinobing/historical_sp500_constituents.git",
        ],
        check=True,
    )
    return checkout


def _approve_fixture(checkout: Path) -> None:
    commit = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    APPROVED_SOURCE_COMMITS["historical_sp500_constituents"] = commit
    APPROVED_SOURCE_LICENCES["historical_sp500_constituents"] = "MIT"


def test_manifest_is_bound_to_actual_origin_head_and_tracked_content(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    _approve_fixture(checkout)
    output = tmp_path / "manifest.json"
    create_git_source_manifest(
        checkout,
        output,
        source_name="historical_sp500_constituents",
        licence="MIT",
        relative_files=("data.csv", "LICENSE"),
        retrieved_at=datetime(2026, 9, 15, tzinfo=UTC),
    )

    payload = json.loads(output.read_text())
    assert payload["repository_url"] == "https://github.com/chinobing/historical_sp500_constituents"
    assert (
        payload["commit_sha"]
        == subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    assert not verify_source_snapshot(output, checkout).checkout_verified
    assert verify_git_source_snapshot(output, checkout).checkout_verified

    payload["repository_url"] = "https://example.invalid/impostor"
    output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GitSourceError, match="repository does not match"):
        verify_git_source_snapshot(output, checkout)
    payload["repository_url"] = "https://github.com/chinobing/historical_sp500_constituents"

    payload["licence"] = "caller invented"
    output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GitSourceError, match="licence/terms label is not approved"):
        verify_git_source_snapshot(output, checkout)
    payload["licence"] = "MIT"

    payload["commit_sha"] = "f" * 40
    output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GitSourceError, match="approved pinned commit"):
        verify_git_source_snapshot(output, checkout)


def test_wrong_origin_or_modified_file_fails_closed(tmp_path: Path) -> None:
    wrong = _checkout(tmp_path, origin="https://example.invalid/impostor.git")
    with pytest.raises(GitSourceError, match="approved source role"):
        create_git_source_manifest(
            wrong,
            tmp_path / "wrong.json",
            source_name="historical_sp500_constituents",
            licence="MIT",
            relative_files=("data.csv",),
        )
    subprocess.run(
        [
            "git",
            "-C",
            str(wrong),
            "remote",
            "set-url",
            "origin",
            "https://github.com/chinobing/historical_sp500_constituents.git",
        ],
        check=True,
    )
    _approve_fixture(wrong)
    (wrong / "data.csv").write_text("changed\n")
    with pytest.raises(GitSourceError, match="differs from pinned commit"):
        create_git_source_manifest(
            wrong,
            tmp_path / "modified.json",
            source_name="historical_sp500_constituents",
            licence="MIT",
            relative_files=("data.csv",),
        )


def test_tracked_tree_expansion_is_complete_and_confined(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    assert tracked_files_under(checkout, (".",)) == ("LICENSE", "data.csv")
    with pytest.raises(GitSourceError, match="canonical and relative"):
        tracked_files_under(checkout, ("../escape",))
