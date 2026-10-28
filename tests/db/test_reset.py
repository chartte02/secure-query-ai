from __future__ import annotations

import json
from dataclasses import replace

import pytest

from db.manage import assert_target, initialize, snapshot
from db.settings import ROOT, Settings

pytestmark = pytest.mark.database


def test_clean_database_matches_frozen_seed_manifest(settings: Settings) -> None:
    expected = json.loads((ROOT / "db" / "seed" / "manifest.json").read_text(encoding="utf-8"))
    with settings.connect() as conn:
        assert snapshot(conn) == expected


def test_reset_guard_rejects_wrong_ownership_marker_before_any_drop(settings: Settings) -> None:
    with settings.connect() as conn:
        original = snapshot(conn)
        wrong = replace(settings, installation_id="00000000-0000-0000-0000-000000000000")
        with pytest.raises(RuntimeError, match="ownership marker"):
            assert_target(conn, "hardened", wrong)
        assert snapshot(conn) == original


def test_idempotent_initialization_keeps_data_and_reports_existing_fixture(
    settings: Settings,
) -> None:
    report = initialize()
    assert report["status"] == "already_initialized"
    assert report["fixture"] == "clean"
    with settings.connect() as conn:
        assert report["sha256"] == snapshot(conn)["sha256"]
