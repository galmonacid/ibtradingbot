from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.config.settings import ConfigurationError, load_config
from src.data.ingest import CANONICAL_COLUMNS, IngestionError, PriceBar, ingest_daily_bars
from src.data.universe import UniverseError, filter_universe, load_seed_universe

ROOT = Path(__file__).parents[1]


def _write_csv(path: Path, rows: list[str], header: str | None = None) -> None:
    path.write_text(
        (header or ",".join(CANONICAL_COLUMNS)) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def _bar(day: date, symbol: str, close: float = 100.0, volume: int = 6_000_000) -> PriceBar:
    return PriceBar(day, symbol, close, close, close, close, close, volume)


def test_ingestion_is_canonical_and_independent_of_row_order(tmp_path: Path) -> None:
    config = load_config(ROOT / "config.example.yaml")
    rows = [
        "2024-01-02,AAPL,100,101,99,100,100,7000000",
        "2024-01-02,MSFT,100,101,99,100,100,6000000",
        "2024-01-03,msft,101,102,100,101,101,6000000",
    ]
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_csv(first, rows)
    _write_csv(second, [rows[1], rows[0], rows[2]])

    result = ingest_daily_bars(first, config)
    reordered = ingest_daily_bars(second, config)

    assert result.bars == reordered.bars
    assert result.quarantined == reordered.quarantined
    assert [(bar.date, bar.symbol) for bar in result.bars] == [
        (date(2024, 1, 2), "AAPL"),
        (date(2024, 1, 2), "MSFT"),
        (date(2024, 1, 3), "MSFT"),
    ]
    assert result.quarantined == ()
    assert len(result.source_sha256) == 64


def test_ingestion_quarantines_bad_rows_and_all_duplicate_occurrences(tmp_path: Path) -> None:
    config = load_config(ROOT / "config.example.yaml")
    path = tmp_path / "quality.csv"
    _write_csv(
        path,
        [
            "2024-01-02,AAPL,100,101,99,100,100,6000000",
            "2024-01-02,AAPL,100,101,99,100,100,6000000",
            "2024-01-03,MSFT,100,98,99,-1,100,0",
            "bad-date,NVDA,nope,101,99,100,100,6000000",
            "2024-01-04,GOOG,100,nan,99,100,100,6000000",
        ],
    )

    result = ingest_daily_bars(path, config)
    reasons = [reason for record in result.quarantined for reason in record.reasons]

    assert result.bars == ()
    assert reasons.count("duplicate_key") == 2
    assert {"non_positive_price", "non_positive_volume", "impossible_ohlc"} <= set(reasons)
    assert {"invalid_date", "invalid_price_type", "non_finite_price"} <= set(reasons)


def test_ingestion_quarantines_temporal_anomalies(tmp_path: Path) -> None:
    config = load_config(ROOT / "config.example.yaml")
    path = tmp_path / "anomalies.csv"
    rows = [
        "2024-01-01,AAPL,100,100,100,100,100,6000000",
        "2024-01-02,AAPL,50,50,50,50,100,12000000",
        "2024-01-01,NVDA,100,100,100,100,100,6000000",
        "2024-01-02,NVDA,170,170,170,170,170,6000000",
    ]
    rows.extend(
        f"2024-01-{day:02d},MSFT,100,100,100,100,100,6000000" for day in range(1, 6)
    )
    _write_csv(path, rows)

    result = ingest_daily_bars(path, config)
    reasons_by_symbol: dict[str, set[str]] = {}
    for record in result.quarantined:
        reasons_by_symbol.setdefault(dict(record.values)["symbol"], set()).update(record.reasons)

    notice_reasons = {
        dict(record.values)["symbol"]: set(record.reasons) for record in result.notices
    }
    assert notice_reasons["AAPL"] == {"adjusted_split_detected"}
    assert "suspicious_adjusted_move" in reasons_by_symbol["NVDA"]
    assert reasons_by_symbol["MSFT"] == {"stale_adjusted_price"}
    assert [(bar.symbol, bar.date) for bar in result.bars] == [
        ("AAPL", date(2024, 1, 1)),
        ("MSFT", date(2024, 1, 1)),
        ("NVDA", date(2024, 1, 1)),
        ("AAPL", date(2024, 1, 2)),
        ("MSFT", date(2024, 1, 2)),
        ("MSFT", date(2024, 1, 3)),
        ("MSFT", date(2024, 1, 4)),
    ]


def test_stale_detection_is_prefix_causal_and_unadjusted_split_is_quarantined(
    tmp_path: Path,
) -> None:
    config = load_config(ROOT / "config.example.yaml")
    four = [
        f"2024-01-{day:02d},AAA,100,100,100,100,100,6000000"
        for day in range(1, 5)
    ]
    prefix = tmp_path / "prefix.csv"
    extended = tmp_path / "extended.csv"
    _write_csv(prefix, four)
    _write_csv(
        extended,
        four
        + [
            "2024-01-05,AAA,100,100,100,100,100,6000000",
            "2024-01-01,BBB,100,100,100,100,100,6000000",
            "2024-01-02,BBB,50,50,50,50,50,12000000",
        ],
    )

    before = ingest_daily_bars(prefix, config)
    after = ingest_daily_bars(extended, config)
    assert tuple(bar for bar in after.bars if bar.symbol == "AAA") == before.bars
    reasons = {
        (dict(record.values)["symbol"], dict(record.values)["date"]): record.reasons
        for record in after.quarantined
    }
    assert reasons[("AAA", "2024-01-05")] == ("stale_adjusted_price",)
    assert "suspicious_adjusted_move" in reasons[("BBB", "2024-01-02")]


def test_ingestion_quarantines_non_monotonic_source_dates(tmp_path: Path) -> None:
    config = load_config(ROOT / "config.example.yaml")
    path = tmp_path / "unordered.csv"
    _write_csv(
        path,
        [
            "2024-01-03,AAPL,100,101,99,100,100,6000000",
            "2024-01-02,AAPL,100,101,99,100,100,6000000",
        ],
    )
    result = ingest_daily_bars(path, config)

    assert [bar.date for bar in result.bars] == [date(2024, 1, 3)]
    assert result.quarantined[0].reasons == ("non_monotonic_date",)


def test_ingestion_rejects_noncanonical_schema(tmp_path: Path) -> None:
    path = tmp_path / "wrong.csv"
    _write_csv(path, [], header="symbol,date")
    with pytest.raises(IngestionError, match="exact canonical"):
        ingest_daily_bars(path, load_config(ROOT / "config.example.yaml"))


def test_seed_universe_is_versioned_and_has_thirty_candidates_plus_spy() -> None:
    config = load_config(ROOT / "config.example.yaml")
    securities = load_seed_universe(ROOT / "data/sample/seed_universe.csv", config)

    assert len([security for security in securities if not security.is_benchmark]) == 30
    assert [security.symbol for security in securities if security.is_benchmark] == ["SPY"]
    assert {security.version for security in securities} == {config.universe_version}


def test_seed_universe_rejects_short_rows_as_domain_errors(tmp_path: Path) -> None:
    path = tmp_path / "short-universe.csv"
    path.write_text(
        "version,symbol,is_benchmark,is_common_stock,primary_listing_us,is_otc,"
        "is_leveraged_or_inverse_etf,isa_eligible\nseed-v1,AAPL,false\n",
        encoding="utf-8",
    )

    with pytest.raises(UniverseError, match="malformed"):
        load_seed_universe(path, load_config(ROOT / "config.example.yaml"))


def test_universe_filter_is_as_of_and_records_every_exclusion_reason() -> None:
    config = load_config(ROOT / "config.example.yaml")
    securities = list(load_seed_universe(ROOT / "data/sample/seed_universe.csv", config))
    aapl_index = next(i for i, security in enumerate(securities) if security.symbol == "AAPL")
    securities[aapl_index] = replace(securities[aapl_index], is_common_stock=False)
    start = date(2023, 1, 1)
    as_of = start + timedelta(days=251)
    bars: list[PriceBar] = []
    bars.extend(_bar(start + timedelta(days=i), "AAPL") for i in range(252))
    bars.extend(_bar(start + timedelta(days=i), "MSFT", close=9.0) for i in range(252))
    bars.extend(_bar(start + timedelta(days=i), "NVDA", volume=1_000) for i in range(252))
    bars.extend(_bar(start + timedelta(days=i), "AMZN") for i in range(251))
    bars.append(_bar(as_of + timedelta(days=1), "MSFT", close=1000.0, volume=100_000_000))

    selection = filter_universe(tuple(reversed(bars)), tuple(securities), as_of, config)
    reasons = {exclusion.symbol: set(exclusion.reasons) for exclusion in selection.exclusions}

    assert selection.eligible_symbols == ()
    assert reasons["AAPL"] == {"not_common_stock"}
    assert "price_below_minimum" in reasons["MSFT"]
    assert "median_dollar_volume_below_minimum" in reasons["NVDA"]
    assert "insufficient_history" in reasons["AMZN"]
    assert reasons["ABBV"] == {"missing_price_history"}
    assert "SPY" not in reasons


def test_universe_filter_accepts_eligible_symbol_and_ignores_future_data() -> None:
    config = load_config(ROOT / "config.example.yaml")
    securities = load_seed_universe(ROOT / "data/sample/seed_universe.csv", config)
    start = date(2023, 1, 1)
    as_of = start + timedelta(days=251)
    history = tuple(_bar(start + timedelta(days=i), "AAPL") for i in range(252))
    baseline = filter_universe(history, securities, as_of, config)
    future_bad_bar = _bar(as_of + timedelta(days=1), "AAPL", close=1.0, volume=1)

    with_future = filter_universe(history + (future_bad_bar,), securities, as_of, config)

    assert baseline.eligible_symbols == ("AAPL",)
    assert with_future == baseline

    stale = filter_universe(history[:-1], securities, as_of, config)
    aapl = next(item for item in stale.exclusions if item.symbol == "AAPL")
    assert "missing_current_bar" in aapl.reasons


@pytest.mark.parametrize("session_count,missing_index", [(253, 200), (260, 3)])
def test_universe_filter_excludes_internal_gap_in_required_session_window(
    session_count: int, missing_index: int
) -> None:
    config = load_config(ROOT / "config.example.yaml")
    securities = load_seed_universe(ROOT / "data/sample/seed_universe.csv", config)
    start = date(2023, 1, 1)
    sessions = [start + timedelta(days=index) for index in range(session_count)]
    bars = tuple(
        [_bar(session, "SPY") for session in sessions]
        + [
            _bar(session, "AAPL")
            for index, session in enumerate(sessions)
            if index != missing_index
        ]
    )

    selection = filter_universe(bars, securities, sessions[-1], config)
    aapl = next(item for item in selection.exclusions if item.symbol == "AAPL")

    assert "missing_session_history" in aapl.reasons
    assert "AAPL" not in selection.eligible_symbols


def test_phase1_config_accessors_and_validation(tmp_path: Path) -> None:
    config = load_config(ROOT / "config.example.yaml")
    assert config.momentum_weights == (0.35, 0.35, 0.30)
    assert config.ranking_weights == (0.65, 0.30)
    assert config.transaction_costs == (0.35, 5.0, 5.0)

    source = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(
        source.replace("momentum_weight: 0.65", "momentum_weight: 0.90"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="momentum_weight"):
        load_config(invalid)
