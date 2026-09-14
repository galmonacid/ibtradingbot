from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from src.backtest.costs import Side
from src.backtest.engine import Trade
from src.data.calendar import TradingCalendar, weekly_signal_dates
from src.research import ResearchError, run_research
from src.research.pipeline import _trade_outcomes

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "config.example.yaml"
DATA = ROOT / "data/sample/research_daily_bars.csv"
UNIVERSE = ROOT / "data/sample/seed_universe.csv"
CALENDAR = ROOT / "data/sample/us_sessions.csv"
ACTIONS = ROOT / "data/sample/corporate_actions.csv"
TIMESTAMP = datetime.fromisoformat("2026-09-07T00:00:00+00:00")


def _trade(day: str, side: Side, shares: float, price: float) -> Trade:
    return Trade(
        date=datetime.fromisoformat(day).date(),
        signal_date=None,
        symbol="AAA",
        side=side,
        shares=shares,
        reference_price=price,
        execution_price=price,
        gross_notional=shares * price,
        commission=0.0,
        slippage_cost=0.0,
        fx_cost=0.0,
        reason="rebalance",
    )


def test_trade_metrics_realize_fifo_lots_after_position_top_up() -> None:
    outcomes = _trade_outcomes(
        (
            _trade("2024-01-01", "buy", 1.0, 100.0),
            _trade("2024-02-01", "buy", 9.0, 10.0),
            _trade("2024-02-02", "sell", 10.0, 20.0),
        )
    )

    assert [outcome.return_value for outcome in outcomes] == pytest.approx([-0.80, 1.0])
    assert [outcome.holding_days for outcome in outcomes] == [32, 1]
    assert [outcome.profit_loss for outcome in outcomes] == pytest.approx([-80.0, 90.0])


def test_weekly_schedule_uses_explicit_calendar_and_omits_partial_final_week() -> None:
    sessions = [
        datetime.fromisoformat(value).date() for value in ("2024-03-28", "2024-04-01", "2024-04-02")
    ]
    calendar = TradingCalendar(
        "XNYS",
        "test-v1",
        tuple(sessions),
        (datetime.fromisoformat("2024-03-28").date(),),
        "hash",
    )
    assert weekly_signal_dates(tuple(sessions), calendar) == (
        datetime.fromisoformat("2024-03-28").date(),
    )


def test_end_to_end_fixture_is_deterministic_costed_and_causal() -> None:
    first = run_research(CONFIG, DATA, UNIVERSE, CALENDAR, ACTIONS, run_timestamp=TIMESTAMP)
    second = run_research(CONFIG, DATA, UNIVERSE, CALENDAR, ACTIONS, run_timestamp=TIMESTAMP)

    assert first == second
    assert first["label"] == (
        "synthetic fixed-universe engineering validation; not a performance claim"
    )
    assert first["input"] == {
        "initial_cash_usd": 100_000.0,
        "bars": 2280,
        "sessions": 380,
        "quarantined_rows": 0,
        "quality_notices": [],
        "delisting_events": 0,
    }
    assert len(first["signals"]) == 79
    assert {signal["regime"] for signal in first["signals"]} == {
        "risk_on",
        "neutral",
        "risk_off",
    }
    for signal in first["signals"]:
        weights = signal["target_weights"]
        assert len(weights) <= 5
        assert all(0.0 <= weight <= 0.30 for weight in weights.values())
        assert sum(weights.values()) <= 0.98 + 1e-12
        if signal["regime"] == "risk_off":
            assert weights == {}

    trades = first["trades"]
    assert len(trades) == 67
    assert all(
        trade["signal_date"] is None or trade["date"] > trade["signal_date"] for trade in trades
    )
    memorial_day = [trade for trade in trades if trade["signal_date"] == "2024-05-24"]
    assert memorial_day and {trade["date"] for trade in memorial_day} == {"2024-05-28"}
    assert first["costs"]["total"] > 0.0
    assert first["costs"]["total"] == pytest.approx(
        first["costs"]["commission"] + first["costs"]["slippage"] + first["costs"]["fx_friction"]
    )
    # Targets and open fills obey 98%; close-marked exposure can drift with prices,
    # but positive cash means the long-only account remains below 100% gross.
    assert max(point["gross_exposure"] for point in first["equity_curve"]) <= 1.0
    assert all(point["cash"] >= 0.0 for point in first["equity_curve"])
    assert first["metrics"]["strategy"]["number_of_trades"] > 0
    assert first["metrics"]["spy_buy_and_hold"]["cagr"] is not None
    assert first["metrics"]["cash"]["cagr"] == 0.0
    assert first["metrics"]["benchmark_relative"]["tracking_error"] is not None
    assert first["provenance"]["strategy_version"] == "phase2-risk-portfolio-v1"
    assert first["provenance"]["ml_model_version"] == "disabled"
    assert first["provenance"]["run_timestamp_utc"] == "2026-09-07T00:00:00+00:00"
    assert first["provenance"]["calendar_exchange"] == "XNYS"
    assert first["provenance"]["calendar_version"] == "xnys-fixture-v1"
    assert first["provenance"]["initial_cash_usd"] == 100_000.0
    assert first["reporting_period"]["start"] == "2024-03-08"
    assert first["equity_curve"][0]["equity"] == 100_000.0
    assert not first["validation_gate_assessment"]["admissible_deployment_evidence"]
    stressed = first["comparisons"]["inverse_volatility_stressed_costs"]
    equal_weight = first["comparisons"]["equal_weight_default_costs"]
    assert stressed["costs"]["total"] > first["costs"]["total"]
    assert stressed["final_equity"] <= first["equity_curve"][-1]["equity"]
    assert equal_weight["metrics"]["number_of_trades"] > 0
    assert all(
        signal["sizing"]["expected_volatility"] <= 0.12 + 1e-12 for signal in first["signals"]
    )


