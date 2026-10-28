"""Integration tests use only the marked synthetic Docker fixtures."""

from __future__ import annotations

import pytest

from db.manage import assert_target
from db.settings import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    settings = Settings.load()
    with settings.connect("hardened") as conn:
        assert_target(conn, "hardened", settings)
    return settings
