from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.cli.validation_pipeline import ValidationArtifactError, run_artifact
from src.validation.ablation import DETERMINISTIC_ABLATIONS
from src.validation.walk_forward import build_expanding_windows


def test_artifact_pipeline_generates_deterministic_fail_closed_reports(tmp_path: Path) -> None:
    start = date(2007, 1, 1)
    sessions = tuple(start + timedelta(days=index) for index in range(12 * 366))
    returns = {
        day.isoformat(): 0.001 if index % 3 else -0.0005 for index, day in enumerate(sessions)
    }
    regimes = {
        day.isoformat(): "on" if index % 40 < 20 else "off" for index, day in enumerate(sessions)
    }
    windows = build_expanding_windows(sessions, verified_complete_through=sessions[-1])
    fold_results = {
        str(window.index): {
            "validation_scores": {
                '{"positions":3}': 1.0,
                '{"positions":4}': 0.95,
            },
            "test_returns": {
                '{"positions":3}': {
                    day.isoformat(): returns[day.isoformat()] for day in window.test
                }
            },
        }
        for window in windows
    }
    oos_dates = tuple(dict.fromkeys(day for window in windows for day in window.test))
    hex64 = "a" * 64
    session_hash = hashlib.sha256(
        "".join(f"{day.isoformat()}\n" for day in sessions).encode()
    ).hexdigest()
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
    artifact = {
        "sessions": [day.isoformat() for day in sessions],
        "verified_complete_through": sessions[-1].isoformat(),
        "point_in_time_universe": False,
        "complete_data_coverage": True,
        "data_id": hex64,
        "cost_id": "stress-v1",
        "stress_scenario": {
            "commission_multiplier": 2.0,
            "slippage_bps_each_side": 10.0,
            "additional_execution_delay_sessions": 1,
            "fx_buffer_unchanged": True,
        },
        "universe_source": "fixed_seed",
        "grid_axes": {"positions": [3, 4]},
        "fold_results": fold_results,
        "evidence": {
            "regimes_by_date": regimes,
            "stressed_returns_by_date": returns,
            "benchmark_returns_by_date": {
                day.isoformat(): value * 0.8
                for day, value in zip(sessions, returns.values(), strict=True)
            },
            "cash_returns_by_date": {day.isoformat(): 0.0 for day in sessions},
            "exposure_by_date": {day.isoformat(): 0.75 for day in sessions},
            "traded_notional": 25.0,
            "realized_trades": [
                {
                    "lot_id": f"lot-{index}",
                    "opened_date": oos_dates[close_index - 1].isoformat(),
                    "closed_date": oos_dates[close_index].isoformat(),
                    "symbol": f"S{index % 6}",
                    "basis": 100.0,
                    "proceeds": 101.0,
                }
                for index in range(200)
                for close_index in (1 + index * (len(oos_dates) - 1) // 200,)
            ],
        },
        "ablation_returns": {
            scenario.name: {day.isoformat(): returns[day.isoformat()] for day in oos_dates}
            for scenario in DETERMINISTIC_ABLATIONS
        },
        "settings": {"bootstrap_seed": 7},
        "dataset": {"name": "synthetic", "version": "data-v1", "synthetic": True},
        "provenance": {
            "git_revision": "a" * 40,
            "git_dirty": False,
            "config_sha256": hex64,
            "data_sha256": hex64,
            "universe_sha256": hex64,
            "calendar_sha256": hex64,
            "calendar_sessions_sha256": session_hash,
            "corporate_actions_sha256": hex64,
            "data_version": "data-v1",
            "universe_version": "universe-v1",
            "calendar_version": "calendar-v1",
            "corporate_actions_version": "actions-v1",
            "strategy_version": "strategy-v1",
            "run_timestamp_utc": "2026-09-10T00:00:00+00:00",
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
        "limitations": ["Synthetic fixture is not deployment evidence."],
    }
    source = tmp_path / "artifact.json"
    source.write_text(json.dumps(artifact), encoding="utf-8")
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "research_report.md"

    report = run_artifact(source, json_output=json_path, markdown_output=markdown_path)
    first = (json_path.read_bytes(), markdown_path.read_bytes())
    run_artifact(source, json_output=json_path, markdown_output=markdown_path)

    assert first == (json_path.read_bytes(), markdown_path.read_bytes())
    assert not report.admissible_evidence
    assert not report.gates.ready_for_paper_trading
    assert report.folds and report.bootstrap and report.ablations
    strategy_metrics = dict(report.strategy_metrics)
    assert strategy_metrics["annualized_volatility"] is not None
    assert strategy_metrics["sortino_ratio"] is not None
    assert strategy_metrics["average_trade_return"] is not None
    assert strategy_metrics["best_month"] is not None
    assert strategy_metrics["turnover"] is not None
    assert strategy_metrics["exposure"] == 0.75
    assert dict(report.benchmark_metrics)["tracking_error"] is not None
    assert "FAIL CLOSED" in markdown_path.read_text(encoding="utf-8")
    assert {item.metric for item in report.bootstrap} >= {
        "cagr",
        "maximum_drawdown",
        "sharpe_ratio",
        "one_year_return",
        "mean",
    }

    self_certifying = deepcopy(artifact)
    self_certifying["point_in_time_universe"] = True
    self_certifying["universe_source"] = "point_in_time"
    source.write_text(json.dumps(self_certifying), encoding="utf-8")
    still_blocked = run_artifact(source, json_output=json_path, markdown_output=markdown_path)
    assert not still_blocked.admissible_evidence
    assert not still_blocked.gates.ready_for_paper_trading

    contradictory = deepcopy(artifact)
    contradictory["strategy_metrics"]["cagr"] = 0.99
    source.write_text(json.dumps(contradictory), encoding="utf-8")
    with pytest.raises(ValidationArtifactError, match="contradicts"):
        run_artifact(source, json_output=json_path, markdown_output=markdown_path)

    contradictory_benchmark = deepcopy(artifact)
    contradictory_benchmark["benchmark_metrics"]["spy_cagr"] = 0.99
    source.write_text(json.dumps(contradictory_benchmark), encoding="utf-8")
    with pytest.raises(ValidationArtifactError, match="benchmark_metrics.spy_cagr contradicts"):
        run_artifact(source, json_output=json_path, markdown_output=markdown_path)

    missing_benchmark_date = deepcopy(artifact)
    del missing_benchmark_date["evidence"]["benchmark_returns_by_date"][oos_dates[0].isoformat()]
    source.write_text(json.dumps(missing_benchmark_date), encoding="utf-8")
    with pytest.raises(ValidationArtifactError, match="benchmark return must be a number"):
        run_artifact(source, json_output=json_path, markdown_output=markdown_path)

    missing_provenance = deepcopy(artifact)
    del missing_provenance["provenance"]["data_sha256"]
    source.write_text(json.dumps(missing_provenance), encoding="utf-8")
    with pytest.raises(ValidationArtifactError, match="data_sha256"):
        run_artifact(source, json_output=json_path, markdown_output=markdown_path)

    malformed = deepcopy(artifact)
    malformed["limitations"] = "not-a-list"
    source.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(ValidationArtifactError, match="limitations must be a list"):
        run_artifact(source, json_output=json_path, markdown_output=markdown_path)
