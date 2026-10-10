"""Causal source extraction tests; synthetic filings are not investment evidence."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.cli.r3_identity_audit import materialize
from src.data.r3_identity import CoverAudit, audit_sec_cover, available_cover_observations

ACCEPTED = datetime(2022, 5, 31, 20, 18, 52, tzinfo=UTC)


def fact(name: str, value: str, context: str = "cover", extra: str = "") -> str:
    return (
        f'<ix:nonNumeric name="dei:{name}" contextRef="{context}" {extra}>{value}</ix:nonNumeric>'
    )


def security(symbol: str, context: str, title: str = "Class A Common Stock") -> str:
    return (
        fact("Security12bTitle", title, context)
        + fact("TradingSymbol", symbol, context)
        + fact("SecurityExchangeName", "NASDAQ", context)
    )


def document(content: str) -> bytes:
    return (fact("EntityCentralIndexKey", "1326801") + content).encode()


def audit(payload: bytes, accepted: datetime = ACCEPTED) -> CoverAudit:
    return audit_sec_cover(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        cik="0001326801",
        accession="0001326801-22-000070",
        accepted_at=accepted,
    )


def test_simultaneous_classes_remain_separate_and_debt_is_not_equity() -> None:
    result = audit(
        document(
            security("A", "a")
            + security("B", "b", "Class B Common Stock")
            + security("NOTE", "n", "Senior Notes")
        )
    )
    assert not result.issues
    assert [r.symbol for r in result.observations] == ["A", "B", "NOTE"]
    assert result.observations[-1].class_title == "Senior Notes"


def test_later_filing_cannot_populate_earlier_decisions() -> None:
    first = audit(document(security("FB", "a")))
    later = audit(document(security("META", "a")), ACCEPTED + timedelta(days=30))
    cutoff = ACCEPTED + timedelta(days=2)
    assert available_cover_observations((first, later), cutoff) == (
        available_cover_observations((first,), cutoff)
    )
    assert available_cover_observations((first,), ACCEPTED) == ()
    assert len(available_cover_observations((first,), ACCEPTED + timedelta(hours=24))) == 1


def test_fiscal_context_does_not_backdate_availability() -> None:
    result = audit(document(security("FB", "19990101_19991231")))
    assert result.observations[0].available_at == ACCEPTED + timedelta(hours=24)


def test_duplicate_equal_facts_are_idempotent() -> None:
    result = audit(document(security("FB", "a") + fact("TradingSymbol", "FB", "a")))
    assert not result.issues
    assert len(result.observations) == 1


@pytest.mark.parametrize(
    "content",
    [
        security("FB", "a") + fact("TradingSymbol", "META", "a"),
        fact("TradingSymbol", "FB", "a"),
        security("FB", "a") + fact("EntityCentralIndexKey", "999"),
        fact("TradingSymbol", "FB", "a", 'continuedAt="next"'),
        '<ix:nonNumeric name="dei:TradingSymbol" contextRef="a">FB',
        security("FB", "a") + fact("TradingSymbol", "OTHER", ""),
    ],
)
def test_ambiguous_or_unsupported_filing_fails_closed(content: str) -> None:
    result = audit(document(content))
    assert result.issues
    assert not result.observations


def test_inline_exclusion_and_nested_formatting() -> None:
    result = audit(document(security("<b>F</b>B<ix:exclude>footnote</ix:exclude>", "a")))
    assert result.observations[0].symbol == "FB"


def test_hash_and_timestamp_validation() -> None:
    payload = document(security("FB", "a"))
    with pytest.raises(ValueError, match="hash"):
        audit_sec_cover(
            payload, expected_sha256="0" * 64, cik="0001326801", accession="x", accepted_at=ACCEPTED
        )
    with pytest.raises(ValueError, match="aware"):
        audit(payload, ACCEPTED.replace(tzinfo=None))
    with pytest.raises(ValueError, match="aware"):
        available_cover_observations((), ACCEPTED.replace(tzinfo=None))


def test_incomplete_context_does_not_borrow_another_class_fields() -> None:
    result = audit(document(fact("TradingSymbol", "FB", "a") + security("OTHER", "b")))
    assert result.issues == ("incomplete_or_conflicting_context:a",)
    assert [row.symbol for row in result.observations] == ["OTHER"]


def test_exchange_transform_retains_display_text_only() -> None:
    content = (
        fact("Security12bTitle", "Common Stock")
        + fact("TradingSymbol", "FB")
        + fact(
            "SecurityExchangeName",
            "The Nasdaq Stock Market LLC",
            extra='format="ixt-sec:exchnameen"',
        )
    )
    result = audit(document(content))
    assert not result.issues
    assert result.observations[0].exchange_display == "The Nasdaq Stock Market LLC"


def input_manifest(tmp_path: Path) -> Path:
    payload = document(security("FB", "a"))
    source = tmp_path / "filing.html"
    source.write_bytes(payload)
    metadata = tmp_path / "submissions.json"
    metadata.write_text(
        json.dumps({"accessionNumber": ["example"], "acceptanceDateTime": [ACCEPTED.isoformat()]})
    )
    manifest = tmp_path / "input.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_version": "r3-sec-cover-audit-input-v1",
                "processing_latency_hours": 24,
                "filings": [
                    {
                        "cik": "0001326801",
                        "accession": "example",
                        "document_path": str(source),
                        "document_sha256": hashlib.sha256(payload).hexdigest(),
                        "acceptance_path": str(metadata),
                        "acceptance_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    )
    return manifest


def test_materializer_binds_inputs_and_refuses_overwrite(tmp_path: Path) -> None:
    manifest = input_manifest(tmp_path)
    output = tmp_path / "report.json"
    result = materialize(manifest, output, ACCEPTED + timedelta(days=1))
    assert result["observations"] == 1
    assert result["report_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    report = json.loads(output.read_text())
    assert report["step4_ready"] is False
    with pytest.raises(FileExistsError):
        materialize(manifest, output, ACCEPTED + timedelta(days=1))


def test_materializer_rejects_tampered_acceptance_source(tmp_path: Path) -> None:
    manifest = input_manifest(tmp_path)
    (tmp_path / "submissions.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        materialize(manifest, tmp_path / "report.json", ACCEPTED + timedelta(days=1))
    assert not (tmp_path / "report.json").exists()


def test_materializer_rejects_future_filing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="audit time"):
        materialize(
            input_manifest(tmp_path), tmp_path / "report.json", ACCEPTED - timedelta(days=1)
        )
