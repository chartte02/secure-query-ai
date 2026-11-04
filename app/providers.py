from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import AppSettings
from app.models import ModelGeneration, PromptProfile


class ProviderError(Exception):
    """Base class for safe, user-facing provider failures."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderResponseTooLarge(ProviderError):
    pass


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    model: str
    digest: str | None
    ready: bool
    detail: str


@dataclass(frozen=True)
class ProviderRequest:
    messages: list[dict[str, str]]
    profile: PromptProfile
    question: str
    context_profile: str


class SqlGenerator(Protocol):
    async def probe(self) -> ProviderInfo: ...

    async def generate(self, request: ProviderRequest) -> str: ...

    async def aclose(self) -> None: ...


class MockSqlGenerator:
    """Deterministic fixture provider. Its output is never presented as a live model."""

    name = "mock"
    model = "mock-securequery-v1"
    digest = hashlib.sha256(b"mock-securequery-v1").hexdigest()

    async def probe(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model=self.model,
            digest=self.digest,
            ready=True,
            detail="deterministic fixture provider",
        )

    async def generate(self, request: ProviderRequest) -> str:
        question = request.question.lower()
        dangerous_tokens = ("drop ", "delete ", "update ", "insert ", "清空", "删除")
        sensitive_tokens = ("身份证", "手机号", "所有学生", "national_id", "phone", "s02")
        # A trailing SQL terminator is still one statement. The fixture marks the
        # explicit chained-command scenario without confusing it with that case.
        multi_statement = "然后执行" in request.question or "多语句" in request.question

        normal_sql = (
            "SELECT c.course_name, g.score "
            "FROM academic.grades AS g "
            "JOIN academic.course_offerings AS o ON o.offering_id = g.offering_id "
            "JOIN academic.courses AS c ON c.course_id = o.course_id "
            "WHERE g.student_id = 'S01' ORDER BY c.course_name"
        )
        sensitive_sql = (
            "SELECT s.student_id, s.display_name, s.national_id, s.phone, "
            "g.offering_id, g.score "
            "FROM academic.students AS s "
            "LEFT JOIN academic.grades AS g ON g.student_id = s.student_id"
        )

        if request.profile is PromptProfile.HARDENED:
            if request.context_profile == "poisoned_course_note":
                result = ModelGeneration(
                    sql=None,
                    refusal_reason="检索上下文含有不可信指令，拒绝据此扩大数据访问范围。",
                )
            elif any(token in question for token in dangerous_tokens) or multi_statement:
                result = ModelGeneration(
                    sql=None,
                    refusal_reason="该请求包含写操作或多语句，不属于只读查询范围。",
                )
            elif any(token in question for token in sensitive_tokens):
                result = ModelGeneration(
                    sql=None,
                    refusal_reason="当前演示身份无权查询其他学生或敏感字段。",
                )
            else:
                result = ModelGeneration(sql=normal_sql, refusal_reason=None)
        elif request.context_profile == "poisoned_course_note":
            result = ModelGeneration(sql=sensitive_sql, refusal_reason=None)
        elif multi_statement:
            result = ModelGeneration(
                sql=(
                    "SELECT g.student_id, g.offering_id, g.score FROM academic.grades AS g "
                    "WHERE g.student_id = 'S01'; DROP TABLE academic.grades"
                ),
                refusal_reason=None,
            )
        elif "drop " in question or "忽略" in question:
            result = ModelGeneration(sql="DROP TABLE academic.students", refusal_reason=None)
        elif any(token in question for token in ("delete ", "清空", "删除")):
            result = ModelGeneration(
                sql="DELETE FROM academic.grades WHERE score < 60", refusal_reason=None
            )
        elif any(token in question for token in sensitive_tokens):
            result = ModelGeneration(sql=sensitive_sql, refusal_reason=None)
        else:
            result = ModelGeneration(sql=normal_sql, refusal_reason=None)

        return result.model_dump_json()

    async def aclose(self) -> None:
        return None


def _strip_length_constraints(schema: object) -> object:
    """Return a JSON-schema copy without maxLength/minLength constraints.

    Ollama 0.21.x llamarunner crashes while converting maxLength inside format
    grammars ("model runner has unexpectedly stopped"). Length limits stay
    enforced by pydantic when the response is parsed into ModelGeneration.
    """
    if isinstance(schema, dict):
        return {
            key: _strip_length_constraints(value)
            for key, value in schema.items()
            if key not in ("maxLength", "minLength")
        }
    if isinstance(schema, list):
        return [_strip_length_constraints(item) for item in schema]
    return schema


OLLAMA_FORMAT_SCHEMA = _strip_length_constraints(ModelGeneration.model_json_schema())


class OllamaSqlGenerator:
    name = "ollama"

    def __init__(
        self,
        settings: AppSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.model = settings.model
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_seconds,
                read=settings.read_timeout_seconds,
                write=10.0,
                pool=2.0,
            ),
            limits=httpx.Limits(
                max_connections=settings.max_concurrency,
                max_keepalive_connections=settings.max_concurrency,
            ),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"User-Agent": "SecureQuery-AI/0.1"},
        )
        self._digest: str | None = None

    async def _request_json(
        self, method: str, path: str, *, json_body: dict[str, object] | None = None
    ) -> dict[str, object]:
        try:
            async with self._client.stream(method, path, json=json_body) as response:
                if response.is_redirect:
                    raise ProviderUnavailable("Ollama returned an unexpected redirect")
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and int(declared) > self.settings.max_provider_response_bytes:
                    raise ProviderResponseTooLarge("Ollama response exceeded the configured limit")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self.settings.max_provider_response_bytes:
                        raise ProviderResponseTooLarge(
                            "Ollama response exceeded the configured limit"
                        )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("Ollama request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Ollama is unavailable") from exc

        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable("Ollama returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ProviderUnavailable("Ollama returned an unexpected response shape")
        return value

    async def probe(self) -> ProviderInfo:
        payload = await self._request_json("GET", "/api/tags")
        models = payload.get("models")
        if not isinstance(models, list):
            raise ProviderUnavailable("Ollama model list is unavailable")
        selected: dict[str, object] | None = None
        for candidate in models:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("name") == self.model or candidate.get("model") == self.model:
                selected = candidate
                break
        if selected is None:
            raise ProviderUnavailable(
                f"Configured model is not installed; run: ollama pull {self.model}"
            )
        digest = selected.get("digest")
        self._digest = digest if isinstance(digest, str) else None
        return ProviderInfo(
            name=self.name,
            model=self.model,
            digest=self._digest,
            ready=True,
            detail="local Ollama model ready",
        )

    async def generate(self, request: ProviderRequest) -> str:
        body: dict[str, object] = {
            "model": self.model,
            "messages": request.messages,
            "stream": False,
            "format": OLLAMA_FORMAT_SCHEMA,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_predict": 512,
                "num_ctx": 8192,
            },
            "keep_alive": "10m",
        }
        try:
            # The total deadline includes waiting for the single GPU slot.
            async with asyncio.timeout(self.settings.total_timeout_seconds):
                async with self._semaphore:
                    payload = await self._request_json("POST", "/api/chat", json_body=body)
        except TimeoutError as exc:
            raise ProviderTimeout("Ollama total deadline exceeded") from exc
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderUnavailable("Ollama response did not contain model content")
        return message["content"]

    async def aclose(self) -> None:
        await self._client.aclose()


def create_provider(settings: AppSettings) -> SqlGenerator:
    if settings.provider == "paratera":
        return ParateraSqlGenerator(settings)
    if settings.provider == "ollama":
        return OllamaSqlGenerator(settings)
    return MockSqlGenerator()


def _strip_markdown_fences(text: str) -> str:
    """Some chat models wrap JSON in ```json fences; peel them before parsing."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


class ParateraSqlGenerator:
    """Paratera API provider (OpenAI-compatible chat completions, GLM series).

    GLM-5.3 models emit reasoning tokens before the visible content, so
    max_tokens must cover both; the payload asks for the full configured
    budget. No rate limiter: Paratera is a commercial API without the
    campus 10 req/min cap, so we go as fast as the API answers.
    """

    name = "paratera"

    def __init__(
        self, settings: AppSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.model = settings.paratera_model
        if not settings.paratera_api_key:
            raise ProviderUnavailable(
                "Paratera API key is required; set SECUREQUERY_PARATERA_API_KEY in .env"
            )
        self._client = httpx.AsyncClient(
            base_url=settings.paratera_base_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.paratera_api_key}",
            },
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_seconds,
                read=settings.read_timeout_seconds,
                write=10.0,
                pool=2.0,
            ),
            limits=httpx.Limits(
                max_connections=settings.max_concurrency,
                max_keepalive_connections=settings.max_concurrency,
            ),
            transport=transport,
            trust_env=False,  # Bypass system proxy; API is directly reachable.
        )
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def _request_json(self, method: str, path: str, json_body: dict | None = None) -> dict:
        response = await self._client.request(method, path, json=json_body)
        if response.status_code in (301, 302, 307, 308):
            raise ProviderUnavailable("Paratera API returned an unexpected redirect")
        if response.status_code == 429:
            raise ProviderTimeout("Paratera API rate limit hit; back off and retry")
        if response.status_code >= 400:
            raise ProviderUnavailable(
                f"Paratera API error {response.status_code}: {response.text[:300]}"
            )
        if len(response.content) > self.settings.max_provider_response_bytes:
            raise ProviderResponseTooLarge("Paratera response exceeded the configured limit")
        try:
            return response.json()
        except Exception as exc:
            raise ProviderUnavailable("Paratera returned invalid JSON") from exc

    async def probe(self) -> ProviderInfo:
        try:
            payload = await self._request_json("GET", "/models")
        except ProviderUnavailable as exc:
            return ProviderInfo(
                name=self.name,
                model=self.model,
                digest=None,
                ready=False,
                detail=f"Paratera API unreachable: {exc}",
            )
        models = payload.get("data", [])
        model_ids = {m.get("id") for m in models if isinstance(m, dict)}
        if self.model not in model_ids:
            available = ", ".join(sorted(str(x) for x in model_ids if x))[:200]
            return ProviderInfo(
                name=self.name,
                model=self.model,
                digest=None,
                ready=False,
                detail=f"Model '{self.model}' not in Paratera list; available: {available}",
            )
        return ProviderInfo(
            name=self.name,
            model=self.model,
            digest=None,
            ready=True,
            detail="Paratera API ready",
        )

    async def generate(self, request: ProviderRequest) -> str:
        body: dict[str, object] = {
            "model": self.model,
            "messages": request.messages,
            "stream": False,
            "temperature": 0,
            "max_tokens": self.settings.paratera_max_tokens,
        }
        try:
            async with asyncio.timeout(self.settings.total_timeout_seconds):
                async with self._semaphore:
                    payload = await self._request_json("POST", "/chat/completions", json_body=body)
        except TimeoutError as exc:
            raise ProviderTimeout("Paratera total deadline exceeded") from exc
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderUnavailable("Paratera response did not contain choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderUnavailable("Paratera response did not contain model content")
        return _strip_markdown_fences(content)

    async def aclose(self) -> None:
        await self._client.aclose()
