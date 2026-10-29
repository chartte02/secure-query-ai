from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import AppSettings, validate_loopback_http_url


@pytest.mark.parametrize(
    "value",
    ["http://127.0.0.1:11434", "http://[::1]:11434", "http://127.1.2.3:8080/"],
)
def test_loopback_ollama_urls_are_allowed(value: str) -> None:
    assert validate_loopback_http_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:11434",
        "http://localhost:11434",
        "http://192.168.1.20:11434",
        "http://169.254.169.254/latest/meta-data",
        "http://user:password@127.0.0.1:11434",
        "http://127.0.0.1:11434/api/chat",
    ],
)
def test_non_literal_or_non_loopback_ollama_urls_are_rejected(value: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        AppSettings(ollama_base_url=value)


def test_model_name_rejects_shell_metacharacters() -> None:
    with pytest.raises(ValidationError):
        AppSettings(model="qwen; shutdown")


def test_unknown_model_is_rejected_even_when_name_is_valid() -> None:
    with pytest.raises(ValidationError):
        AppSettings(model="other-model:7b")


def test_demo_features_require_explicit_configuration(monkeypatch) -> None:
    monkeypatch.delenv("SECUREQUERY_DEMO_MODE", raising=False)
    assert AppSettings(_env_file=None).demo_mode is False


def test_settings_do_not_load_another_working_directory_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "SECUREQUERY_OLLAMA_BASE_URL=http://192.168.1.1:11434\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECUREQUERY_OLLAMA_BASE_URL", raising=False)
    assert AppSettings(provider="mock").ollama_base_url.startswith("http://127.0.0.1:")

