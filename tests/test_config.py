from pathlib import Path

import pytest

from src.config.settings import ConfigurationError, load_config

ROOT = Path(__file__).parents[1]


def test_example_config_loads_with_stable_hash() -> None:
    config = load_config(ROOT / "config.example.yaml")

    assert config.timezone == "Europe/London"
    assert len(config.sha256) == 64
    assert config.target_annual_volatility == 0.12
    assert config.min_position_weight == 0.10
    assert config.max_position_weight == 0.30
    assert config.cash_buffer == 0.02
    assert config.regime_exposure_limits == {
        "risk_on": 1.0,
        "neutral": 0.5,
        "risk_off": 0.0,
    }
    assert config.drawdown_thresholds == (0.10, 0.15)
    assert config.hard_drawdown_requires_manual_reenable is True
    assert config.rank_hysteresis_multiplier == 2
    assert config.transaction_costs == (0.35, 5.0, 5.0)
    assert config.stress_transaction_costs == (0.70, 10.0, 5.0)


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("allow_short: false", "allow_short: true", "execution.allow_short"),
        ("max_positions: 5", "max_positions: 6", "target <= max <= 5"),
        ("target_positions: 4", "target_positions: 4.5", "must be an integer"),
        ("max_position_weight: 0.30", "max_position_weight: 0.31", "max_position_weight"),
        ("cash_buffer: 0.02", "cash_buffer: 0.01", "cash_buffer"),
        (
            "target_annual_volatility: 0.12",
            "target_annual_volatility: 0",
            "target_annual_volatility",
        ),
        (
            "rank_hysteresis_multiplier: 2",
            "rank_hysteresis_multiplier: 3",
            "rank_hysteresis_multiplier",
        ),
        ("max_gross_exposure_neutral: 0.50", "max_gross_exposure_neutral: 1.01", "gross exposures"),
        ("max_gross_exposure_risk_off: 0.00", "max_gross_exposure_risk_off: 0.25", "must be 0"),
        ("source: fixed_seed", "source: dynamic", "source must be fixed_seed"),
        ("min_positions: 0", "min_positions: 1", "min_positions must be 0"),
        (
            "allow_fractional_shares: true",
            "allow_fractional_shares: false",
            "allow_fractional_shares",
        ),
        (
            "slippage_bps_each_side: 5",
            "slippage_bps_each_side: 10000",
            "must be below 10000",
        ),
        (
            "max_portfolio_drawdown_soft: 0.10",
            "max_portfolio_drawdown_soft: 0.15",
            "0 < soft < hard",
        ),
        (
            "max_portfolio_drawdown_hard: 0.15",
            "max_portfolio_drawdown_hard: 0.16",
            "must remain 0.15",
        ),
        (
            "hard_drawdown_requires_manual_reenable: true",
            "hard_drawdown_requires_manual_reenable: false",
            "must be true",
        ),
        (
            "commission_multiplier: 2.0",
            "commission_multiplier: 0.5",
            "must remain 2",
        ),
    ],
)
def test_unsafe_configuration_is_rejected(
    tmp_path: Path, needle: str, replacement: str, message: str
) -> None:
    source = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    path = tmp_path / "unsafe.yaml"
    path.write_text(source.replace(needle, replacement), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=message):
        load_config(path)


def test_obsolete_timed_hard_stop_is_rejected(tmp_path: Path) -> None:
    source = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    path = tmp_path / "timed-hard-stop.yaml"
    path.write_text(
        source.replace(
            "  hard_drawdown_requires_manual_reenable: true",
            "  hard_drawdown_requires_manual_reenable: true\n  hard_stop_new_entries_days: 10",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="unsupported.*remains latched"):
        load_config(path)


def test_phase3_validation_settings_are_typed_and_safe(tmp_path: Path) -> None:
    config = load_config(ROOT / "config.example.yaml")
    assert config.validation_windows == (8, 2, 1, 6)
    assert config.bootstrap_settings == (2000, 20, 20260909)
    assert config.bootstrap_gate_thresholds == (0.0, 0.0, 0.25)
    assert config.sensitivity_grid["target_positions"] == (3, 4, 5)

    source = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    path = tmp_path / "unsafe-bootstrap.yaml"
    path.write_text(
        source.replace("bootstrap_iterations: 2000", "bootstrap_iterations: 1999"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="at least 2000"):
        load_config(path)


def test_non_live_historical_universe_sources_are_allowed(tmp_path: Path) -> None:
    source = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    path = tmp_path / "public-reconstructed.yaml"
    path.write_text(
        source.replace("source: fixed_seed", "source: public_reconstructed"), encoding="utf-8"
    )
    assert load_config(path).values["universe"]["source"] == "public_reconstructed"
    path.write_text(
        source.replace("source: fixed_seed", "source: trusted_canonical"), encoding="utf-8"
    )
    assert load_config(path).values["universe"]["source"] == "trusted_canonical"
