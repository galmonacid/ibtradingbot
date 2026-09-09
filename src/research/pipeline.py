"""Phase 1 orchestration without network or broker side effects."""

from __future__ import annotations

import math
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.backtest.costs import CostModel
from src.backtest.engine import PriceBar as BacktestBar
from src.backtest.engine import Trade, run_backtest
from src.backtest.metrics import (
    TradeOutcome,
    benchmark_relative_metrics,
    performance_metrics,
)
from src.config.settings import AppConfig, load_config
from src.data.calendar import (
    CalendarError,
    load_trading_calendar,
    weekly_signal_dates,
)
from src.data.corporate_actions import CorporateActionsError, load_corporate_actions
from src.data.ingest import IngestionError, ingest_daily_bars
from src.data.universe import UniverseError, filter_universe, load_seed_universe
from src.features import Regime, RegimeParameters, build_features, classify_regimes
from src.portfolio import build_equal_weight_targets
from src.strategy import RankingParameters, rank_features

STRATEGY_VERSION = "phase1-deterministic-v1"


class ResearchError(ValueError):
    """Raised when research cannot safely produce an admissible result."""


def _trade_outcomes(trades: Sequence[Trade]) -> tuple[TradeOutcome, ...]:
    # A buy creates a FIFO lot whose basis includes every cash cost paid on
    # entry. A sell may realize several outcomes, with exit costs allocated by
    # shares across the consumed lots.
    lots: dict[str, list[tuple[float, float, date]]] = {}
    outcomes: list[TradeOutcome] = []
    for trade in trades:
        if trade.side == "buy":
            lots.setdefault(trade.symbol, []).append(
                (
                    trade.shares,
                    trade.gross_notional + trade.commission + trade.fx_cost,
                    trade.date,
                )
            )
            continue
        symbol_lots = lots.get(trade.symbol, [])
        if not symbol_lots or trade.shares <= 0.0:
            continue
        total_net_proceeds = trade.gross_notional - trade.commission - trade.fx_cost
        remaining_to_close = trade.shares
        while remaining_to_close > 1e-12 and symbol_lots:
            lot_shares, lot_basis, opened = symbol_lots[0]
            closed_shares = min(remaining_to_close, lot_shares)
            closed_fraction = closed_shares / lot_shares
            closed_basis = lot_basis * closed_fraction
            allocated_proceeds = total_net_proceeds * closed_shares / trade.shares
            outcomes.append(
                TradeOutcome(
                    allocated_proceeds / closed_basis - 1.0,
                    (trade.date - opened).days,
                    allocated_proceeds - closed_basis,
                )
            )
            remaining_to_close -= closed_shares
            remaining_lot_shares = lot_shares - closed_shares
            if remaining_lot_shares <= 1e-12:
                symbol_lots.pop(0)
            else:
                symbol_lots[0] = (
                    remaining_lot_shares,
                    lot_basis - closed_basis,
                    opened,
                )
        if not symbol_lots:
            lots.pop(trade.symbol, None)
    return tuple(outcomes)


def _git_revision(root: Path) -> tuple[str, bool]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable", True
    return revision, dirty


def _exposures(config: AppConfig) -> dict[str, float]:
    section = config.values["portfolio"]
    assert isinstance(section, dict)
    return {
        name: float(section[f"max_gross_exposure_{name}"])
        for name in ("risk_on", "neutral", "risk_off")
    }


def _ranking_parameters(config: AppConfig) -> RankingParameters:
    momentum = config.momentum_weights
    momentum_total, trend = config.ranking_weights
    volatility, drawdown = config.ranking_penalties
    return RankingParameters(
        momentum_63_weight=momentum[0],
        momentum_126_weight=momentum[1],
        momentum_252_weight=momentum[2],
        momentum_total_weight=momentum_total,
        trend_weight=trend,
        volatility_penalty=volatility,
        drawdown_penalty=drawdown,
    )


def _regime_parameters(config: AppConfig) -> RegimeParameters:
    risk_on, neutral, high_vol = config.regime_thresholds
    section = config.values["regime"]
    assert isinstance(section, dict)
    return RegimeParameters(
        risk_on_breadth=risk_on,
        neutral_breadth=neutral,
        high_vol_percentile=high_vol,
        min_vol_history=int(section["volatility_lookback"]),
    )


def _serialize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items()}


