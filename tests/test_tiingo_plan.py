from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.cli import tiingo_plan
from src.data.git_source import (
    APPROVED_SOURCE_COMMITS,
    APPROVED_SOURCE_LICENCES,
    APPROVED_SOURCE_ORIGINS,
    create_git_source_manifest,
)


def _manifest(root: Path, source_name: str, filename: str, content: str) -> Path:
    root.mkdir()
    raw = content.encode()
    (root / filename).write_bytes(raw)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", filename], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            APPROVED_SOURCE_ORIGINS[source_name],
        ],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    APPROVED_SOURCE_COMMITS[source_name] = commit
    APPROVED_SOURCE_LICENCES[source_name] = "test-only"
    path = root / "manifest.json"
    create_git_source_manifest(
        root,
        path,
        source_name=source_name,
        licence="test-only",
        relative_files=(filename,),
        retrieved_at=datetime(2026, 9, 16, tzinfo=UTC),
    )
    return path


def test_cli_bounds_requests_to_membership_with_feature_warmup(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    shared = tuple(f"S{index:03d}" for index in range(439))
    membership_content = (
        "date,tickers\n"
        f'2020-01-10,"{",".join(sorted(shared + ("AAA",)))}"\n'
        f'2020-02-10,"{",".join(sorted(shared + ("NEW",)))}"\n'
        f'2022-01-10,"{",".join(sorted(shared + ("AAA",)))}"\n'
    )
    membership_root = tmp_path / "membership"
    membership_manifest = _manifest(
        membership_root,
        "historical_sp500_constituents",
        "membership.csv",
        membership_content,
    )
    identity_root = tmp_path / "identity"
    identity_manifest = _manifest(
        identity_root,
        "unliftedq/index-constitution",
        "events.csv",
        "event_date,event_type,old_symbol,new_symbol,old_name,new_name,source_url,notes\n"
        "2020-01-20,name_change,AAA,,Old,New,https://example.test/event,verified\n",
    )
    output = tmp_path / "plan.json"
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sys,
        "argv",
        [
            "tiingo-plan",
            "--membership-manifest",
            str(membership_manifest),
            "--membership-root",
            str(membership_root),
            "--membership-file",
            "membership.csv",
            "--identity-manifest",
            str(identity_manifest),
            "--identity-root",
            str(identity_root),
            "--identity-file",
            "events.csv",
            "--coverage-start",
            "2018-01-01",
            "--coverage-end",
            "2022-03-01",
            "--lookback-days",
            "400",
            "--output",
            str(output),
        ],
    )

    assert tiingo_plan.main() == 0
    rows = json.loads(output.read_text())
    by_symbol = {
        symbol: [row for row in rows if row["provider_symbol"] == symbol]
        for symbol in {row["provider_symbol"] for row in rows}
    }
    assert [(row["start"], row["end"]) for row in by_symbol["AAA"]] == [
        ("2018-12-06", "2020-02-10"),
        ("2020-12-06", "2022-03-01"),
    ]
    assert by_symbol["NEW"][0]["start"] == "2019-01-06"
    assert by_symbol["SPY"][0] == {
        "security_id": by_symbol["SPY"][0]["security_id"],
        "provider_symbol": "SPY",
        "start": "2018-01-01",
        "end": "2022-03-01",
    }
    assert json.loads(capsys.readouterr().out)["requests"] == len(rows)  # type: ignore[attr-defined]
