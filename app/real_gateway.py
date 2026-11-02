"""Formal C gateway: parse, authorize, execute, and safely serialize results."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as datetime_time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg

from app.gateway import GatewayOutcome
from app.models import (
    GatewayHandoff,
    QueryColumn,
    QueryError,
    QueryGatewayDecision,
    QueryResult,
)
from app.sql_policy import PolicyDecision, authorize_candidate

MAX_ROWS = 100
_TYPE_NAMES = {
    16: "bool",
    20: "int8",
    21: "int2",
    23: "int4",
    25: "text",
    1043: "varchar",
    1082: "date",
    1184: "timestamptz",
    1700: "numeric",
    2950: "uuid",
}
_SQLSTATE_CODES = {
    "42501": "database_permission_denied",
    "25006": "database_read_only",
    "57014": "database_timeout",
}


class RealGateway:
    """Only formal executor for model-produced SQL."""

    executor = "gateway"

    def __init__(
        self,
        connection_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._connection_factory = connection_factory or self._default_connection_factory

    async def inspect_and_execute(self, handoff: GatewayHandoff) -> GatewayOutcome:
        return await asyncio.to_thread(self._execute, handoff)

    def _execute(self, handoff: GatewayHandoff) -> GatewayOutcome:
        started = time.perf_counter()
        policy = authorize_candidate(handoff)
        decision = _gateway_decision(policy)
        if policy.decision == "BLOCK":
            return GatewayOutcome(decision=decision, result=None)

        db_role: str | None = None
        try:
            from db.client import resolve_actor

            db_role = resolve_actor(handoff.principal_id).db_role
            with self._connection_factory(handoff.principal_id) as connection:
                connection.execute("SET TRANSACTION READ ONLY")
                with connection.cursor() as cursor:
                    cursor.execute(policy.normalized_sql)
                    if cursor.description is None:
                        return GatewayOutcome(
                            decision=decision,
                            result=None,
                            error=QueryError(
                                code="database_no_result_set",
                                stage="database",
                                message="The statement did not return a result set.",
                            ),
                            db_role=db_role,
                        )
                    columns = [
                        QueryColumn(
                            name=column.name,
                            type=_TYPE_NAMES.get(column.type_code, str(column.type_code)),
                        )
                        for column in cursor.description
                    ]
                    names = [column.name for column in cursor.description]
                    fetched = cursor.fetchmany(MAX_ROWS + 1)
        except psycopg.Error as exc:
            sqlstate = exc.sqlstate
            return GatewayOutcome(
                decision=decision,
                result=None,
                error=QueryError(
                    code=_SQLSTATE_CODES.get(sqlstate or "", "database_error"),
                    stage="database",
                    sqlstate=sqlstate if sqlstate and len(sqlstate) == 5 else None,
                    message=_safe_db_message(exc),
                ),
                db_role=db_role,
            )
        except ValueError as exc:
            return GatewayOutcome(
                decision=decision,
                result=None,
                error=QueryError(
                    code="invalid_principal",
                    stage="gateway",
                    message=str(exc)[:300],
                ),
                db_role=db_role,
            )

        truncated = len(fetched) > MAX_ROWS
        rows = [
            [
                _json_value(row[name] if isinstance(row, dict) else row[index])
                for index, name in enumerate(names)
            ]
            for row in fetched[:MAX_ROWS]
        ]
        return GatewayOutcome(
            decision=decision,
            result=QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                masked_columns=list(policy.mask_columns),
                execution_ms=round((time.perf_counter() - started) * 1_000),
            ),
            db_role=db_role,
        )

    @staticmethod
    def _default_connection_factory(principal_id: str) -> Any:
        from db.client import query_connection

        return query_connection(principal_id, profile="hardened")


def _gateway_decision(policy: PolicyDecision) -> QueryGatewayDecision:
    return QueryGatewayDecision(
        decision=policy.decision,
        reason_code=policy.reason_code,
        audit_id=str(uuid4()),
        policy_version=policy.policy_version,
    )


def _safe_db_message(error: psycopg.Error) -> str:
    message = getattr(getattr(error, "diag", None), "message_primary", None)
    return str(message or "Database execution failed.")[:300]


def _json_value(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, datetime_time, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return str(value)
