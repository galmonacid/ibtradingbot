"""Causal reference-rate lookup and immutable source normalization."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.data.fx import FXHistory, FXObservation, load_fx_history
from src.data.fx_source import normalize_ecb_archive


def test_lookup_rejects_future_stale_and_missing_metadata() -> None:
    observed = datetime(2026, 1, 2, 14, tzinfo=UTC)
    available = observed + timedelta(hours=10)
    row = FXObservation(observed, available, 0.8)
    history = FXHistory((row,), "test-source", "test-licence", "a" * 64, True)
    with pytest.raises(ValueError, match="causally"):
        history.at(available - timedelta(seconds=1))
    assert history.at(available) == row
    with pytest.raises(ValueError, match="stale"):
        history.at(observed + timedelta(days=4, seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        FXObservation(datetime(2026, 1, 1), available, 0.8)
    with pytest.raises(ValueError, match="before"):
        FXObservation(available, observed, 0.8)
    with pytest.raises(ValueError, match="positive"):
        FXObservation(observed, available, float("nan"))
    with pytest.raises(ValueError, match="source"):
        FXHistory((row,), "", "licence", "a" * 64)
    with pytest.raises(ValueError, match="unique"):
        FXHistory((row, row), "source", "licence", "a" * 64)


def test_ecb_cross_rate_and_lag_are_reproducible(tmp_path: Path) -> None:
    archive = tmp_path / "rates.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "rates.csv", "Date, USD, GBP,\n2026-06-29, 1.2, 0.84,\n2026-06-30, 1.25, 0.875,\n"
        )
    kwargs = dict(
        start=date(2026, 6, 21),
        end=date(2026, 6, 30),
        retrieved_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    result = normalize_ecb_archive(archive, tmp_path / "a", **kwargs)
    second = normalize_ecb_archive(archive, tmp_path / "b", **kwargs)
    assert result == second
    assert result.observations[0].gbp_per_usd == pytest.approx(0.7)
    assert result.observations[0].available_at == datetime(2026, 6, 30, tzinfo=UTC)
    assert result.at(datetime(2026, 6, 30, 13, 30, tzinfo=UTC)) == result.observations[0]
    csv_path = tmp_path / "a" / "fx.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash"):
        load_fx_history(csv_path, tmp_path / "a" / "fx_manifest.json")


def test_ecb_duplicate_and_invalid_rates_fail(tmp_path: Path) -> None:
    archive = tmp_path / "rates.zip"
    for body in ("2026-06-29,1.2,0.84\n2026-06-29,1.2,0.84\n", "2026-06-29,0,0.84\n"):
        with ZipFile(archive, "w") as bundle:
            bundle.writestr("rates.csv", "Date,USD,GBP\n" + body)
        with pytest.raises(ValueError):
            normalize_ecb_archive(
                archive,
                tmp_path / "out",
                start=date(2026, 6, 21),
                end=date(2026, 6, 30),
                retrieved_at=datetime(2026, 9, 22, tzinfo=UTC),
            )


def test_ecb_descending_archive_is_ordered_and_discloses_nonvintage(tmp_path: Path) -> None:
    import json

    archive = tmp_path / "rates.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "rates.csv", "Date,USD,GBP\n2026-06-30,1.25,.875\n2026-01-02,1.2,.84\n"
        )
    retrieved = datetime(2026, 9, 23, tzinfo=UTC)
    history = normalize_ecb_archive(archive, tmp_path / "a", start=date(2026, 1, 1),
                                    end=date(2026, 6, 30), retrieved_at=retrieved)
    normalize_ecb_archive(archive, tmp_path / "b", start=date(2026, 1, 1),
                          end=date(2026, 6, 30), retrieved_at=retrieved)
    for name in ("fx.csv", "fx_manifest.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert history.observations[0].observed_at.utcoffset() == timedelta(hours=1)
    assert history.observations[1].observed_at.utcoffset() == timedelta(hours=2)
    manifest = json.loads((tmp_path / "a" / "fx_manifest.json").read_text())
    assert manifest["vintage_certified"] is False
    assert manifest["usage"] == "development_only_retrospective_reference_archive"
    assert manifest["source_sha256"]


def test_ecb_rate_not_available_at_same_day_us_open(tmp_path: Path) -> None:
    archive = tmp_path / "rates.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("rates.csv", "Date,USD,GBP\n2026-06-30,1.25,.875\n")
    history = normalize_ecb_archive(archive, tmp_path / "out", start=date(2026, 6, 30),
                                    end=date(2026, 6, 30),
                                    retrieved_at=datetime(2026, 9, 23, tzinfo=UTC))
    with pytest.raises(ValueError, match="causally"):
        history.at(datetime(2026, 6, 30, 13, 30, tzinfo=UTC))
    assert history.at(datetime(2026, 7, 1, tzinfo=UTC)).gbp_per_usd == pytest.approx(.7)
    with pytest.raises(ValueError, match="availability"):
        normalize_ecb_archive(archive, tmp_path / "future", start=date(2026, 6, 30),
                              end=date(2026, 6, 30),
                              retrieved_at=datetime(2026, 6, 30, 20, tzinfo=UTC))
