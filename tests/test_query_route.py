from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.config import AppSettings
from app.gateway import GatewayOutcome, GatewayUnavailable
from app.main import create_app
from app.models import (
    GatewayHandoff,
    QueryColumn,
    QueryGatewayDecision,
    QueryResult,
)
from app.providers import MockSqlGenerator, ProviderRequest

NORMAL_QUESTION = "查询我在《数据库原理及安全》这门课的成绩，包括课程名称和分数。"
DANGEROUS_QUESTION = "删除我教学班里所有低于 60 分的成绩记录。"


class RecordingGateway:
    def __init__(
        self,
        outcome: GatewayOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.error = error
        self.handoffs: list[GatewayHandoff] = []

    async def inspect_and_execute(self, handoff: GatewayHandoff) -> GatewayOutcome:
        self.handoffs.append(handoff)
        if self.error is not None:
            raise self.error
        assert self.outcome is not None
        return self.outcome


class BadOutputProvider(MockSqlGenerator):
    async def generate(self, request: ProviderRequest) -> str:
        return "```json\n{bad}\n```"


def decision(value: str, reason_code: str = "test_reason") -> QueryGatewayDecision:
    return QueryGatewayDecision(
        decision=value,
        reason_code=reason_code,
        audit_id="audit-0001",
        policy_version="campus_policy_v1",
    )


def sample_result() -> QueryResult:
    return QueryResult(
        columns=[
            QueryColumn(name="course_name", type="text"),
            QueryColumn(name="score", type="numeric"),
        ],
        rows=[["数据库原理及安全", 52.0]],
        row_count=1,
        truncated=False,
        masked_columns=[],
        execution_ms=12,
    )


def make_client(
    gateway: RecordingGateway | None = None,
    provider: MockSqlGenerator | None = None,
) -> TestClient:
    settings = AppSettings(provider="mock", demo_mode=True)
    app = create_app(
        settings=settings,
        provider=provider or MockSqlGenerator(),
        gateway=gateway,
    )
    return TestClient(app)


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "question": NORMAL_QUESTION,
        "principal_id": "student_s01",
        "context_profile": "clean",
    }
    body.update(overrides)
    return body


def test_refused_query_never_reaches_gateway() -> None:
    gateway = RecordingGateway()
    with make_client(gateway) as client:
        response = client.post("/api/v1/queries", json=payload(question=DANGEROUS_QUESTION))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refused"
    assert body["gateway"] is None
    assert body["result"] is None
    assert gateway.handoffs == []


def test_invalid_model_output_never_reaches_gateway() -> None:
    gateway = RecordingGateway()
    with make_client(gateway, BadOutputProvider()) as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 200
    assert response.json()["status"] == "invalid_output"
    assert gateway.handoffs == []


def test_unconnected_gateway_returns_503_with_generation() -> None:
    with make_client() as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["generation"]["status"] == "generated"
    assert body["generation"]["candidate_sql"].startswith("SELECT")
    assert body["gateway"] is None
    assert body["result"] is None


def test_gateway_failure_returns_503_without_faking_result() -> None:
    gateway = RecordingGateway(error=GatewayUnavailable("offline"))
    with make_client(gateway) as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["result"] is None


def test_gateway_block_returns_decision_without_result() -> None:
    gateway = RecordingGateway(GatewayOutcome(decision=decision("BLOCK"), result=None))
    with make_client(gateway) as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["gateway"]["decision"] == "BLOCK"
    assert body["result"] is None
    handoff = gateway.handoffs[0]
    assert handoff.principal_id == "student_s01"
    assert handoff.schema_version == "campus_lab_v1"
    assert handoff.candidate_sql.startswith("SELECT")


def test_block_with_result_is_treated_as_unavailable() -> None:
    gateway = RecordingGateway(
        GatewayOutcome(decision=decision("BLOCK"), result=sample_result())
    )
    with make_client(gateway) as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["result"] is None


def test_gateway_execution_returns_result_and_mask_metadata() -> None:
    gateway = RecordingGateway(
        GatewayOutcome(decision=decision("MASK"), result=sample_result())
    )
    with make_client(gateway) as client:
        response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "executed"
    assert body["gateway"]["decision"] == "MASK"
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"] == [["数据库原理及安全", 52.0]]


def test_query_request_rejects_identity_sql_and_profile_override() -> None:
    with make_client() as client:
        identity = client.post(
            "/api/v1/queries",
            json=payload(
                principal_id="attacker",
                candidate_sql="DROP TABLE academic.students",
            ),
        )
        profile = client.post("/api/v1/queries", json=payload(prompt_profile="baseline"))
    assert identity.status_code == 422
    assert identity.json()["error"]["code"] == "invalid_request"
    assert "attacker" not in identity.text
    assert profile.status_code == 422


def test_query_audit_log_contains_digest_not_question_or_sql(caplog) -> None:
    gateway = RecordingGateway(
        GatewayOutcome(decision=decision("ALLOW"), result=sample_result())
    )
    with caplog.at_level(logging.INFO, logger="securequery.audit"):
        with make_client(gateway) as client:
            response = client.post("/api/v1/queries", json=payload())
    assert response.status_code == 200
    combined = "\n".join(record.message for record in caplog.records)
    assert "query_completed" in combined
    assert "sql_digest" in combined
    assert NORMAL_QUESTION not in combined
    assert "SELECT" not in combined


def test_health_and_catalog_report_gateway_state() -> None:
    with make_client() as client:
        assert client.get("/api/v1/health").json()["gateway_connected"] is False
        catalog = client.get("/api/v1/demo/catalog").json()
        assert catalog["deployment"]["gateway_connected"] is False
    gateway = RecordingGateway(GatewayOutcome(decision=decision("BLOCK"), result=None))
    with make_client(gateway) as client:
        assert client.get("/api/v1/health").json()["gateway_connected"] is True
        catalog = client.get("/api/v1/demo/catalog").json()
        assert catalog["deployment"]["gateway_connected"] is True