def run_research(
    config_path: Path,
    data_path: Path,
    universe_path: Path,
    calendar_path: Path,
    corporate_actions_path: Path,
    *,
    initial_cash: float = 100_000.0,
    run_timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Run the Phase 1 engineering baseline and return a JSON-ready report."""

    if not math.isfinite(initial_cash) or initial_cash <= 0.0:
        raise ResearchError("initial cash must be finite and positive")
    config = load_config(config_path)
    try:
        ingestion = ingest_daily_bars(data_path, config)
        securities = load_seed_universe(universe_path, config)
        calendar = load_trading_calendar(calendar_path)
        corporate_actions = load_corporate_actions(corporate_actions_path)
    except (IngestionError, UniverseError, CalendarError, CorporateActionsError) as error:
        raise ResearchError(str(error)) from error
    if ingestion.quarantined:
        reasons = sorted({reason for row in ingestion.quarantined for reason in row.reasons})
        raise ResearchError(
            f"research input contains {len(ingestion.quarantined)} quarantined rows: "
            + ", ".join(reasons)
        )

    benchmark_sessions = sorted(
        {bar.date for bar in ingestion.bars if bar.symbol == config.benchmark}
    )
    if not benchmark_sessions:
        raise ResearchError(f"benchmark {config.benchmark} has no valid price bars")
    calendar_config = config.values["calendar"]
    assert isinstance(calendar_config, dict)
    if (
        calendar.exchange != calendar_config["exchange"]
        or calendar.version != calendar_config["version"]
    ):
        raise ResearchError("trading calendar metadata does not match configuration")
    calendar_in_range = tuple(
        session
        for session in calendar.sessions
        if benchmark_sessions[0] <= session <= benchmark_sessions[-1]
    )
    if tuple(benchmark_sessions) != calendar_in_range:
        raise ResearchError("benchmark sessions do not match the supplied trading calendar")
    benchmark_session_set = set(benchmark_sessions)
    extra_bar_dates = sorted({bar.date for bar in ingestion.bars} - benchmark_session_set)
    if extra_bar_dates:
        raise ResearchError(
            "non-benchmark bars contain sessions absent from the benchmark: "
            + ", ".join(session.isoformat() for session in extra_bar_dates[:5])
        )
    security_symbols = {security.symbol for security in securities}
    bar_keys = {(bar.date, bar.symbol) for bar in ingestion.bars}
    for event in corporate_actions.delistings:
        if event.symbol not in security_symbols:
            raise ResearchError(f"corporate action has unknown symbol {event.symbol}")
        if event.date not in set(calendar.sessions):
            raise ResearchError("corporate action date is absent from the trading calendar")
        if not benchmark_sessions[0] <= event.date <= benchmark_sessions[-1]:
            raise ResearchError("corporate action is outside the research data period")
        if (event.date, event.symbol) in bar_keys:
            raise ResearchError("delisting event conflicts with a price bar on the same date")
    universe_by_date = {
        session: filter_universe(ingestion.bars, securities, session, config)
        for session in benchmark_sessions
    }
    features = build_features(
        ingestion.bars,
        benchmark=config.benchmark,
        eligible_symbols_by_date={
            session: selection.eligible_symbols
            for session, selection in universe_by_date.items()
        },
    )
    regimes = {
        row.date: row
        for row in classify_regimes(
            features,
            benchmark=config.benchmark,
            parameters=_regime_parameters(config),
        )
    }
    targets: dict[date, dict[str, float]] = {}
    signal_report: list[dict[str, Any]] = []
    portfolio = config.values["portfolio"]
    strategy = config.values["strategy"]
    assert isinstance(portfolio, dict) and isinstance(strategy, dict)
    exposure_by_regime = _exposures(config)
    for signal_date in weekly_signal_dates(tuple(benchmark_sessions), calendar):
        universe = universe_by_date[signal_date]
        allowed = set(universe.eligible_symbols)
        rows = tuple(
            row
            for row in features
            if row.date == signal_date and (row.symbol in allowed or row.symbol == config.benchmark)
        )
        ranked_symbols: list[str] = []
        ranking_exclusions: list[dict[str, str]] = []
        if allowed:
            ranking = rank_features(
                rows,
                as_of_date=signal_date,
                benchmark=config.benchmark,
                parameters=_ranking_parameters(config),
            )
            ranked_symbols = [item.symbol for item in ranking.ranked]
            ranking_exclusions = [asdict(item) for item in ranking.exclusions]
        regime_row = regimes.get(signal_date)
        regime = Regime.NEUTRAL if regime_row is None else regime_row.regime
        target = build_equal_weight_targets(
            ranked_symbols,
            target_positions=int(strategy["target_positions"]),
            regime_ceiling=exposure_by_regime[str(regime)],
            cash_buffer=float(portfolio["cash_buffer"]),
            max_position_weight=float(portfolio["max_position_weight"]),
            max_positions=int(strategy["max_positions"]),
        )
        targets[signal_date] = target
        signal_report.append(
            {
                "date": signal_date.isoformat(),
                "regime": str(regime),
                "ranked": ranked_symbols,
                "target_weights": target,
                "universe_exclusions": [asdict(item) for item in universe.exclusions],
                "ranking_exclusions": ranking_exclusions,
            }
        )

    backtest_bars = tuple(
        BacktestBar(bar.date, bar.symbol, bar.open, bar.close, bar.adjusted_close)
        for bar in ingestion.bars
    )
    commission, slippage, fx_buffer = config.transaction_costs
    result = run_backtest(
        backtest_bars,
        targets,
        initial_cash=initial_cash,
        costs=CostModel(commission, slippage, fx_buffer),
        delistings=corporate_actions.delistings,
        cash_buffer=float(portfolio["cash_buffer"]),
        max_position_weight=float(portfolio["max_position_weight"]),
        max_positions=int(strategy["max_positions"]),
    )
    actionable_signals = [session for session, weights in targets.items() if weights]
    reporting_start = (
        min(actionable_signals) if actionable_signals else result.equity_curve[0].date
    )
    reporting_curve = tuple(
        point for point in result.equity_curve if point.date >= reporting_start
    )
    dates = [point.date for point in reporting_curve]
    values = [point.equity for point in reporting_curve]
    exposures = [point.gross_exposure for point in reporting_curve]
    outcomes = _trade_outcomes(result.trades)
    traded_notional = sum(trade.gross_notional for trade in result.trades)
    strategy_metrics = performance_metrics(
        dates,
        values,
        trade_outcomes=outcomes,
        traded_notional=traded_notional,
        exposures=exposures,
    )

    spy_close = {
        bar.date: bar.adjusted_close
        for bar in ingestion.bars
        if bar.symbol == config.benchmark
    }
    if any(session not in spy_close for session in dates):
        raise ResearchError("benchmark is missing one or more strategy sessions")
    first_spy = spy_close[dates[0]]
    benchmark_values = [initial_cash * spy_close[session] / first_spy for session in dates]
    cash_values = [initial_cash for _session in dates]
    benchmark_metrics = performance_metrics(dates, benchmark_values)
    cash_metrics = performance_metrics(dates, cash_values)
    relative_metrics = benchmark_relative_metrics(dates, values, benchmark_values)

    timestamp = run_timestamp or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ResearchError("run timestamp must be timezone-aware")
    root = Path(__file__).parents[2]
    revision, dirty = _git_revision(root)
    universe_bytes = universe_path.read_bytes()
    total_commission = sum(trade.commission for trade in result.trades)
    total_slippage = sum(trade.slippage_cost for trade in result.trades)
    total_fx = sum(trade.fx_cost for trade in result.trades)
    return {
        "label": "synthetic fixed-universe engineering validation; not a performance claim",
        "provenance": {
            "git_revision": revision,
            "git_dirty": dirty,
            "config_sha256": config.sha256,
            "data_sha256": ingestion.source_sha256,
            "universe_sha256": sha256(universe_bytes).hexdigest(),
            "calendar_sha256": calendar.source_sha256,
            "calendar_exchange": calendar.exchange,
            "calendar_version": calendar.version,
            "corporate_actions_sha256": corporate_actions.source_sha256,
            "corporate_actions_version": str(
                config.values["corporate_actions"]["version"]
            ),
            "initial_cash_usd": initial_cash,
            "universe_version": config.universe_version,
            "strategy_version": STRATEGY_VERSION,
            "ml_model_version": "disabled",
            "run_timestamp_utc": timestamp.astimezone(UTC).isoformat(),
        },
        "input": {
            "initial_cash_usd": initial_cash,
            "bars": len(ingestion.bars),
            "sessions": len(benchmark_sessions),
            "quarantined_rows": 0,
            "quality_notices": [
                {
                    "line_number": notice.line_number,
                    "values": dict(notice.values),
                    "reasons": notice.reasons,
                }
                for notice in ingestion.notices
            ],
            "delisting_events": len(corporate_actions.delistings),
        },
        "reporting_period": {
            "start": dates[0].isoformat(),
            "end": dates[-1].isoformat(),
            "sessions": len(dates),
        },
        "signals": signal_report,
        "costs": {
            "commission": total_commission,
            "slippage": total_slippage,
            "fx_friction": total_fx,
            "total": total_commission + total_slippage + total_fx,
        },
        "metrics": {
            "strategy": asdict(strategy_metrics),
            "spy_buy_and_hold": asdict(benchmark_metrics),
            "cash": asdict(cash_metrics),
            "benchmark_relative": asdict(relative_metrics),
        },
        "trades": [
            {
                **asdict(trade),
                "date": trade.date.isoformat(),
                "signal_date": None
                if trade.signal_date is None
                else trade.signal_date.isoformat(),
            }
            for trade in result.trades
        ],
        "execution_issues": [
            {
                **asdict(issue),
                "date": issue.date.isoformat(),
                "signal_date": None
                if issue.signal_date is None
                else issue.signal_date.isoformat(),
            }
            for issue in result.execution_issues
        ],
        "equity_curve": [
            {**asdict(point), "date": point.date.isoformat()}
            for point in reporting_curve
        ],
        "final_positions": _serialize_mapping(result.final_positions),
        "final_cash": result.final_cash,
    }
