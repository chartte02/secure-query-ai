from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from time import perf_counter

from pydantic import ValidationError

from app.catalog import PRINCIPALS, SCHEMA_VERSION
from app.config import AppSettings
from app.diagnostics import diagnose_sql
from app.models import GenerationRequest, GenerationResponse, ModelGeneration, Provenance
from app.prompts import build_prompt
from app.providers import (
    ProviderError,
    ProviderInfo,
    ProviderRequest,
    SqlGenerator,
)

LOGGER = logging.getLogger("securequery.audit")


class GenerationService:
    def __init__(self, settings: AppSettings, provider: SqlGenerator) -> None:
        self.settings = settings
        self.provider = provider
        self.provider_info = ProviderInfo(
            name=settings.provider,
            model=settings.model if settings.provider == "ollama" else "mock-securequery-v1",
            digest=None,
            ready=False,
            detail="provider has not been probed",
        )

    async def startup(self) -> None:
        try:
            self.provider_info = await self.provider.probe()
        except ProviderError as exc:
            self.provider_info = ProviderInfo(
                name=self.settings.provider,
                model=self.settings.model,
                digest=None,
                ready=False,
                detail=str(exc),
            )

    async def close(self) -> None:
        await self.provider.aclose()

    def health(self) -> dict[str, object]:
        return {
            "status": "ready" if self.provider_info.ready else "degraded",
            "provider": asdict(self.provider_info),
            "schema_version": SCHEMA_VERSION,
            "demo_mode": self.settings.demo_mode,
            "notice": "Candidate SQL is never executed by this service.",
        }

    async def generate(
        self, request_id: str, request: GenerationRequest
    ) -> GenerationResponse:
        if request.prompt_profile.value == "baseline" and not self.settings.demo_mode:
            raise PermissionError("baseline profile is disabled outside demo mode")
        if request.context_profile != "clean" and not self.settings.demo_mode:
            raise PermissionError("untrusted demo context is disabled outside demo mode")

        principal = PRINCIPALS[request.principal_id]
        prompt = build_prompt(
            profile=request.prompt_profile,
            principal=principal,
            question=request.question,
            context_profile=request.context_profile,
        )
        provider_request = ProviderRequest(
            messages=prompt.messages,
            profile=request.prompt_profile,
            question=request.question,
            context_profile=request.context_profile,
        )

        started = perf_counter()
        raw = await self.provider.generate(provider_request)
        latency_ms = round((perf_counter() - started) * 1_000)
        try:
            generated = ModelGeneration.model_validate_json(raw)
        except ValidationError:
            status = "invalid_output"
            candidate_sql = None
            refusal_reason = "模型输出不符合严格 JSON 契约。"
        else:
            candidate_sql = generated.sql
            refusal_reason = generated.refusal_reason
            status = "generated" if candidate_sql else "refused"

        diagnostics = diagnose_sql(candidate_sql)
        if candidate_sql and not diagnostics.parseable:
            status = "invalid_output"
            candidate_sql = None
            refusal_reason = "模型输出未构成可解析的 PostgreSQL 语句。"

        raw_for_response = None
        if self.settings.demo_mode:
            raw_for_response = raw[: self.settings.max_raw_output_chars]

        info = self.provider_info
        if not info.ready:
            # A successful generation proves the provider became available after startup.
            try:
                info = await self.provider.probe()
            except ProviderError:
                info = ProviderInfo(
                    name=self.settings.provider,
                    model=getattr(self.provider, "model", self.settings.model),
                    digest=getattr(self.provider, "_digest", None),
                    ready=True,
                    detail="provider responded; model digest could not be verified",
                )
            self.provider_info = info

        response = GenerationResponse(
            request_id=request_id,
            status=status,
            candidate_sql=candidate_sql,
            refusal_reason=refusal_reason,
            raw_model_output=raw_for_response,
            diagnostics=diagnostics,
            provenance=Provenance(
                provider=info.name,  # type: ignore[arg-type]
                model=info.model,
                model_digest=info.digest,
                prompt_version=prompt.version,
                prompt_hash=prompt.content_hash,
                schema_version=SCHEMA_VERSION,
                context_profile=request.context_profile,
                latency_ms=latency_ms,
            ),
        )
        question_hash = hashlib.sha256(request.question.encode("utf-8")).hexdigest()[:16]
        LOGGER.info(
            json.dumps(
                {
                    "event": "candidate_generated",
                    "request_id": request_id,
                    "question_hash": question_hash,
                    "question_length": len(request.question),
                    "provider": info.name,
                    "model": info.model,
                    "prompt_version": prompt.version,
                    "status": status,
                    "latency_ms": latency_ms,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        return response

