from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.providers import MockSqlGenerator


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings(provider="mock", demo_mode=True)


@pytest.fixture
def client(settings: AppSettings):
    app = create_app(settings=settings, provider=MockSqlGenerator())
    with TestClient(app) as test_client:
        yield test_client

