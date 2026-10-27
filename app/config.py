from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ProviderName = Literal["mock", "ollama"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def validate_loopback_http_url(value: str) -> str:
    """Allow only an HTTP endpoint addressed by a literal loopback IP."""

    parsed = urlsplit(value)
    if parsed.scheme != "http":
        raise ValueError("Ollama URL must use http on the local loopback interface")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Ollama URL cannot contain credentials, query, or fragment")
    if parsed.path not in ("", "/"):
        raise ValueError("Ollama URL cannot contain a path")
    if parsed.hostname is None:
        raise ValueError("Ollama URL must include a host")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("Ollama host must be a literal loopback IP") from exc
    if not address.is_loopback:
        raise ValueError("Ollama host must be a loopback IP")
    return value.rstrip("/")


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECUREQUERY_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: ProviderName = "mock"
    demo_mode: bool = False
    model: Literal["qwen2.5-coder:7b", "qwen2.5-coder:3b"] = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://127.0.0.1:11435"
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    read_timeout_seconds: float = Field(default=60.0, gt=0, le=180)
    total_timeout_seconds: float = Field(default=90.0, gt=0, le=240)
    max_provider_response_bytes: int = Field(default=65_536, ge=1_024, le=262_144)
    max_raw_output_chars: int = Field(default=8_192, ge=256, le=32_768)
    max_concurrency: int = Field(default=1, ge=1, le=4)
    max_request_bytes: int = Field(default=16_384, ge=2_048, le=65_536)

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, value: str) -> str:
        return validate_loopback_http_url(value)

