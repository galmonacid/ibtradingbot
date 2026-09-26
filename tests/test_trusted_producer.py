from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.cli import historical_build
from src.data.fmp import FmpRequest, acquire_fmp_extracts
from src.data.fmp_transform import transform_fmp_manifest
from src.data.git_source import (
    APPROVED_SOURCE_COMMITS,
    APPROVED_SOURCE_LICENCES,
    APPROVED_SOURCE_ORIGINS,
    create_git_source_manifest,
    verify_git_source_snapshot,
)
from src.data.membership_audit import derive_constituent_changes
from src.data.source_adapters import (
    transform_identity_source,
    transform_membership_source,
    transform_riazarbi_audit_source,
)
from src.data.source_native_qa import ISHARES_IVV_ROLE, WIKIPEDIA_ROLE
from src.data.tiingo import TiingoRequest, acquire_tiingo_extracts
from src.data.tiingo_transform import transform_tiingo_source
from src.data.trusted_historical import (
    DatedSecurityIdentity,
    VerifiedSourceSnapshot,
)
from src.data.trusted_producer import build_trusted_historical_dataset


def _source(root: Path, index: int, content: bytes | None = None) -> VerifiedSourceSnapshot:
    names = (
        "historical_sp500_constituents",
        "unliftedq/index-constitution",
        "riazarbi/sp500-scraper",
        "historical-index-etf-holdings",
    )
    source_name = names[index]
    source_root = root / f"source-{index}"
    source_root.mkdir()
    filename = f"source-{index}.csv"
    content = content or f"source-{index}\n".encode()
    (source_root / filename).write_bytes(content)
    return _commit_source(source_root, source_name, (filename,))


