from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from src.cli import historical_build
from src.data.execution_audit import ExecutionAuditRecord, audit_historical_executions
from src.data.fmp import FmpRequest, acquire_fmp_extracts
from src.data.fmp_transform import transform_fmp_manifest
from src.data.membership_audit import derive_constituent_changes
from src.data.source_adapters import (
    transform_audit_evidence_source,
    transform_identity_source,
    transform_membership_source,
)
from src.data.tiingo import TiingoRequest, acquire_tiingo_extracts
from src.data.tiingo_transform import transform_tiingo_source
from src.data.trusted_historical import (
    DatedSecurityIdentity,
    VerifiedSourceSnapshot,
    verify_source_snapshot,
)
from src.data.trusted_producer import build_trusted_historical_dataset


def _source(root: Path, index: int, content: bytes | None = None) -> VerifiedSourceSnapshot:
    names = (
        "historical_sp500_constituents",
        "unliftedq/index-constitution",
        "riazarbi/sp500-scraper",
        "historical-spy-holdings",
    )
    source_name = names[index]
    source_root = root / f"source-{index}"
    source_root.mkdir()
    filename = f"source-{index}.csv"
    content = content or f"source-{index}\n".encode()
    (source_root / filename).write_bytes(content)
    manifest = source_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_name": source_name,
                "repository_url": f"https://example.test/source-{index}",
                "commit_sha": f"{index + 1:x}" * 40,
                "licence": "MIT",
                "retrieved_at": datetime(2026, 9, 13, tzinfo=UTC).isoformat(),
                "files": [{"path": filename, "sha256": hashlib.sha256(content).hexdigest()}],
            }
        ),
        encoding="utf-8",
    )
    return verify_source_snapshot(manifest, source_root)


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
    audit_csv = (
        "symbol,action,effective_date\n"
        + "".join(
            f"{change.symbol},{change.action},{change.effective_date.isoformat()}\n"
            for change in changes
        )
    ).encode()
    qa_evidence_sources = tuple(
        transform_audit_evidence_source(
            _source(tmp_path, index, audit_csv),
            tmp_path / f"source-{index}",
            f"source-{index}.csv",
        )
        for index in (2, 3)
    )
    security_by_symbol = {row.symbol: row.security_id for row in identity_intervals}
    instruments = tuple((security_by_symbol[symbol], symbol) for symbol in final_symbols + ("SPY",))
    tiingo_root = tmp_path / "tiingo"
    tiingo_acquisition = acquire_tiingo_extracts(
        tuple(
            TiingoRequest(security_id, symbol, sessions[0], sessions[1])
            for security_id, symbol in instruments
        ),
        tiingo_root,
        token="token",
        transport=_TiingoTransport(),
        plan="test-plan",
        api_version="v1",
        licence="terms-reviewed",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    tiingo_source = transform_tiingo_source(tiingo_acquisition.manifest_path, tiingo_root)
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
        execution_audit=audit_historical_executions(
            sessions,
            (
                ExecutionAuditRecord(
                    sessions[0],
                    sessions[1],
                    security_by_symbol["B000"],
                    1_000,
                    10,
                    0.35,
                    0.70,
                    5,
                    10,
                ),
            ),
        ),
    )
    assert result.membership_audit.passed
    assert result.semantic_report.passed
    assert result.trusted_evidence.semantically_validated
    assert result.canonical.manifest_path.is_file()
    assert result.evidence_manifest_path.is_file()

    sessions_path = tmp_path / "sessions.txt"
    sessions_path.write_text("".join(f"{day.isoformat()}\n" for day in sessions), encoding="utf-8")
    execution_path = tmp_path / "execution.json"
    execution_path.write_text(
        json.dumps(
            [
                {
                    "decision_session": sessions[0].isoformat(),
                    "fill_session": sessions[1].isoformat(),
                    "security_id": security_by_symbol["B000"],
                    "notional": 1_000,
                    "fill_price": 10,
                    "baseline_commission": 0.35,
                    "stressed_commission": 0.70,
                    "baseline_slippage_bps": 5,
                    "stressed_slippage_bps": 10,
                }
            ]
        ),
        encoding="utf-8",
    )
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
                f"source-{index}.csv",
            ]
        )
    arguments.extend(
        [
            "--tiingo-manifest",
            str(tiingo_acquisition.manifest_path),
            "--tiingo-root",
            str(tiingo_root),
            "--fmp-manifest",
            str(fmp_acquisition.manifest_path),
            "--fmp-root",
            str(fmp_root),
            "--sessions",
            str(sessions_path),
            "--execution-audit",
            str(execution_path),
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
    assert Path(output["producer_evidence"]).is_file()
