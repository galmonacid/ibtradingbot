"""Versioned seed-universe metadata and point-in-time eligibility filtering."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.config.settings import AppConfig
from src.data.ingest import PriceBar

UNIVERSE_COLUMNS = (
    "version",
    "symbol",
    "is_benchmark",
    "is_common_stock",
    "primary_listing_us",
    "is_otc",
    "is_leveraged_or_inverse_etf",
    "isa_eligible",
)
# The longest mandatory Phase 1 feature is a 252-session return observed with
# a five-session skip: current endpoint + 252 lookback + 5 skipped sessions.
MANDATORY_FEATURE_HISTORY_SESSIONS = 258


class UniverseError(ValueError):
    """Raised when versioned universe metadata is missing or inconsistent."""


@dataclass(frozen=True, order=True)
class UniverseSecurity:
    version: str
    symbol: str
    is_benchmark: bool
    is_common_stock: bool
    primary_listing_us: bool
    is_otc: bool
    is_leveraged_or_inverse_etf: bool
    isa_eligible: bool


@dataclass(frozen=True, order=True)
class UniverseExclusion:
    symbol: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class UniverseSelection:
    version: str
    as_of: date
    benchmark: str
    eligible_symbols: tuple[str, ...]
    exclusions: tuple[UniverseExclusion, ...]


def _flag(value: str, field: str, line_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise UniverseError(f"{field} must be true or false on line {line_number}")


def load_seed_universe(path: Path, config: AppConfig) -> tuple[UniverseSecurity, ...]:
    """Load and validate immutable metadata for the fixed engineering universe."""
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise UniverseError(f"cannot read seed universe {path}: {error}") from error
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != UNIVERSE_COLUMNS:
            raise UniverseError("seed universe must use the exact canonical column order")
        securities: list[UniverseSecurity] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise UniverseError(f"malformed seed universe row on line {line_number}")
            symbol = row["symbol"].strip().upper()
            version = row["version"].strip()
            if not symbol or not version:
                raise UniverseError(f"blank symbol or version on line {line_number}")
            securities.append(
                UniverseSecurity(
                    version=version,
                    symbol=symbol,
                    is_benchmark=_flag(row["is_benchmark"], "is_benchmark", line_number),
                    is_common_stock=_flag(row["is_common_stock"], "is_common_stock", line_number),
                    primary_listing_us=_flag(
                        row["primary_listing_us"], "primary_listing_us", line_number
                    ),
                    is_otc=_flag(row["is_otc"], "is_otc", line_number),
                    is_leveraged_or_inverse_etf=_flag(
                        row["is_leveraged_or_inverse_etf"],
                        "is_leveraged_or_inverse_etf",
                        line_number,
                    ),
                    isa_eligible=_flag(row["isa_eligible"], "isa_eligible", line_number),
                )
            )
    symbols = [security.symbol for security in securities]
    if len(symbols) != len(set(symbols)):
        raise UniverseError("seed universe contains duplicate symbols")
    if any(security.version != config.universe_version for security in securities):
        raise UniverseError("seed universe version does not match configuration")
    benchmarks = [security for security in securities if security.is_benchmark]
    if len(benchmarks) != 1 or benchmarks[0].symbol != config.benchmark:
        raise UniverseError("seed universe must contain exactly the configured benchmark")
    candidate_count = sum(not security.is_benchmark for security in securities)
    if not 30 <= candidate_count <= config.universe_max_symbols:
        raise UniverseError("seed universe must contain 30 to configured max candidate symbols")
    return tuple(sorted(securities, key=lambda security: security.symbol))


def filter_universe(
    bars: tuple[PriceBar, ...],
    securities: tuple[UniverseSecurity, ...],
    as_of: date,
    config: AppConfig,
) -> UniverseSelection:
    """Filter the seed universe using only observations available through ``as_of``."""
    histories: dict[str, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        if bar.date <= as_of:
            histories[bar.symbol].append(bar)
    for history in histories.values():
        history.sort(key=lambda bar: bar.date)
    benchmark_history = histories.get(config.benchmark, [])
    required_history = max(
        config.minimum_history_sessions,
        MANDATORY_FEATURE_HISTORY_SESSIONS,
    )
    required_count = min(required_history, len(benchmark_history))
    required_session_dates = {bar.date for bar in benchmark_history[-required_count:]}

    eligible: list[str] = []
    exclusions: list[UniverseExclusion] = []
    for security in sorted(securities, key=lambda item: item.symbol):
        if security.is_benchmark:
            continue
        reasons: list[str] = []
        if not security.is_common_stock:
            reasons.append("not_common_stock")
        if not security.primary_listing_us:
            reasons.append("not_primary_us_listing")
        if security.is_otc:
            reasons.append("otc_security")
        if security.is_leveraged_or_inverse_etf:
            reasons.append("leveraged_or_inverse_etf")
        if not security.isa_eligible:
            reasons.append("not_isa_eligible")

        history = histories.get(security.symbol, [])
        if not history:
            reasons.append("missing_price_history")
        else:
            if history[-1].date != as_of:
                reasons.append("missing_current_bar")
            if len(history) < config.minimum_history_sessions:
                reasons.append("insufficient_history")
            elif len(required_session_dates) >= config.minimum_history_sessions:
                observed_dates = {bar.date for bar in history}
                if not required_session_dates.issubset(observed_dates):
                    reasons.append("missing_session_history")
            if history[-1].close < config.minimum_price_usd:
                reasons.append("price_below_minimum")
            if len(history) < 20:
                reasons.append("insufficient_liquidity_history")
            else:
                dollar_volumes = [bar.close * bar.volume for bar in history[-20:]]
                if statistics.median(dollar_volumes) < config.minimum_median_dollar_volume_20d:
                    reasons.append("median_dollar_volume_below_minimum")
        if reasons:
            exclusions.append(UniverseExclusion(security.symbol, tuple(sorted(reasons))))
        else:
            eligible.append(security.symbol)

    return UniverseSelection(
        version=config.universe_version,
        as_of=as_of,
        benchmark=config.benchmark,
        eligible_symbols=tuple(eligible),
        exclusions=tuple(exclusions),
    )
