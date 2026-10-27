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
    principal_id: Literal["student_001", "teacher_001", "admin_demo"]
    prompt_profile: PromptProfile
    context_profile: Literal["clean", "poisoned_course_note"] = "clean"


class ModelGeneration(StrictModel):
    sql: str | None = Field(default=None, max_length=10_000)
    refusal_reason: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def require_exactly_one_outcome(self) -> "ModelGeneration":
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

