from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.data.trusted_historical import (
    DatedSecurityIdentity,
    MembershipSnapshot,
    SecurityIdentityInterval,
    TrustedHistoricalError,
    VerifiedSourceSnapshot,
    build_security_membership_intervals,
    verify_source_snapshot,
)


def test_verified_source_snapshot_cannot_be_constructed_without_verification() -> None:
    with pytest.raises(TrustedHistoricalError, match="must be issued"):
        VerifiedSourceSnapshot(
            "x",
            "https://example.test",
            "a" * 40,
            "MIT",
            datetime.now(UTC),
            (),
            "b" * 64,
            False,
        )


def _manifest(root: Path, **changes: object) -> Path:
    source = root / "snapshots" / "members.csv"
    source.parent.mkdir(exist_ok=True)
    source.write_text("date,symbol\n2020-01-01,AAA\n", encoding="utf-8")
    payload: dict[str, object] = {
        "source_name": "historical_sp500_constituents",
        "repository_url": "https://github.com/chinobing/historical_sp500_constituents",
        "commit_sha": "a" * 40,
        "licence": "MIT",
        "retrieved_at": "2026-09-12T10:00:00+00:00",
        "files": [
            {
                "path": "snapshots/members.csv",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ],
    }
    payload.update(changes)
    path = root / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_source_manifest_verifies_pinned_hashed_files(tmp_path: Path) -> None:
    result = verify_source_snapshot(_manifest(tmp_path), tmp_path)

    assert result.commit_sha == "a" * 40
    assert result.licence == "MIT"
    assert result.files[0].path == "snapshots/members.csv"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"commit_sha": "main"}, "40 lowercase"),
        ({"licence": ""}, "licence must be"),
        ({"retrieved_at": "2026-09-12T10:00:00"}, "timezone-aware"),
        ({"api_key": "do-not-store"}, "credentials or secrets"),
    ],
)
def test_source_manifest_rejects_incomplete_or_sensitive_evidence(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(TrustedHistoricalError, match=message):
        verify_source_snapshot(_manifest(tmp_path, **changes), tmp_path)


def test_source_manifest_rejects_hash_mismatch_and_path_escape(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "snapshots" / "members.csv").write_text("changed", encoding="utf-8")
    with pytest.raises(TrustedHistoricalError, match="hash mismatch"):
        verify_source_snapshot(manifest, tmp_path)

    escaped = _manifest(
        tmp_path,
        files=[{"path": "../outside.csv", "sha256": "b" * 64}],
    )
    with pytest.raises(TrustedHistoricalError, match="canonical relative"):
        verify_source_snapshot(escaped, tmp_path)


def _identities() -> DatedSecurityIdentity:
    return DatedSecurityIdentity(
        (
            SecurityIdentityInterval("SEC-1", "OLD", date(2010, 1, 1), date(2020, 6, 1)),
            SecurityIdentityInterval("SEC-1", "NEW", date(2020, 6, 1), None),
            SecurityIdentityInterval("SEC-2", "OLD", date(2025, 1, 1), None),
            SecurityIdentityInterval("SEC-3", "BBB", date(2010, 1, 1), None),
        )
    )


def test_membership_uses_stable_identity_across_rename_and_ticker_reuse() -> None:
    snapshots = (
        MembershipSnapshot(date(2020, 1, 1), ("OLD",)),
        MembershipSnapshot(date(2020, 7, 1), ("NEW",)),
        MembershipSnapshot(date(2024, 1, 1), ("BBB",)),
        MembershipSnapshot(date(2025, 2, 1), ("BBB", "OLD")),
    )
    result = build_security_membership_intervals(snapshots, _identities(), source_version="pit-v1")

    assert [(row.security_id, row.effective_from, row.effective_to) for row in result] == [
        ("SEC-1", date(2020, 1, 1), date(2024, 1, 1)),
        ("SEC-2", date(2025, 2, 1), None),
        ("SEC-3", date(2024, 1, 1), None),
    ]


def test_future_snapshots_and_identity_events_do_not_change_historical_prefix() -> None:
    prefix = (MembershipSnapshot(date(2020, 1, 1), ("OLD",)),)
    before = build_security_membership_intervals(prefix, _identities(), source_version="pit-v1")
    extended = (*prefix, MembershipSnapshot(date(2025, 2, 1), ("OLD",)))
    after = build_security_membership_intervals(extended, _identities(), source_version="pit-v1")

    assert before[0].security_id == after[0].security_id == "SEC-1"
    assert before[0].effective_from == after[0].effective_from == date(2020, 1, 1)


def test_identity_and_membership_conflicts_fail_closed() -> None:
    with pytest.raises(TrustedHistoricalError, match="overlapping identity"):
        DatedSecurityIdentity(
            (
                SecurityIdentityInterval("SEC-1", "AAA", date(2020, 1, 1), None),
                SecurityIdentityInterval("SEC-2", "AAA", date(2021, 1, 1), None),
            )
        )
    with pytest.raises(TrustedHistoricalError, match="overlapping ticker identities"):
        DatedSecurityIdentity(
            (
                SecurityIdentityInterval("SEC-1", "AAA", date(2020, 1, 1), None),
                SecurityIdentityInterval("SEC-1", "BBB", date(2021, 1, 1), None),
            )
        )
    identities = DatedSecurityIdentity(
        (SecurityIdentityInterval("SEC-1", "AAA", date(2020, 1, 1), None),)
    )
    with pytest.raises(TrustedHistoricalError, match="no unambiguous"):
        build_security_membership_intervals(
            (MembershipSnapshot(date(2019, 1, 1), ("AAA",)),),
            identities,
            source_version="pit-v1",
        )
    duplicate_dates = (
        MembershipSnapshot(date(2020, 1, 1), ("AAA",)),
        MembershipSnapshot(date(2020, 1, 1), ("AAA",)),
    )
    with pytest.raises(TrustedHistoricalError, match="duplicate dates"):
        build_security_membership_intervals(duplicate_dates, identities, source_version="pit-v1")
