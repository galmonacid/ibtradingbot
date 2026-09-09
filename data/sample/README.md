# Sample daily bars

`daily_bars.csv` is a small, fixed engineering fixture. It has the Phase 0
daily-OHLCV schema and basic internally consistent values so the bootstrap
pipeline can validate local input deterministically.

It is not a point-in-time investment universe, a complete market-data source,
or suitable for research, backtesting, or performance claims. No prices are
downloaded, inferred, repaired, or forward-filled by the Phase 0 pipeline.

`research_daily_bars.csv` is a deterministic synthetic Phase 1 fixture created
by `generate_research_fixture.py`. It is long enough to exercise rolling
features, delayed signals, accounting, and reporting, but it is still not real
market data and cannot support a performance or investment claim.

`us_sessions.csv` is the matching versioned XNYS engineering calendar. Its
explicit week-end flags let the research pipeline handle exchange holidays and
truncated price histories without inferring schedules from future price rows.
