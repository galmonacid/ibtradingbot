import json
import logging

from src.logging import JsonFormatter


def test_json_formatter_has_required_fields() -> None:
    record = logging.LogRecord("test", logging.INFO, "", 0, "fixture_validated", (), None)
    record.run_id = "phase-0"

    rendered = json.loads(JsonFormatter().format(record))

    assert rendered["event"] == "fixture_validated"
    assert rendered["level"] == "INFO"
    assert rendered["run_id"] == "phase-0"
    assert rendered["timestamp"].endswith("Z")