def test_cli_emits_json_and_invalid_input_fails_without_traceback(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "src.cli.research_pipeline",
        "--config",
        str(CONFIG),
        "--data",
        str(DATA),
        "--universe",
        str(UNIVERSE),
        "--calendar",
        str(CALENDAR),
        "--corporate-actions",
        str(ACTIONS),
        "--run-timestamp",
        TIMESTAMP.isoformat(),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["input"]["sessions"] == 380
    assert "research_pipeline_completed" in completed.stderr

    invalid_cash = subprocess.run(
        command + ["--initial-cash", "-1"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid_cash.returncode == 1
    assert "research_pipeline_failed" in invalid_cash.stderr
    assert "Traceback" not in invalid_cash.stderr

    command[command.index(str(DATA))] = str(tmp_path / "missing.csv")
    failed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    assert failed.returncode == 1
    assert "research_pipeline_failed" in failed.stderr
    assert "Traceback" not in failed.stderr


def test_complete_pipeline_is_prefix_invariant(tmp_path: Path) -> None:
    cutoff = "2024-06-28"
    source_lines = DATA.read_text(encoding="utf-8").splitlines()
    prefix = tmp_path / "prefix.csv"
    prefix.write_text(
        "\n".join(
            [source_lines[0]]
            + [line for line in source_lines[1:] if line.split(",", 1)[0] <= cutoff]
        )
        + "\n",
        encoding="utf-8",
    )
    before = run_research(CONFIG, prefix, UNIVERSE, CALENDAR, ACTIONS, run_timestamp=TIMESTAMP)
    after = run_research(CONFIG, DATA, UNIVERSE, CALENDAR, ACTIONS, run_timestamp=TIMESTAMP)

    assert before["signals"] == [signal for signal in after["signals"] if signal["date"] <= cutoff]
    assert before["trades"] == [trade for trade in after["trades"] if trade["date"] <= cutoff]
    assert before["equity_curve"] == [
        point for point in after["equity_curve"] if point["date"] <= cutoff
    ]


def test_pipeline_rejects_missing_benchmark_and_noncalendar_bar(tmp_path: Path) -> None:
    no_spy = tmp_path / "no_spy.csv"
    no_spy.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume\n"
        "2024-01-02,AAPL,100,101,99,100,100,6000000\n",
        encoding="utf-8",
    )
    with pytest.raises(ResearchError, match="benchmark SPY"):
        run_research(CONFIG, no_spy, UNIVERSE, CALENDAR, ACTIONS, run_timestamp=TIMESTAMP)

    weekend = tmp_path / "weekend.csv"
    lines = DATA.read_text(encoding="utf-8").splitlines()
    last_aapl = next(line for line in reversed(lines) if ",AAPL," in line)
    weekend.write_text(
        "\n".join(lines + ["2024-07-13," + last_aapl.split(",", 1)[1]]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ResearchError, match="absent from the benchmark"):
        run_research(CONFIG, weekend, UNIVERSE, CALENDAR, ACTIONS, run_timestamp=TIMESTAMP)


def test_pipeline_applies_point_in_time_membership_and_records_provenance(
    tmp_path: Path,
) -> None:
    rows = UNIVERSE.read_text(encoding="utf-8").splitlines()[1:]
    candidates = [row.split(",")[1] for row in rows if row.split(",")[1] != "SPY"]
    membership = tmp_path / "membership.csv"
    security_master = tmp_path / "security-master.csv"
    security_master.write_text(
        "metadata_version," + UNIVERSE.read_text(encoding="utf-8").replace("version,", "", 1),
        encoding="utf-8",
    )
    membership.write_text(
        "source_version,symbol,effective_from,effective_to\n"
        + "".join(f"pit-fixture-v1,{symbol},2020-01-01,\n" for symbol in candidates),
        encoding="utf-8",
    )
    report = run_research(
        CONFIG,
        DATA,
        UNIVERSE,
        CALENDAR,
        ACTIONS,
        run_timestamp=TIMESTAMP,
        point_in_time_universe_path=membership,
        historical_security_master_path=security_master,
    )
    assert report["provenance"]["point_in_time_universe"] is True
    assert report["provenance"]["universe_version"] == "pit-fixture-v1"
