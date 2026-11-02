from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.catalog import SCHEMA_VERSION, public_catalog
from app.config import AppSettings
from app.gateway import GatewayUnavailable, NotConnectedGateway, SqlGateway
from app.models import (
    GatewayHandoff,
    GenerationRequest,
    GenerationResponse,
    LabReplayResponse,
    PromptProfile,
    QueryRequest,
    QueryResponse,
)
from app.prompts import load_prompt
from app.providers import (
    ProviderResponseTooLarge,
    ProviderTimeout,
    ProviderUnavailable,
    SqlGenerator,
    create_provider,
)
from app.query_service import QueryService
from app.service import GenerationService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}, "request_id": request_id},
        headers={"Cache-Control": "no-store"},
    )


def create_app(
    settings: AppSettings | None = None,
    provider: SqlGenerator | None = None,
    gateway: SqlGateway | None = None,
) -> FastAPI:
    resolved_settings = settings or AppSettings()
    resolved_provider = provider or create_provider(resolved_settings)
    service = GenerationService(resolved_settings, resolved_provider)
    if gateway is not None:
        resolved_gateway: SqlGateway = gateway
    elif resolved_settings.demo_mode and resolved_settings.lab_gateway:
        # Import lazily so the default service stays free of database drivers.
        from app.lab_gateway import LocalLabGateway

        resolved_gateway = LocalLabGateway()
    else:
        resolved_gateway = NotConnectedGateway()
    query_service = QueryService(service, resolved_gateway)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await service.startup()
        yield
        await service.close()

    docs_enabled = resolved_settings.demo_mode
    application = FastAPI(
        title="SecureQuery AI",
        version="0.1.0",
        debug=False,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.generation_service = service
    application.state.query_service = query_service
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    @application.middleware("http")
    async def security_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = str(uuid4())
        if request.method == "POST" and request.url.path.startswith("/api/"):
            content_length = request.headers.get("content-length")
            if content_length is None:
                return _error_response(
                    request, 411, "length_required", "Content-Length is required."
                )
            try:
                declared_length = int(content_length)
            except ValueError:
                return _error_response(
                    request, 400, "invalid_content_length", "Content-Length is invalid."
                )
            if declared_length < 0:
                return _error_response(
                    request, 400, "invalid_content_length", "Content-Length is invalid."
                )
            if declared_length > resolved_settings.max_request_bytes:
                return _error_response(
                    request, 413, "request_too_large", "Request body is too large."
                )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        # Also prevent a long-lived demo tab from mixing a new HTML page with
        # stale JavaScript/CSS after a local update.
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, _: RequestValidationError
    ) -> JSONResponse:
        return _error_response(request, 422, "invalid_request", "Request validation failed.")

    @application.exception_handler(ProviderTimeout)
    async def provider_timeout_handler(request: Request, _: ProviderTimeout) -> JSONResponse:
        return _error_response(request, 504, "provider_timeout", "Local model timed out.")

    @application.exception_handler(ProviderResponseTooLarge)
    async def provider_size_handler(
        request: Request, _: ProviderResponseTooLarge
    ) -> JSONResponse:
        return _error_response(
            request, 503, "provider_response_too_large", "Local model response was too large."
        )

    @application.exception_handler(ProviderUnavailable)
    async def provider_unavailable_handler(
        request: Request, _: ProviderUnavailable
    ) -> JSONResponse:
        return _error_response(
            request, 503, "provider_unavailable", "Local model is unavailable."
        )

    @application.exception_handler(GatewayUnavailable)
    async def gateway_unavailable_handler(
        request: Request, _: GatewayUnavailable
    ) -> JSONResponse:
        return _error_response(
            request, 503, "gateway_unavailable", "SQL gateway is not connected."
        )

    @application.exception_handler(PermissionError)
    async def forbidden_demo_handler(request: Request, _: PermissionError) -> JSONResponse:
        return _error_response(
            request, 403, "demo_feature_disabled", "This demo feature is disabled."
        )

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("securequery.error").error(
            "Unhandled request failure request_id=%s type=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        return _error_response(request, 500, "internal_error", "Internal service error.")

    @application.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            **service.health(),
            "gateway_connected": query_service.gateway_connected,
            "executor": query_service.executor,
        }

    @application.get("/api/v1/demo/catalog")
    async def demo_catalog() -> dict[str, object]:
        catalog = public_catalog(resolved_settings.demo_mode)
        catalog["provider"] = service.health()["provider"]
        catalog["deployment"] = {
            "ollama_url": resolved_settings.ollama_base_url,
            "gateway_connected": query_service.gateway_connected,
            # The generation service still holds no database credentials.
            "database_connected": query_service.executor == "lab_direct",
            "executor": query_service.executor,
        }
        catalog["prompt_versions"] = [
            load_prompt(profile)[0]
            for profile in PromptProfile
            if resolved_settings.demo_mode or profile is PromptProfile.HARDENED
        ]
        return catalog

    @application.post("/api/v1/generations", response_model=GenerationResponse)
    async def generate(request: Request, payload: GenerationRequest) -> GenerationResponse:
        return await service.generate(request.state.request_id, payload)

    @application.post(
        "/api/v1/queries",
        response_model=QueryResponse,
        responses={503: {"model": QueryResponse}},
    )
    async def query(request: Request, payload: QueryRequest) -> QueryResponse | JSONResponse:
        result = await query_service.query(request.state.request_id, payload)
        if result.status == "unavailable":
            # Component unavailable is HTTP 503, but the body keeps the
            # generation result so the page can still show the candidate.
            return JSONResponse(status_code=503, content=result.model_dump(mode="json"))
        return result

    @application.get("/api/v1/lab/scenarios")
    async def lab_scenarios() -> dict[str, object]:
        if query_service.executor != "lab_direct":
            raise PermissionError("lab gateway is disabled")
        from app.lab_gateway import LAB_SCENARIOS

        return {
            "executor": query_service.executor,
            "scenarios": [
                {"id": scenario_id, **asdict(scenario)}
                for scenario_id, scenario in LAB_SCENARIOS.items()
            ],
        }

    @application.post(
        "/api/v1/lab/replay/{scenario_id}",
        response_model=LabReplayResponse,
    )
    async def lab_replay(
        request: Request, scenario_id: str
    ) -> LabReplayResponse | JSONResponse:
        """Replay a fixed synthetic SQL to show member B's controls. No model call."""
        if query_service.executor != "lab_direct":
            raise PermissionError("lab gateway is disabled")
        from app.lab_gateway import LAB_SCENARIOS

        scenario = LAB_SCENARIOS.get(scenario_id)
        if scenario is None:
            return _error_response(
                request, 404, "unknown_scenario", "Unknown lab scenario."
            )
        outcome = await query_service.gateway.inspect_and_execute(
            GatewayHandoff(
                request_id=request.state.request_id,
                principal_id=scenario.principal_id,
                candidate_sql=scenario.sql,
                schema_version=SCHEMA_VERSION,
            )
        )
        return LabReplayResponse(
            request_id=request.state.request_id,
            scenario_id=scenario_id,
            label=scenario.label,
            expectation=scenario.expectation,
            principal_id=scenario.principal_id,
            candidate_sql=scenario.sql,
            gateway=outcome.decision,
            result=outcome.result,
            error=outcome.error,
            db_role=outcome.db_role,
        )

    application.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")

    @application.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")

    return application


app = create_app()

