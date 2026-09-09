from pathlib import Path

import pytest

from src.data.quality import DataQualityError, validate_daily_bars

ROOT = Path(__file__).parents[1]


def test_checked_in_fixture_validates() -> None:
    summary = validate_daily_bars(ROOT / "data/sample/daily_bars.csv")

    assert summary.row_count == 6
    assert summary.symbols == ("AAPL", "MSFT", "SPY")
    assert (summary.first_date, summary.last_date) == ("2024-01-02", "2024-01-03")


def test_impossible_ohlc_is_rejected(tmp_path: Path) -> None:
    data = "date,symbol,open,high,low,close,adjusted_close,volume\n2024-01-02,AAA,10,9,8,10,10,1\n"
    path = tmp_path / "bad.csv"
    path.write_text(data, encoding="utf-8")

    with pytest.raises(DataQualityError, match="impossible OHLC"):
        validate_daily_bars(path)


def test_non_finite_prices_and_non_monotonic_dates_are_rejected(tmp_path: Path) -> None:
    data = (
        "date,symbol,open,high,low,close,adjusted_close,volume\n2024-01-03,AAA,nan,11,9,10,10,1\n"
    )
    path = tmp_path / "nan.csv"
    path.write_text(data, encoding="utf-8")
    with pytest.raises(DataQualityError, match="non-finite"):
        validate_daily_bars(path)

    ordered = (
        "date,symbol,open,high,low,close,adjusted_close,volume\n"
        "2024-01-03,AAA,10,11,9,10,10,1\n"
        "2024-01-02,AAA,10,11,9,10,10,1\n"
    )
    path.write_text(ordered, encoding="utf-8")
    with pytest.raises(DataQualityError, match="non-monotonic"):
        validate_daily_bars(path)
