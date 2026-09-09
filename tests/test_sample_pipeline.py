import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_sample_pipeline_validates_fixture() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli.sample_pipeline",
            "--config",
            "config.example.yaml",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "validated"
    assert output["data"]["rows"] == 6
    assert output["data"]["symbols"] == ["AAPL", "MSFT", "SPY"]
    assert "sample_pipeline_validated" in result.stderr


def test_sample_pipeline_rejects_invalid_data(tmp_path: Path) -> None:
    bad_data = tmp_path / "missing.csv"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli.sample_pipeline",
            "--config",
            "config.example.yaml",
            "--data",
            str(bad_data),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "sample_pipeline_failed" in result.stderr
