from pathlib import Path

import pytest

from src.config.credentials import load_tiingo_token


def test_local_file_and_environment_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.local.toml"
    path.write_text('[tiingo]\napi_token = "local-test-token"\n')
    monkeypatch.delenv("TEST_TIINGO_TOKEN", raising=False)
    assert load_tiingo_token(environment_name="TEST_TIINGO_TOKEN", credentials_file=path) == (
        "local-test-token"
    )
    monkeypatch.setenv("TEST_TIINGO_TOKEN", "environment-test-token")
    path.write_text("invalid TOML")
    assert load_tiingo_token(environment_name="TEST_TIINGO_TOKEN", credentials_file=path) == (
        "environment-test-token"
    )


@pytest.mark.parametrize("content", [
    '[tiingo]\napi_token = "private-test-value',
    '[tiingo]\napi_token = "private-test-value"\napi_token = "duplicate"',
    '[tiingo]\napi_token = "private-test-value with-space"',
    '[tiingo]\napi_token = 123', '[tiingo]\napi_token = ""',
])
def test_errors_do_not_expose_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
):
    monkeypatch.delenv("TEST_TIINGO_TOKEN", raising=False)
    path = tmp_path / "credentials.local.toml"
    path.write_text(content)
    with pytest.raises(ValueError) as caught:
        load_tiingo_token(environment_name="TEST_TIINGO_TOKEN", credentials_file=path)
    assert "private-test-value" not in str(caught.value)


def test_missing_file_is_actionable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TEST_TIINGO_TOKEN", raising=False)
    with pytest.raises(ValueError, match="credential missing"):
        load_tiingo_token(environment_name="TEST_TIINGO_TOKEN",
                          credentials_file=tmp_path / "absent")
