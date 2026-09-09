from pathlib import Path

import pytest

from src.config.settings import ConfigurationError, load_config

ROOT = Path(__file__).parents[1]


def test_example_config_loads_with_stable_hash() -> None:
    config = load_config(ROOT / "config.example.yaml")

    assert config.timezone == "Europe/London"
    assert len(config.sha256) == 64


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("allow_short: false", "allow_short: true", "execution.allow_short"),
        ("max_positions: 5", "max_positions: 6", "target <= max <= 5"),
        ("target_positions: 4", "target_positions: 4.5", "must be an integer"),
        ("max_position_weight: 0.30", "max_position_weight: 0.31", "max_position_weight"),
        ("cash_buffer: 0.02", "cash_buffer: 0.01", "cash_buffer"),
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
