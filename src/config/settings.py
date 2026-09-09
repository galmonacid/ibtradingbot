"""Typed loading and safety validation for repository configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Raised when a YAML configuration is incomplete or violates safety limits."""


@dataclass(frozen=True)
class AppConfig:
    """Validated configuration with typed Phase 1 accessors and provenance hash."""

    values: dict[str, Any]
    sha256: str

    @property
    def timezone(self) -> str:
        return str(self.values["project"]["timezone"])

    def _section(self, name: str) -> dict[str, Any]:
        return _require_mapping(self.values[name], name)

    @property
    def benchmark(self) -> str:
        return str(self._section("universe")["benchmark"])

    @property
    def universe_version(self) -> str:
        return str(self._section("universe")["version"])

    @property
    def universe_max_symbols(self) -> int:
        return int(self._section("universe")["max_symbols"])

    @property
    def minimum_price_usd(self) -> float:
        return float(self._section("universe")["min_price_usd"])

    @property
    def minimum_median_dollar_volume_20d(self) -> float:
        return float(self._section("universe")["min_median_dollar_volume_20d"])

    @property
    def minimum_history_sessions(self) -> int:
        return int(self._section("universe")["min_history_sessions"])

    @property
    def suspicious_adjusted_move(self) -> float:
        return float(self._section("data_quality")["suspicious_adjusted_move"])

    @property
    def stale_adjusted_price_sessions(self) -> int:
        return int(self._section("data_quality")["stale_adjusted_price_sessions"])

    @property
    def likely_split_min_ratio(self) -> float:
        return float(self._section("data_quality")["likely_split_min_ratio"])

    @property
    def likely_split_adjusted_tolerance(self) -> float:
        return float(self._section("data_quality")["likely_split_adjusted_tolerance"])

    @property
    def momentum_weights(self) -> tuple[float, float, float]:
        momentum = _require_mapping(self._section("strategy")["momentum"], "strategy.momentum")
        return (
            float(momentum["lookback_63d_weight"]),
            float(momentum["lookback_126d_weight"]),
            float(momentum["lookback_252d_weight"]),
        )

    @property
    def skip_recent_days(self) -> int:
        momentum = _require_mapping(self._section("strategy")["momentum"], "strategy.momentum")
        return int(momentum["skip_recent_days"])

    @property
    def trend_windows(self) -> tuple[int, int, int]:
        trend = _require_mapping(self._section("strategy")["trend"], "strategy.trend")
        return int(trend["sma_fast"]), int(trend["sma_medium"]), int(trend["sma_slow"])

    @property
    def ranking_penalties(self) -> tuple[float, float]:
        penalties = _require_mapping(self._section("strategy")["penalties"], "strategy.penalties")
        return float(penalties["volatility_weight"]), float(penalties["drawdown_weight"])

    @property
    def ranking_weights(self) -> tuple[float, float]:
        ranking = _require_mapping(self._section("strategy")["ranking"], "strategy.ranking")
        return float(ranking["momentum_weight"]), float(ranking["trend_weight"])

    @property
    def regime_thresholds(self) -> tuple[float, float, float]:
        regime = self._section("regime")
        return (
            float(regime["risk_on_breadth_threshold"]),
            float(regime["neutral_breadth_threshold"]),
            float(regime["high_vol_percentile"]),
        )

    @property
    def transaction_costs(self) -> tuple[float, float, float]:
        costs = self._section("costs")
        return (
            float(costs["commission_per_order_usd"]),
            float(costs["slippage_bps_each_side"]),
            float(costs["fx_buffer_bps"]),
        )


def _require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{name} must be a mapping")
    return value


