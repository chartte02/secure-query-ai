from __future__ import annotations

import hashlib
import json
import logging

from app.gateway import GatewayUnavailable, NotConnectedGateway, SqlGateway
from app.models import (
    GatewayHandoff,
    GenerationRequest,
    PromptProfile,
    QueryRequest,
    QueryResponse,
)
from app.service import GenerationService

LOGGER = logging.getLogger("securequery.audit")


class QueryService:
    """Orchestrate generation and the independent SQL gateway.

    This service never imports or opens a database connection. It hands the
    candidate SQL to the gateway and reports the decision unchanged.
    """

    def __init__(self, generations: GenerationService, gateway: SqlGateway) -> None:
        self.generations = generations
        self.gateway = gateway

    @property
    def executor(self) -> str:
        return getattr(self.gateway, "executor", "gateway")

    @property
    def gateway_connected(self) -> bool:
        return self.executor == "gateway" and not isinstance(
            self.gateway, NotConnectedGateway
        )

    async def query(self, request_id: str, request: QueryRequest) -> QueryResponse:
        generation = await self.generations.generate(
            request_id,
            GenerationRequest(
                question=request.question,
                principal_id=request.principal_id,
                prompt_profile=PromptProfile.HARDENED,
                context_profile=request.context_profile,
            ),
        )
        if generation.status != "generated" or not generation.candidate_sql:
            response = QueryResponse(
                request_id=request_id,
                status=generation.status,
                generation=generation,
                gateway=None,
                result=None,
                executor=self.executor,
            )
            self._audit(request_id, response, sql_digest=None)
            return response

        handoff = GatewayHandoff(
            request_id=request_id,
            principal_id=request.principal_id,
            candidate_sql=generation.candidate_sql,
            schema_version=generation.provenance.schema_version,
        )
        sql_digest = hashlib.sha256(generation.candidate_sql.encode("utf-8")).hexdigest()
        try:
            outcome = await self.gateway.inspect_and_execute(handoff)
            if outcome.error is not None:
                if outcome.result is not None:
                    raise GatewayUnavailable("gateway returned both error and result")
            elif outcome.decision.decision != "BLOCK" and outcome.result is None:
                raise GatewayUnavailable("gateway returned no result")
            elif outcome.decision.decision == "BLOCK" and outcome.result is not None:
                raise GatewayUnavailable("gateway returned a result for a blocked query")
        except GatewayUnavailable:
            response = QueryResponse(
                request_id=request_id,
                status="unavailable",
                generation=generation,
                gateway=None,
                result=None,
                executor=self.executor,
            )
            self._audit(request_id, response, sql_digest=sql_digest)
            return response

        if outcome.error is not None:
            response = QueryResponse(
                request_id=request_id,
                status="error",
                generation=generation,
                gateway=outcome.decision,
                result=None,
                error=outcome.error,
                db_role=outcome.db_role,
                executor=self.executor,
            )
        else:
            response = QueryResponse(
                request_id=request_id,
                status="blocked" if outcome.decision.decision == "BLOCK" else "executed",
                generation=generation,
                gateway=outcome.decision,
                result=outcome.result,
                db_role=outcome.db_role,
                executor=self.executor,
            )
        self._audit(request_id, response, sql_digest=sql_digest)
        return response

    @staticmethod
    def _audit(request_id: str, response: QueryResponse, sql_digest: str | None) -> None:
        LOGGER.info(
            json.dumps(
                {
                    "event": "query_completed",
                    "request_id": request_id,
                    "status": response.status,
                    "generation_status": response.generation.status,
                    "gateway_decision": response.gateway.decision if response.gateway else None,
                    "reason_code": response.gateway.reason_code if response.gateway else None,
                    "row_count": response.result.row_count if response.result else None,
                    "executor": response.executor,
                    "db_role": response.db_role,
                    "error_code": response.error.code if response.error else None,
                    "sqlstate": response.error.sqlstate if response.error else None,
                    "sql_digest": sql_digest,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
