from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptProfile(StrEnum):
    BASELINE = "baseline"
    HARDENED = "hardened"


class GenerationRequest(StrictModel):
    question: str = Field(min_length=1, max_length=1_000)
    principal_id: Literal["student_s01", "student_s02", "teacher_t01"]
    prompt_profile: PromptProfile
    context_profile: Literal["clean", "poisoned_course_note"] = "clean"


class ModelGeneration(StrictModel):
    sql: str | None = Field(default=None, max_length=10_000)
    refusal_reason: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def require_exactly_one_outcome(self) -> ModelGeneration:
        if self.sql is not None:
            self.sql = self.sql.strip()
        if self.refusal_reason is not None:
            self.refusal_reason = self.refusal_reason.strip()
        has_sql = bool(self.sql)
        has_refusal = bool(self.refusal_reason)
        if has_sql == has_refusal:
            raise ValueError("exactly one of sql or refusal_reason must be non-empty")
        return self


class SqlDiagnostics(StrictModel):
    parseable: bool
    statement_count: int
    statement_types: list[str]
    tables: list[str]
    columns: list[str]
    warnings: list[str]


class Provenance(StrictModel):
    provider: Literal["mock", "ollama"]
    model: str
    model_digest: str | None
    prompt_version: str
    prompt_hash: str
    schema_version: str
    context_profile: str
    latency_ms: int


class GenerationResponse(StrictModel):
    request_id: str
    status: Literal["generated", "refused", "invalid_output"]
    candidate_sql: str | None
    refusal_reason: str | None
    raw_model_output: str | None
    diagnostics: SqlDiagnostics
    provenance: Provenance


class GatewayHandoff(StrictModel):
    request_id: str
    principal_id: str
    candidate_sql: str
    schema_version: str


class QueryRequest(StrictModel):
    """Normal query entry. It never accepts SQL, roles, DSNs, or a prompt profile."""

    question: str = Field(min_length=1, max_length=1_000)
    principal_id: Literal["student_s01", "student_s02", "teacher_t01"]
    context_profile: Literal["clean", "poisoned_course_note"] = "clean"


class QueryGatewayDecision(StrictModel):
    decision: Literal["ALLOW", "MASK", "BLOCK"]
    reason_code: str = Field(min_length=1, max_length=100)
    audit_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)


class QueryColumn(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)


class QueryResult(StrictModel):
    columns: list[QueryColumn]
    rows: list[list[str | int | float | bool | None]]
    row_count: int = Field(ge=0)
    truncated: bool
    masked_columns: list[str]
    execution_ms: int = Field(ge=0)


class QueryError(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    stage: Literal["gateway", "database"]
    sqlstate: str | None = Field(default=None, min_length=5, max_length=5)
    message: str = Field(min_length=1, max_length=300)


class QueryResponse(StrictModel):
    request_id: str
    status: Literal[
        "refused", "invalid_output", "blocked", "executed", "unavailable", "error"
    ]
    generation: GenerationResponse
    gateway: QueryGatewayDecision | None = None
    result: QueryResult | None = None
    error: QueryError | None = None
    db_role: str | None = Field(default=None, max_length=100)
    executor: Literal["gateway", "lab_direct"] = "gateway"

    @model_validator(mode="after")
    def require_consistent_outcome(self) -> QueryResponse:
        if self.status in {"refused", "invalid_output", "unavailable"}:
            if self.gateway is not None or self.result is not None or self.error is not None:
                raise ValueError("non-executed responses cannot carry gateway, result, or error")
        elif self.status == "blocked":
            if self.gateway is None or self.result is not None or self.error is not None:
                raise ValueError("blocked responses require a decision and no result or error")
            if self.gateway.decision != "BLOCK":
                raise ValueError("blocked status requires a BLOCK decision")
        elif self.status == "error":
            if self.error is None or self.result is not None:
                raise ValueError("error responses require an error and no result")
        else:
            if self.gateway is None or self.result is None:
                raise ValueError("executed responses require a decision and a result")
            if self.error is not None:
                raise ValueError("executed responses cannot carry an error")
            if self.gateway.decision not in {"ALLOW", "MASK"}:
                raise ValueError("executed status requires ALLOW or MASK")
        return self


class LabReplayResponse(StrictModel):
    """Fixed-SQL replay for observing member B's controls. The model is not invoked."""

    request_id: str
    scenario_id: str
    label: str
    expectation: str
    principal_id: str
    candidate_origin: Literal["fixed_sql_replay"] = "fixed_sql_replay"
    model_invoked: bool = False
    executor: Literal["lab_direct"] = "lab_direct"
    candidate_sql: str
    gateway: QueryGatewayDecision | None = None
    result: QueryResult | None = None
    error: QueryError | None = None
    db_role: str | None = None

    @model_validator(mode="after")
    def require_exactly_one_outcome(self) -> LabReplayResponse:
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of result or error must be present")
        return self

