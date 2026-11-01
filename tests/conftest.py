"""Pytest fixtures shared by member A (API) and member B (database) suites.

Member A's API tests use `client` (backed by `app_settings` and the Mock
provider, no Ollama or database); member B's database tests use the
session-scoped `settings` fixture, which requires the Docker PostgreSQL lab.

Member A's imports are deferred into the fixture bodies so that member B's
documented minimal environment (`requirements-dev.lock`, no app dependencies)
can still import this conftest and run the database suites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from db.manage import assert_target
from db.settings import Settings

if TYPE_CHECKING:
    from app.config import AppSettings


@pytest.fixture
def app_settings() -> AppSettings:
    from app.config import AppSettings

    return AppSettings(provider="mock", demo_mode=True)


@pytest.fixture
def client(app_settings: AppSettings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.providers import MockSqlGenerator

    app = create_app(settings=app_settings, provider=MockSqlGenerator())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def settings() -> Settings:
    settings = Settings.load()
    with settings.connect("hardened") as conn:
        assert_target(conn, "hardened", settings)
    return settings
