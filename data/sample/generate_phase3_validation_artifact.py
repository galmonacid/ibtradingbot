"""Generate a deterministic synthetic artifact that exercises the Phase 3 workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.validation.ablation import DETERMINISTIC_ABLATIONS
from src.validation.walk_forward import build_expanding_windows


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_artifact(root: Path) -> dict[str, object]:
    """Return synthetic engineering evidence, never admissible performance evidence."""
    start = date(2007, 1, 1)
    end = date(2021, 1, 1)
    sessions: list[date] = []
    current = start
    while current < end:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    session_tuple = tuple(sessions)
    windows = build_expanding_windows(session_tuple, verified_complete_through=session_tuple[-1])
    daily_returns = {
        day.isoformat(): (0.0007 if index % 5 else -0.0015)
        for index, day in enumerate(session_tuple)
    }
    grid_axes: dict[str, list[object]] = {
        "target_positions": [3, 4, 5],
        "skip_recent_days": [0, 5, 10],
        "target_annual_volatility": [0.10, 0.12, 0.15],
        "risk_on_breadth_threshold": [0.55, 0.60, 0.65],
        "rebalance_frequency": ["weekly", "biweekly"],
        "rebalance_day": ["Thursday", "Friday"],
        "trend_window_scale": [0.80, 1.00, 1.20],
        "momentum_63d_weight": [0.30, 0.35, 0.40],
        "execution_delay_sessions": [1, 2],
        "commission_multiplier": [1.0, 2.0],
        "slippage_bps_each_side": [5.0, 10.0],
    }
    baseline: dict[str, object] = {
        "target_positions": 4,
        "skip_recent_days": 5,
        "target_annual_volatility": 0.12,
        "risk_on_breadth_threshold": 0.60,
        "rebalance_frequency": "weekly",
        "rebalance_day": "Friday",
        "trend_window_scale": 1.00,
        "momentum_63d_weight": 0.35,
        "execution_delay_sessions": 1,
        "commission_multiplier": 1.0,
        "slippage_bps_each_side": 5.0,
    }
    candidates = [baseline]
    for axis, choices in grid_axes.items():
        candidates.extend(
            {**baseline, axis: choice} for choice in choices if choice != baseline[axis]
        )

    def parameter_key(values: dict[str, object]) -> str:
        return json.dumps(values, sort_keys=True, separators=(",", ":"))

    baseline_key = parameter_key(baseline)
    fold_results = {
        str(window.index): {
            "validation_scores": {
                parameter_key(candidate): 0.95 if candidate == baseline else 0.90
                for candidate in candidates
            },
            "test_returns": {
                baseline_key: {
                    day.isoformat(): daily_returns[day.isoformat()] for day in window.test
                }
            },
        }
        for window in windows
    }
    oos_dates = tuple(dict.fromkeys(day for window in windows for day in window.test))
    session_bytes = "".join(f"{day.isoformat()}\n" for day in session_tuple).encode()
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "0" * 40
    config = root / "config.example.yaml"
    data = root / "data/sample/research_daily_bars.csv"
    universe = root / "data/sample/seed_universe.csv"
    calendar = root / "data/sample/us_sessions.csv"
    actions = root / "data/sample/corporate_actions.csv"
    metric_names = (
        "cagr",
        "annualized_volatility",
        "sharpe_ratio",
        "sortino_ratio",
        "maximum_drawdown",
        "calmar_ratio",
        "win_rate",
        "profit_factor",
        "turnover",
        "average_holding_period",
        "exposure",
        "number_of_trades",
        "average_trade_return",
        "median_trade_return",
        "best_trade",
        "worst_trade",
        "best_month",
        "worst_month",
        "best_year",
        "worst_year",
    )
    return {
        "sessions": [day.isoformat() for day in session_tuple],
        "verified_complete_through": session_tuple[-1].isoformat(),
        "point_in_time_universe": False,
        "complete_data_coverage": True,
        "universe_source": "fixed_seed",
        "data_id": _sha(data),
        "cost_id": "phase2-stress-costs-v1",
        "stress_scenario": {
            "commission_multiplier": 2.0,
            "slippage_bps_each_side": 10.0,
            "additional_execution_delay_sessions": 1,
            "fx_buffer_unchanged": True,
        },
        "grid_axes": grid_axes,
        "candidates": candidates,
        "fold_results": fold_results,
        "evidence": {
            "regimes_by_date": {
                day.isoformat(): "risk_on" if index % 80 < 40 else "neutral"
                for index, day in enumerate(session_tuple)
            },
            "stressed_returns_by_date": {
                day: value - 0.00005 for day, value in daily_returns.items()
            },
            "benchmark_returns_by_date": {day: value * 0.8 for day, value in daily_returns.items()},
            "cash_returns_by_date": {day: 0.0 for day in daily_returns},
            "exposure_by_date": {day: 0.75 for day in daily_returns},
            "traded_notional": 25.0,
            "realized_trades": [
                {
                    "lot_id": f"lot-{index}",
                    "opened_date": oos_dates[
                        max(0, 1 + index * (len(oos_dates) - 1) // 180 - 1)
                    ].isoformat(),
                    "closed_date": oos_dates[1 + index * (len(oos_dates) - 1) // 180].isoformat(),
                    "symbol": f"SYN{index % 6}",
                    "basis": 100.0,
                    "proceeds": 101.0 if index % 4 else 99.5,
                }
                for index in range(180)
            ],
        },
        "ablation_returns": {
            scenario.name: {day.isoformat(): daily_returns[day.isoformat()] for day in oos_dates}
            for scenario in DETERMINISTIC_ABLATIONS
        },
        "settings": {
            "bootstrap_iterations": 2000,
            "bootstrap_seed": 20260910,
            "minimum_economic_validation_score": 0.60,
        },
        "dataset": {
            "name": "synthetic Phase 3 engineering fixture",
            "version": "synthetic-phase3-v1",
            "synthetic": True,
        },
        "provenance": {
            "git_revision": revision,
            "git_dirty": True,
            "config_sha256": _sha(config),
            "data_sha256": _sha(data),
            "universe_sha256": _sha(universe),
            "calendar_sha256": _sha(calendar),
            "calendar_sessions_sha256": hashlib.sha256(session_bytes).hexdigest(),
            "corporate_actions_sha256": _sha(actions),
            "data_version": "synthetic-phase3-v1",
            "universe_version": "seed-v1",
            "calendar_version": "synthetic-weekday-calendar-v1",
            "corporate_actions_version": "actions-fixture-v1",
            "strategy_version": "phase2-risk-portfolio-v1",
            "run_timestamp_utc": datetime(2026, 9, 10, tzinfo=UTC).isoformat(),
        },
        "benchmark_metrics": {
            "spy_cagr": None,
            "cash_cagr": None,
            "excess_cagr": None,
            "tracking_error": None,
            "information_ratio": None,
            "up_market_capture": None,
            "down_market_capture": None,
        },
        "strategy_metrics": dict.fromkeys(metric_names),
        "stressed_metrics": dict.fromkeys(metric_names),
        "limitations": [
            "Synthetic returns and a weekday-only calendar are engineering fixtures.",
            "The fixed seed universe is not point-in-time deployment evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).parents[2]
    args.output.write_text(
        json.dumps(build_artifact(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
