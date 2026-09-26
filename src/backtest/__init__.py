"""Event-driven research backtest and reporting primitives."""

from src.backtest.costs import CostModel
from src.backtest.engine import (
    BacktestDecision,
    BacktestExecutionTrace,
    BacktestResult,
    CorporateActionSettlement,
    EquityPoint,
    ExecutionFill,
    MissingOpenDisposition,
    OrderIntent,
    PriceBar,
    PriceBarLike,
    TraceTargetWeight,
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
    "BacktestDecision",
    "BacktestExecutionTrace",
    "BenchmarkMetrics",
    "CostModel",
    "CorporateActionSettlement",
    "EquityPoint",
    "ExecutionFill",
    "MissingOpenDisposition",
    "OrderIntent",
    "PerformanceMetrics",
    "PriceBar",
    "PriceBarLike",
    "Trade",
    "TraceTargetWeight",
    "TradeOutcome",
    "benchmark_relative_metrics",
    "performance_metrics",
    "run_backtest",
]
