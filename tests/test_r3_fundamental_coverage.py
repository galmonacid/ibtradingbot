import json
from datetime import datetime
from pathlib import Path

import pytest

from src.cli.r3_fundamental_coverage import materialize
from src.research.r3_source_feasibility import canonical_bytes, sha256_bytes


def fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    cik = "0000000001"
    main = {"cik": cik, "name": "Fixture", "filings": {"files": [], "recent": {
        "accessionNumber": ["a", "b"], "form": ["10-K", "10-K/A"],
        "acceptanceDateTime": ["2014-11-26T19:00:00.000Z", "2014-11-27T19:00:00.000Z"],
        "filingDate": ["2014-11-26", "2014-11-27"],
        "reportDate": ["2013-12-31", "2013-12-31"], "primaryDocument": ["a.htm", "b.htm"]
    }}}
    base = {"end": "2013-12-31", "form": "10-K", "accn": "a", "fy": 2013, "fp": "FY"}
    facts = {"cik": 1, "facts": {"us-gaap": {
        "Assets": {"units": {"USD": [{**base, "val": 100}]}},
        "NetIncomeLoss": {"units": {"USD": [
            {**base, "start": "2013-01-01", "val": 20},
            {**base, "start": "2013-01-01", "accn": "b", "form": "10-K/A", "val": 90}
        ]}}
    }}}
    records = []
    for filename, url, payload in (
        ("main.json", f"https://data.sec.gov/submissions/CIK{cik}.json", main),
        ("facts.json", f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", facts),
    ):
        data = canonical_bytes(payload)
        (tmp_path / filename).write_bytes(data)
        records.append({"url": url, "file": filename, "sha256": sha256_bytes(data)})
    manifest = tmp_path / "access.json"
    manifest.write_bytes(canonical_bytes(records))
    period = tmp_path / "period.json"
    period.write_bytes(canonical_bytes({"monthly_coverage": [{"date": "2014-11-28"}]}))
    return manifest, period, sha256_bytes(period.read_bytes())


def test_real_early_close_latency_hashes_and_immutable_output(tmp_path: Path) -> None:
    pytest.importorskip("exchange_calendars")
    manifest, period, digest = fixture(tmp_path)
    output = tmp_path / "report.json"
    stamp = datetime.fromisoformat("2015-01-01T00:00:00+00:00")
    summary = materialize((manifest,), (tmp_path,), output, stamp,
                          period_path=period, period_sha256=digest)
    report = json.loads(output.read_bytes())
    assert summary["issuer_months"] == 1
    assert report["decision_closes"]["2014-11-28"] == "2014-11-28T18:00:00+00:00"
    ratio = next(row for row in report["monthly"][0]["ratios"]
                 if row["name"] == "annual_net_income_assets")
    assert ratio["value"] == 0.2  # amendment becomes available at 19:00, after 13:00 NY close
    assert report["security_joins_admitted"] == 0
    assert not report["model_fitting_permitted"]
    with pytest.raises(FileExistsError):
        materialize((manifest,), (tmp_path,), output, stamp,
                    period_path=period, period_sha256=digest)


def test_raw_source_tamper_rejected(tmp_path: Path) -> None:
    pytest.importorskip("exchange_calendars")
    manifest, period, digest = fixture(tmp_path)
    (tmp_path / "facts.json").write_text("{}")
    with pytest.raises(ValueError, match="source hash mismatch"):
        materialize((manifest,), (tmp_path,), tmp_path / "out",
                    datetime.fromisoformat("2015-01-01T00:00Z"),
                    period_path=period, period_sha256=digest)
    assert not (tmp_path / "out").exists()


def test_wrong_issuer_rejected(tmp_path: Path) -> None:
    pytest.importorskip("exchange_calendars")
    manifest, period, digest = fixture(tmp_path)
    payload = json.loads((tmp_path / "facts.json").read_bytes())
    payload["cik"] = 2
    data = canonical_bytes(payload)
    (tmp_path / "facts.json").write_bytes(data)
    rows = json.loads(manifest.read_bytes())
    rows[1]["sha256"] = sha256_bytes(data)
    manifest.write_bytes(canonical_bytes(rows))
    with pytest.raises(ValueError, match="issuer mismatch"):
        materialize((manifest,), (tmp_path,), tmp_path / "out",
                    datetime.fromisoformat("2015-01-01T00:00Z"),
                    period_path=period, period_sha256=digest)
