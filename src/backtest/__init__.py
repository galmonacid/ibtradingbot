"""Event-driven research backtest and reporting primitives."""

from src.backtest.costs import CostModel
from src.backtest.engine import (
    BacktestResult,
    EquityPoint,
    PriceBar,
    PriceBarLike,
    Trade,
    run_backtest,
)
from src.backtest.metrics import (
    BenchmarkMetrics,
    PerformanceMetrics,
    TradeOutcome,
    benchmark_relative_metrics,
    performance_metrics,
)

__all__ = [
    "BacktestResult",
    "BenchmarkMetrics",
    "CostModel",
    "EquityPoint",
    "PerformanceMetrics",
    "PriceBar",
    "PriceBarLike",
    "Trade",
    "TradeOutcome",
    "benchmark_relative_metrics",
    "performance_metrics",
    "run_backtest",
]
