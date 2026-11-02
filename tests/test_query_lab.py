"""Integration checks for the demo-only lab executor (requires the Docker lab)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.models import ModelGeneration
from app.providers import MockSqlGenerator, ProviderRequest

pytestmark = pytest.mark.database


class FixedSqlProvider(MockSqlGenerator):
    def __init__(self, sql: str) -> None:
        self.sql = sql

    async def generate(self, request: ProviderRequest) -> str:
        return ModelGeneration(sql=self.sql, refusal_reason=None).model_dump_json()


def make_client(provider: MockSqlGenerator | None = None) -> TestClient:
    settings = AppSettings(provider="mock", demo_mode=True, lab_gateway=True)
    return TestClient(create_app(settings=settings, provider=provider or MockSqlGenerator()))


def make_plain_client() -> TestClient:
    settings = AppSettings(provider="mock", demo_mode=True, lab_gateway=False)
    return TestClient(create_app(settings=settings, provider=MockSqlGenerator()))


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "question": "查询我的成绩",
        "principal_id": "student_s01",
        "context_profile": "clean",
    }
    body.update(overrides)
    return body


def test_lab_gateway_returns_real_rows_and_db_role() -> None:
    with make_client() as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "executed"
    assert body["executor"] == "lab_direct"
    assert body["db_role"] == "sq_student_s01"
    assert body["result"]["row_count"] == 3
    assert body["error"] is None


def test_rls_cross_student_read_is_empty_not_an_error() -> None:
    provider = FixedSqlProvider(
        "SELECT student_id, offering_id, score FROM academic.grades "
        "WHERE student_id = 'S02'"
    )
    with make_client(provider) as client:
        response = client.post("/api/v1/queries", json=payload())
    body = response.json()
    assert body["status"] == "executed"
    assert body["result"]["row_count"] == 0
    assert body["error"] is None
    assert body["db_role"] == "sq_student_s01"


def test_sensitive_column_read_returns_sqlstate_42501() -> None:
    provider = FixedSqlProvider("SELECT national_id FROM academic.students")
    with make_client(provider) as client:
        response = client.post("/api/v1/queries", json=payload())
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "error"
    assert body["error"]["stage"] == "database"
    assert body["error"]["sqlstate"] == "42501"
    assert body["error"]["code"] == "database_permission_denied"
    assert body["result"] is None
    assert body["db_role"] == "sq_student_s01"


def test_write_is_rejected_by_read_only_role() -> None:
    provider = FixedSqlProvider("DELETE FROM academic.grades WHERE score < 60")
    with make_client(provider) as client:
        response = client.post("/api/v1/queries", json=payload())
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["stage"] == "database"
    assert body["error"]["sqlstate"] in {"25006", "42501"}
    assert body["result"] is None


def test_result_is_limited_to_100_rows() -> None:
    provider = FixedSqlProvider("SELECT generate_series(1, 150) AS n")
    with make_client(provider) as client:
        response = client.post("/api/v1/queries", json=payload())
    body = response.json()
    assert body["status"] == "executed"
    assert body["result"]["row_count"] == 100
    assert body["result"]["truncated"] is True


def test_health_reports_lab_direct_executor() -> None:
    with make_client() as client:
        health = client.get("/api/v1/health").json()
        catalog = client.get("/api/v1/demo/catalog").json()
    assert health["executor"] == "lab_direct"
    assert health["gateway_connected"] is False
    assert catalog["deployment"]["database_connected"] is True


def test_lab_replay_own_grades_returns_rows() -> None:
    with make_client() as client:
        response = client.post("/api/v1/lab/replay/own_grades", json={})
    body = response.json()
    assert response.status_code == 200
    assert body["candidate_origin"] == "fixed_sql_replay"
    assert body["model_invoked"] is False
    assert body["db_role"] == "sq_student_s01"
    assert body["result"]["row_count"] == 3
    assert body["error"] is None


def test_lab_replay_column_denied_returns_sqlstate() -> None:
    with make_client() as client:
        response = client.post("/api/v1/lab/replay/column_denied", json={})
    body = response.json()
    assert body["error"]["sqlstate"] == "42501"
    assert body["error"]["code"] == "database_permission_denied"
    assert body["result"] is None
    assert body["db_role"] == "sq_student_s01"


def test_lab_replay_rls_cross_student_is_empty() -> None:
    with make_client() as client:
        body = client.post("/api/v1/lab/replay/rls_cross_student", json={}).json()
    assert body["error"] is None
    assert body["result"]["row_count"] == 0


def test_lab_replay_write_is_denied() -> None:
    with make_client() as client:
        body = client.post("/api/v1/lab/replay/write_denied", json={}).json()
    assert body["error"]["sqlstate"] in {"25006", "42501"}


def test_lab_scenarios_are_listed() -> None:
    with make_client() as client:
        body = client.get("/api/v1/lab/scenarios").json()
    ids = {item["id"] for item in body["scenarios"]}
    assert {"own_grades", "rls_cross_student", "column_denied", "write_denied"} <= ids


def test_lab_routes_are_disabled_without_lab_gateway() -> None:
    with make_plain_client() as client:
        listing = client.get("/api/v1/lab/scenarios")
        replay = client.post("/api/v1/lab/replay/own_grades", json={})
    assert listing.status_code == 403
    assert replay.status_code == 403
