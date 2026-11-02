"""Opt-in integration tests; default pytest never contacts a model server."""
import asyncio
import os
from uuid import uuid4

import pytest

from app.config import AppSettings
from app.models import GenerationRequest
from app.providers import create_provider
from app.service import GenerationService


@pytest.mark.ollama
@pytest.mark.skipif(
    os.getenv("SECUREQUERY_RUN_OLLAMA_TESTS") != "1",
    reason="explicit local model opt-in required",
)
@pytest.mark.parametrize("model", ["qwen2.5-coder:7b", "qwen2.5-coder:3b"])
def test_local_model_generates_structured_candidate(model):
    async def run():
        settings = AppSettings(provider="ollama", model=model, demo_mode=True)
        service = GenerationService(settings, create_provider(settings))
        try:
            await service.startup()
            assert service.provider_info.ready, service.provider_info.detail
            response = await service.generate(str(uuid4()), GenerationRequest(
                question="查询我低于 60 分的课程名称和分数。", principal_id="student_s01",
                prompt_profile="hardened", context_profile="clean",
            ))
            assert response.status == "generated"
            assert response.diagnostics.parseable
            assert response.provenance.provider == "ollama"
            assert response.provenance.model_digest
            assert not response.diagnostics.warnings
        finally:
            await service.close()
    asyncio.run(run())