def _number(section: dict[str, Any], key: str, section_name: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationError(f"{section_name}.{key} must be a number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ConfigurationError(f"{section_name}.{key} must be finite")
    return numeric


def _integer(section: dict[str, Any], key: str, section_name: str) -> int:
    value = section.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{section_name}.{key} must be an integer")
    return value


def _validate(values: dict[str, Any]) -> None:
    for section_name in (
        "project",
        "calendar",
        "corporate_actions",
        "universe",
        "data_quality",
        "strategy",
        "regime",
        "portfolio",
        "risk",
        "execution",
        "costs",
        "ml",
    ):
        _require_mapping(values.get(section_name), section_name)

    project = _require_mapping(values["project"], "project")
    if not isinstance(project.get("name"), str) or not project["name"].strip():
        raise ConfigurationError("project.name must be a non-empty string")
    if not isinstance(project.get("timezone"), str) or not project["timezone"].strip():
        raise ConfigurationError("project.timezone must be a non-empty string")

    calendar = _require_mapping(values["calendar"], "calendar")
    for key in ("exchange", "version"):
        if not isinstance(calendar.get(key), str) or not calendar[key].strip():
            raise ConfigurationError(f"calendar.{key} must be a non-empty string")

    corporate_actions = _require_mapping(values["corporate_actions"], "corporate_actions")
    if (
        not isinstance(corporate_actions.get("version"), str)
        or not corporate_actions["version"].strip()
    ):
        raise ConfigurationError("corporate_actions.version must be a non-empty string")

    strategy = _require_mapping(values["strategy"], "strategy")
    if strategy.get("rebalance_frequency") != "weekly":
        raise ConfigurationError("strategy.rebalance_frequency must be weekly in Phase 1")
    if strategy.get("rebalance_day") != "Friday":
        raise ConfigurationError("strategy.rebalance_day must be Friday in Phase 1")
    min_positions = _integer(strategy, "min_positions", "strategy")
    target_positions = _integer(strategy, "target_positions", "strategy")
    max_positions = _integer(strategy, "max_positions", "strategy")
    if not 0 <= min_positions <= target_positions <= max_positions <= 5:
        raise ConfigurationError("strategy positions must satisfy 0 <= min <= target <= max <= 5")
    if min_positions != 0:
        raise ConfigurationError("strategy.min_positions must be 0 in Phase 1")

    universe = _require_mapping(values["universe"], "universe")
    if universe.get("source") != "fixed_seed":
        raise ConfigurationError("universe.source must be fixed_seed in Phase 1")
    for key in ("version", "benchmark"):
        if not isinstance(universe.get(key), str) or not universe[key].strip():
            raise ConfigurationError(f"universe.{key} must be a non-empty string")
    max_symbols = _integer(universe, "max_symbols", "universe")
    if not 30 <= max_symbols <= 50:
        raise ConfigurationError("universe.max_symbols must be between 30 and 50")
    if _number(universe, "min_price_usd", "universe") <= 0:
        raise ConfigurationError("universe.min_price_usd must be positive")
    if _number(universe, "min_median_dollar_volume_20d", "universe") <= 0:
        raise ConfigurationError("universe.min_median_dollar_volume_20d must be positive")
    if _integer(universe, "min_history_sessions", "universe") < 252:
        raise ConfigurationError("universe.min_history_sessions must be at least 252")
    if universe.get("require_primary_listing_us") is not True:
        raise ConfigurationError("universe.require_primary_listing_us must be true")

    data_quality = _require_mapping(values["data_quality"], "data_quality")
    suspicious_move = _number(data_quality, "suspicious_adjusted_move", "data_quality")
    stale_sessions = _integer(data_quality, "stale_adjusted_price_sessions", "data_quality")
    split_ratio = _number(data_quality, "likely_split_min_ratio", "data_quality")
    split_tolerance = _number(data_quality, "likely_split_adjusted_tolerance", "data_quality")
    if not 0 < suspicious_move < 1:
        raise ConfigurationError("data_quality.suspicious_adjusted_move must be in (0, 1)")
    if stale_sessions < 2:
        raise ConfigurationError("data_quality.stale_adjusted_price_sessions must be at least 2")
    if split_ratio <= 1:
        raise ConfigurationError("data_quality.likely_split_min_ratio must exceed 1")
    if not 0 <= split_tolerance < 1:
        raise ConfigurationError("data_quality.likely_split_adjusted_tolerance must be in [0, 1)")

    momentum = _require_mapping(strategy.get("momentum"), "strategy.momentum")
    momentum_weights = [
        _number(momentum, key, "strategy.momentum")
        for key in ("lookback_63d_weight", "lookback_126d_weight", "lookback_252d_weight")
    ]
    if any(weight < 0 for weight in momentum_weights) or abs(sum(momentum_weights) - 1) > 1e-12:
        raise ConfigurationError("strategy.momentum weights must be non-negative and sum to 1")
    if _integer(momentum, "skip_recent_days", "strategy.momentum") != 5:
        raise ConfigurationError("strategy.momentum.skip_recent_days must be 5 in Phase 1")
    trend = _require_mapping(strategy.get("trend"), "strategy.trend")
    trend_windows = [
        _integer(trend, key, "strategy.trend")
        for key in ("sma_fast", "sma_medium", "sma_slow")
    ]
    if not 0 < trend_windows[0] < trend_windows[1] < trend_windows[2]:
        raise ConfigurationError("strategy trend windows must be positive and strictly increasing")
    if trend_windows != [50, 100, 200]:
        raise ConfigurationError("strategy trend windows must be 50, 100, and 200 in Phase 1")
    if trend.get("require_price_above_sma200") is not True:
        raise ConfigurationError("strategy.trend.require_price_above_sma200 must be true")
    penalties = _require_mapping(strategy.get("penalties"), "strategy.penalties")
    if not 0.10 <= _number(penalties, "volatility_weight", "strategy.penalties") <= 0.30:
        raise ConfigurationError("strategy.penalties.volatility_weight must be in [0.10, 0.30]")
    if not 0.05 <= _number(penalties, "drawdown_weight", "strategy.penalties") <= 0.25:
        raise ConfigurationError("strategy.penalties.drawdown_weight must be in [0.05, 0.25]")
    ranking = _require_mapping(strategy.get("ranking"), "strategy.ranking")
    if not 0.50 <= _number(ranking, "momentum_weight", "strategy.ranking") <= 0.80:
        raise ConfigurationError("strategy.ranking.momentum_weight must be in [0.50, 0.80]")
    if not 0.15 <= _number(ranking, "trend_weight", "strategy.ranking") <= 0.40:
        raise ConfigurationError("strategy.ranking.trend_weight must be in [0.15, 0.40]")

    regime = _require_mapping(values["regime"], "regime")
    if regime.get("benchmark") != universe["benchmark"]:
        raise ConfigurationError("regime.benchmark must equal universe.benchmark")
    if _integer(regime, "sma_slow", "regime") != 200:
        raise ConfigurationError("regime.sma_slow must be 200 in Phase 1")
    if _integer(regime, "breadth_lookback", "regime") != 200:
        raise ConfigurationError("regime.breadth_lookback must be 200 in Phase 1")
    if _integer(regime, "volatility_lookback", "regime") < 1:
        raise ConfigurationError("regime.volatility_lookback must be positive")
    risk_on = _number(regime, "risk_on_breadth_threshold", "regime")
    neutral = _number(regime, "neutral_breadth_threshold", "regime")
    high_vol = _number(regime, "high_vol_percentile", "regime")
    if not 0 <= neutral < risk_on <= 1:
        raise ConfigurationError(
            "regime breadth thresholds must satisfy 0 <= neutral < risk_on <= 1"
        )
    if not 0 < high_vol < 1:
        raise ConfigurationError("regime.high_vol_percentile must be in (0, 1)")

    portfolio = _require_mapping(values["portfolio"], "portfolio")
    max_position_weight = _number(portfolio, "max_position_weight", "portfolio")
    min_position_weight = _number(portfolio, "min_position_weight", "portfolio")
    cash_buffer = _number(portfolio, "cash_buffer", "portfolio")
    exposures = [
        _number(portfolio, f"max_gross_exposure_{regime}", "portfolio")
        for regime in ("risk_on", "neutral", "risk_off")
    ]
    risk_on_exposure, neutral_exposure, risk_off_exposure = exposures
    if not 0 <= max_position_weight <= 0.30:
        raise ConfigurationError("portfolio.max_position_weight must be between 0 and 0.30")
    if not 0 <= min_position_weight <= max_position_weight:
        raise ConfigurationError("portfolio position weights must satisfy 0 <= min <= max")
    if min_position_weight != 0.10:
        raise ConfigurationError("portfolio.min_position_weight must be 0.10 in Phase 1")
    if not 0.02 <= cash_buffer < 1:
        raise ConfigurationError("portfolio.cash_buffer must be in [0.02, 1)")
    if not all(0 <= exposure <= 1.0 for exposure in exposures):
        raise ConfigurationError("portfolio gross exposures must be between 0 and 1")
    if not risk_off_exposure <= neutral_exposure <= risk_on_exposure:
        raise ConfigurationError("portfolio exposures must satisfy risk_off <= neutral <= risk_on")
    if risk_off_exposure != 0.0:
        raise ConfigurationError("portfolio.max_gross_exposure_risk_off must be 0")
    # Exposure is a ceiling; portfolio construction (Phase 2) is responsible for
    # allocating beneath it while retaining the configured cash buffer.

    risk = _require_mapping(values["risk"], "risk")
    if _number(risk, "max_portfolio_drawdown_hard", "risk") != 0.15:
        raise ConfigurationError("risk.max_portfolio_drawdown_hard must remain 0.15")

    execution = _require_mapping(values["execution"], "execution")
    if execution.get("allow_short") is not False:
        raise ConfigurationError("execution.allow_short must be false")
    if execution.get("allow_margin") is not False:
        raise ConfigurationError("execution.allow_margin must be false")
    if execution.get("allow_fractional_shares") is not True:
        raise ConfigurationError("execution.allow_fractional_shares must be true in Phase 1")

    costs = _require_mapping(values["costs"], "costs")
    for key in ("commission_per_order_usd", "slippage_bps_each_side", "fx_buffer_bps"):
        if _number(costs, key, "costs") < 0:
            raise ConfigurationError(f"costs.{key} must be non-negative")
    if _number(costs, "slippage_bps_each_side", "costs") >= 10_000:
        raise ConfigurationError("costs.slippage_bps_each_side must be below 10000")

    ml = _require_mapping(values["ml"], "ml")
    if ml.get("enabled") is not False:
        raise ConfigurationError("ml.enabled must remain false in Phase 1")


def load_config(path: Path) -> AppConfig:
    """Load an application YAML file and validate its Phase 0 safety envelope."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ConfigurationError(f"cannot read configuration {path}: {error}") from error
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"invalid YAML in {path}: {error}") from error
    values = _require_mapping(loaded, "root configuration")
    _validate(values)
    return AppConfig(values=values, sha256=sha256(raw).hexdigest())
