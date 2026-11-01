"""Lab-only direct executor for observing member B's database controls.

This is NOT member C's policy gateway. It performs no SQL policy checks; the
database role still enforces read-only transactions, column grants, RLS, and
statement timeouts. It is enabled only when both
``SECUREQUERY_DEMO_MODE=true`` and ``SECUREQUERY_LAB_GATEWAY=true``.
"""

from __future__ import annotations

import asyncio
import time as clock
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from app.gateway import GatewayOutcome
from app.models import (
    GatewayHandoff,
    QueryColumn,
    QueryError,
    QueryGatewayDecision,
    QueryResult,
)

MAX_ROWS = 100

_TYPE_NAMES = {
    16: "bool",
    20: "int8",
    21: "int2",
    23: "int4",
    25: "text",
    1082: "date",
    1043: "varchar",
    1184: "timestamptz",
    1700: "numeric",
    2950: "uuid",
}

_SQLSTATE_CODES = {
    "42501": "database_permission_denied",
    "25006": "database_read_only",
    "57014": "database_timeout",
    "42P01": "database_undefined_table",
    "42703": "database_undefined_column",
    "42601": "database_syntax_error",
}


@dataclass(frozen=True)
class LabScenario:
    label: str
    principal_id: str
    sql: str
    expectation: str


# Fixed SQL replay only. The model is never invoked for these scenarios.
LAB_SCENARIOS: dict[str, LabScenario] = {
    "own_grades": LabScenario(
        label="正常：本人成绩",
        principal_id="student_s01",
        sql=(
            "SELECT c.course_name, g.score FROM academic.grades AS g "
            "JOIN academic.course_offerings AS o ON o.offering_id = g.offering_id "
            "JOIN academic.courses AS c ON c.course_id = o.course_id "
            "WHERE g.student_id = 'S01' ORDER BY c.course_name"
        ),
        expectation="3 rows: O01 52, O03 65, O05 78",
    ),
    "rls_cross_student": LabScenario(
        label="RLS：跨学生读取",
        principal_id="student_s01",
        sql=(
            "SELECT student_id, offering_id, score FROM academic.grades "
            "WHERE student_id = 'S02'"
        ),
        expectation="executed with 0 rows; RLS filters silently, no error",
    ),
    "column_denied": LabScenario(
        label="列权限：读取 national_id",
        principal_id="student_s01",
        sql="SELECT national_id FROM academic.students",
        expectation="error SQLSTATE 42501 database_permission_denied",
    ),
    "write_denied": LabScenario(
        label="只读：删除成绩",
        principal_id="student_s01",
        sql="DELETE FROM academic.grades WHERE score < 60",
        expectation="error SQLSTATE 25006 read-only or 42501",
    ),
    "row_limit": LabScenario(
        label="限行：150 行截断为 100",
        principal_id="student_s01",
        sql="SELECT generate_series(1, 150) AS n",
        expectation="executed with 100 rows and truncated=true",
    ),
}


def _decision() -> QueryGatewayDecision:
    return QueryGatewayDecision(
        decision="ALLOW",
        reason_code="lab_direct_no_policy",
        audit_id=str(uuid4()),
        policy_version="lab_direct_v1",
    )


def _json_value(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return str(value)


class LocalLabGateway:
    """Temporary executor used only for local demonstrations of B's controls."""

    executor = "lab_direct"

    async def inspect_and_execute(self, handoff: GatewayHandoff) -> GatewayOutcome:
        return await asyncio.to_thread(self._execute, handoff)

    def _execute(self, handoff: GatewayHandoff) -> GatewayOutcome:
        started = clock.perf_counter()
        try:
            import psycopg

            from db.client import query_connection
        except ImportError:
            return GatewayOutcome(
                decision=_decision(),
                result=None,
                error=QueryError(
                    code="database_driver_unavailable",
                    stage="database",
                    message="The database driver is not installed.",
                ),
            )

        db_role: str | None = None
        try:
            with query_connection(handoff.principal_id) as conn:
                db_role = conn.execute("SELECT session_user AS role").fetchone()["role"]
                with conn.cursor() as cursor:
                    cursor.execute(handoff.candidate_sql)
                    if cursor.description is None:
                        return GatewayOutcome(
                            decision=_decision(),
                            result=None,
                            error=QueryError(
                                code="database_no_result_set",
                                stage="database",
                                message="The statement did not return a result set.",
                            ),
                            db_role=db_role,
                        )
                    column_names = [column.name for column in cursor.description]
                    columns = [
                        QueryColumn(
                            name=column.name,
                            type=_TYPE_NAMES.get(column.type_code, str(column.type_code)),
                        )
                        for column in cursor.description
                    ]
                    fetched = cursor.fetchmany(MAX_ROWS + 1)
        except psycopg.Error as exc:
            sqlstate = exc.sqlstate
            return GatewayOutcome(
                decision=_decision(),
                result=None,
                error=QueryError(
                    code=_SQLSTATE_CODES.get(sqlstate or "", "database_error"),
                    stage="database",
                    sqlstate=sqlstate if sqlstate and len(sqlstate) == 5 else None,
                    message=(exc.diag.message_primary or type(exc).__name__)[:300],
                ),
                db_role=db_role,
            )
        except ValueError as exc:
            return GatewayOutcome(
                decision=_decision(),
                result=None,
                error=QueryError(
                    code="invalid_principal",
                    stage="gateway",
                    message=str(exc)[:300],
                ),
            )

        truncated = len(fetched) > MAX_ROWS
        rows = [
            [_json_value(row[name]) for name in column_names]
            for row in fetched[:MAX_ROWS]
        ]
        return GatewayOutcome(
            decision=_decision(),
            result=QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                masked_columns=[],
                execution_ms=round((clock.perf_counter() - started) * 1_000),
            ),
            db_role=db_role,
        )
