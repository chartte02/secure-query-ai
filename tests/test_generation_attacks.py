from __future__ import annotations

import pytest

from app.catalog import SCENARIOS

ATTACK_SCENARIOS = [scenario for scenario in SCENARIOS if scenario.get("kind") == "attack"]


@pytest.mark.parametrize(
    "scenario", ATTACK_SCENARIOS, ids=[case["id"] for case in ATTACK_SCENARIOS]
)
def test_mock_attack_pair_is_explicit_and_never_executed(client, scenario) -> None:
    request = {
        key: scenario[key] for key in ("question", "principal_id", "context_profile")
    }
    baseline = client.post(
        "/api/v1/generations", json={**request, "prompt_profile": "baseline"}
    ).json()
    hardened = client.post(
        "/api/v1/generations", json={**request, "prompt_profile": "hardened"}
    ).json()
    assert baseline["provenance"]["provider"] == "mock"
    assert baseline["candidate_sql"]
    assert hardened["status"] == "refused"
    assert hardened["candidate_sql"] is None
    assert "decision" not in baseline  # A's diagnostics never authorize SQL.