def _commit_source(
    source_root: Path, source_name: str, relative_files: tuple[str, ...]
) -> VerifiedSourceSnapshot:
    subprocess.run(["git", "init", "-q", str(source_root)], check=True)
    subprocess.run(["git", "-C", str(source_root), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(source_root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(source_root), "add", *relative_files], check=True)
    subprocess.run(["git", "-C", str(source_root), "commit", "-qm", "fixture"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source_root),
            "remote",
            "add",
            "origin",
            APPROVED_SOURCE_ORIGINS[source_name],
        ],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    APPROVED_SOURCE_COMMITS[source_name] = commit
    APPROVED_SOURCE_LICENCES[source_name] = "MIT"
    manifest = source_root / "manifest.json"
    create_git_source_manifest(
        source_root,
        manifest,
        source_name=source_name,
        licence="MIT",
        relative_files=relative_files,
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    return verify_git_source_snapshot(manifest, source_root)


def _native_qa_source(
    root: Path,
    index: int,
    initial_symbols: tuple[str, ...],
    final_symbols: tuple[str, ...],
) -> tuple[VerifiedSourceSnapshot, str]:
    source_root = root / f"source-{index}"
    directory = source_root / "snapshots"
    directory.mkdir(parents=True)
    dates = ("20190101", "20200102")
    relative_files: list[str] = []
    for stamp, symbols in zip(dates, (initial_symbols, final_symbols), strict=True):
        relative = f"snapshots/{stamp}.csv"
        path = source_root / relative
        day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if index == 2:
                header = [
                    "Symbol",
                    "Security",
                    "GICS Sector",
                    "GICS Sub-Industry",
                    "Headquarters Location",
                    "Date added",
                    "CIK",
                    "Founded",
                    "date",
                ]
                writer.writerow(header)
                writer.writerows(
                    [symbol, symbol, "Sector", "Industry", "US", "", "1", "2000", day]
                    for symbol in symbols
                )
            else:
                header = [
                    "symbol", "name", "sector", "asset_class", "market_value",
                    "weight_pct", "notional_value", "shares", "CUSIP", "ISIN",
                    "SEDOL", "price", "location", "exchange", "market_currency",
                    "fx_rate", "accrual_date", "date",
                ]
                writer.writerow(header)
                writer.writerows(
                    [
                        symbol, symbol, "Sector", "Equity", "1", "1", "1", "1",
                        "x", "x", "x", "1", "US", "NYSE", "USD", "1", "-", day,
                    ]
                    for symbol in symbols
                )
        relative_files.append(relative)
    source_name = "riazarbi/sp500-scraper" if index == 2 else "historical-index-etf-holdings"
    return _commit_source(source_root, source_name, tuple(relative_files)), "snapshots"


class _TiingoTransport:
    def get_json(self, endpoint: str, parameters: object, token: str) -> object:
        symbol = endpoint.split("/")[2]
        price = 100 if symbol == "SPY" else 10
        return [
            {
                "date": f"{day.isoformat()}T00:00:00Z",
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "adjClose": price,
                "adjOpen": price,
                "adjHigh": price,
                "adjLow": price,
                "adjVolume": 100,
                "volume": 100,
                "divCash": 0,
                "splitFactor": 1,
            }
            for day in (date(2020, 1, 2), date(2020, 1, 3))
        ]


class _FmpTransport:
    def get_json(self, endpoint: str, parameters: object, token: str) -> object:
        assert isinstance(parameters, dict)
        symbol = str(parameters.get("symbol", ""))
        if endpoint == "historical-price-eod/full":
            price = 100 if symbol == "SPY" else 10
            return [
                {
                    "date": day.isoformat(),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 100,
                }
                for day in (date(2020, 1, 2), date(2020, 1, 3))
            ]
        if endpoint == "dividends":
            return []
        return []


def test_offline_producer_connects_sources_audit_semantics_parquet_and_evidence(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    sessions = (date(2020, 1, 2), date(2020, 1, 3))
    shared_symbols = tuple(f"C{index:03d}" for index in range(425))
    old_symbols = tuple(f"A{index:03d}" for index in range(25))
    new_symbols = tuple(f"B{index:03d}" for index in range(25))
    initial_symbols = tuple(sorted(shared_symbols + old_symbols))
    final_symbols = tuple(sorted(shared_symbols + new_symbols))
    membership_csv = (
        "date,tickers\n"
        f'2019-01-01,"{",".join(initial_symbols)}"\n'
        f'2020-01-02,"{",".join(final_symbols)}"\n'
    ).encode()
    membership_snapshot = _source(tmp_path, 0, membership_csv)
    membership_source = transform_membership_source(
        membership_snapshot, tmp_path / "source-0", "source-0.csv"
    )
    identity_csv = (
        b"event_date,event_type,old_symbol,new_symbol,old_name,new_name,source_url,notes\n"
        b"2019-06-01,name_change,A000,,Old name,New name,https://example.test/event,verified\n"
    )
    identity_snapshot = _source(tmp_path, 1, identity_csv)
    identity_source = transform_identity_source(
        identity_snapshot,
        tmp_path / "source-1",
        "source-1.csv",
        coverage_start=date(2019, 1, 1),
        known_symbols=tuple(sorted(set(initial_symbols + final_symbols + ("SPY",)))),
    )
    identity_intervals = identity_source.parsed.identity_intervals
    membership_snapshots = membership_source.memberships
    changes = derive_constituent_changes(
        membership_snapshots, DatedSecurityIdentity(identity_intervals)
    )
    native_sources = tuple(
        _native_qa_source(tmp_path, index, initial_symbols, final_symbols)
        for index in (2, 3)
    )
    qa_evidence_sources = (
        transform_riazarbi_audit_source(
            native_sources[0][0],
            tmp_path / "source-2",
            native_sources[0][1],
            source_role=WIKIPEDIA_ROLE,
        ),
        transform_riazarbi_audit_source(
            native_sources[1][0],
            tmp_path / "source-3",
            native_sources[1][1],
            source_role=ISHARES_IVV_ROLE,
        ),
    )
    security_by_symbol = {row.symbol: row.security_id for row in identity_intervals}
    instruments = tuple((security_by_symbol[symbol], symbol) for symbol in final_symbols + ("SPY",))
    tiingo_requests = tuple(
        TiingoRequest(security_id, symbol, sessions[0], sessions[1])
        for security_id, symbol in instruments
    )
    tiingo_plan_path = tmp_path / "tiingo-plan.json"
    tiingo_plan_path.write_text(
        json.dumps(
            [
                {
                    "security_id": row.security_id,
                    "provider_symbol": row.provider_symbol,
                    "start": row.start.isoformat(),
                    "end": row.end.isoformat(),
                }
                for row in tiingo_requests
            ]
        ),
        encoding="utf-8",
    )
    tiingo_root = tmp_path / "tiingo"
    tiingo_acquisition = acquire_tiingo_extracts(
        tiingo_requests,
        tiingo_root,
        token="token",
        transport=_TiingoTransport(),
        plan="test-plan",
        api_version="v1",
        licence="terms-reviewed",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    tiingo_source = transform_tiingo_source(
        tiingo_acquisition.manifest_path, tiingo_root, tiingo_plan_path
    )
    fmp_root = tmp_path / "fmp"
    fmp_acquisition = acquire_fmp_extracts(
        tuple(
            FmpRequest("historical-price-eod/full", security_id, symbol, sessions[0], sessions[1])
            for security_id, symbol in instruments
        )
        + (
            FmpRequest("dividends", security_by_symbol["B000"], "B000", sessions[0], sessions[1]),
            FmpRequest("delisted-companies", "GLOBAL", ""),
        ),
        fmp_root,
        token="token",
        transport=_FmpTransport(),
        plan="Basic",
        api_version="stable",
        licence="terms-reviewed",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    fmp_source = transform_fmp_manifest(
        fmp_acquisition.manifest_path, fmp_root, identities=identity_intervals
    )
    result = build_trusted_historical_dataset(
        tmp_path / "build",
        membership_source=membership_source,
        identity_source=identity_source,
        qa_evidence_sources=qa_evidence_sources,  # type: ignore[arg-type]
        tiingo_source=tiingo_source,
        fmp_source=fmp_source,
        sessions=sessions,
        benchmark_security_id=security_by_symbol["SPY"],
        primary_changes=changes,
        audit_sample_size=50,
        audit_seed=7,
        exclusions=(),
        terminal_treatments=(),
        fmp_quarantines=(),
    )
    assert result.membership_audit.passed
    assert result.semantic_report.passed
    assert result.dataset_evidence.certified
    assert result.canonical.manifest_path.is_file()
    assert result.dataset_evidence_manifest_path.is_file()
    assert result.universe_policy_path.is_file()

    without_fmp = build_trusted_historical_dataset(
        tmp_path / "build-without-fmp",
        membership_source=membership_source,
        identity_source=identity_source,
        qa_evidence_sources=qa_evidence_sources,  # type: ignore[arg-type]
        tiingo_source=tiingo_source,
        fmp_source=None,
        sessions=sessions,
        benchmark_security_id=security_by_symbol["SPY"],
        primary_changes=changes,
        audit_sample_size=50,
        audit_seed=7,
        exclusions=(),
        terminal_treatments=(),
    )
    assert without_fmp.fmp_reconciliation is None
    assert without_fmp.dataset_evidence.certified

    sessions_path = tmp_path / "sessions.txt"
    sessions_path.write_text("".join(f"{day.isoformat()}\n" for day in sessions), encoding="utf-8")
    cli_output = tmp_path / "cli-build"
    arguments = ["historical-build"]
    for role, index in (
        ("membership", 0),
        ("identity", 1),
        ("scraper-qa", 2),
        ("holdings-qa", 3),
    ):
        arguments.extend(
            [
                f"--{role}-manifest",
                str(tmp_path / f"source-{index}" / "manifest.json"),
                f"--{role}-root",
                str(tmp_path / f"source-{index}"),
                f"--{role}-file",
                "snapshots" if index in (2, 3) else f"source-{index}.csv",
            ]
        )
    arguments.extend(
        [
            "--tiingo-manifest",
            str(tiingo_acquisition.manifest_path),
            "--tiingo-root",
            str(tiingo_root),
            "--tiingo-request-plan",
            str(tiingo_plan_path),
            "--fmp-manifest",
            str(fmp_acquisition.manifest_path),
            "--fmp-root",
            str(fmp_root),
            "--sessions",
            str(sessions_path),
            "--coverage-start",
            "2019-01-01",
            "--output-directory",
            str(cli_output),
            "--audit-sample-size",
            "50",
        ]
    )
    monkeypatch.setattr(sys, "argv", arguments)  # type: ignore[attr-defined]
    assert historical_build.main() == 0
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert Path(output["canonical_manifest"]).is_file()
    assert Path(output["dataset_evidence"]).is_file()
    assert Path(output["universe_policy"]).is_file()

    partial_root = tmp_path / "tiingo-partial"
    shutil.copytree(tiingo_root, partial_root)
    partial_manifest_path = partial_root / "tiingo_manifest.json"
    partial_manifest = json.loads(partial_manifest_path.read_text())
    failed_record = next(
        row for row in partial_manifest["requests"] if row["provider_symbol"] == "B024"
    )
    failed_record = {
        key: value
        for key, value in failed_record.items()
        if key in {"request_id", "security_id", "provider_symbol", "endpoint", "parameters"}
    } | {"status": "failed", "attempts": 1, "error": "HTTPError: 404"}
    partial_manifest["requests"] = [
        failed_record if row["provider_symbol"] == "B024" else row
        for row in partial_manifest["requests"]
    ]
    partial_manifest["complete"] = False
    partial_manifest_path.write_text(json.dumps(partial_manifest), encoding="utf-8")
    partial_source = transform_tiingo_source(
        partial_manifest_path, partial_root, tiingo_plan_path
    )
    partial_build = build_trusted_historical_dataset(
        tmp_path / "partial-build",
        membership_source=membership_source,
        identity_source=identity_source,
        qa_evidence_sources=qa_evidence_sources,  # type: ignore[arg-type]
        tiingo_source=partial_source,
        fmp_source=None,
        sessions=sessions,
        benchmark_security_id=security_by_symbol["SPY"],
        primary_changes=changes,
        audit_sample_size=50,
        audit_seed=7,
        exclusions=(),
        terminal_treatments=(),
        minimum_investable_constituents=400,
    )
    policy = json.loads(partial_build.universe_policy_path.read_text())
    assert min(row["price_eligible_constituents"] for row in policy["session_counts"]) == 449
    with pytest.raises(ValueError, match="never sustains"):
        build_trusted_historical_dataset(
            tmp_path / "partial-build-too-strict",
            membership_source=membership_source,
            identity_source=identity_source,
            qa_evidence_sources=qa_evidence_sources,  # type: ignore[arg-type]
            tiingo_source=partial_source,
            fmp_source=None,
            sessions=sessions,
            benchmark_security_id=security_by_symbol["SPY"],
            primary_changes=changes,
            audit_sample_size=50,
            audit_seed=7,
            exclusions=(),
            terminal_treatments=(),
            minimum_investable_constituents=450,
        )
