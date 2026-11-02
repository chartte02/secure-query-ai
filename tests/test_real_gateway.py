from __future__ import annotations

from types import SimpleNamespace

import psycopg

from app.models import GatewayHandoff
from app.real_gateway import MAX_ROWS, RealGateway

SAFE_SQL = "SELECT student_id, offering_id, score FROM academic.grades WHERE student_id = 'S01'"


def handoff(sql: str = SAFE_SQL) -> GatewayHandoff:
    return GatewayHandoff(
        request_id="req-gateway",
        principal_id="student_s01",
        candidate_sql=sql,
        schema_version="campus_lab_v1",
    )


class FakeCursor:
    description = [
        SimpleNamespace(name="student_id", type_code=25),
        SimpleNamespace(name="score", type_code=1700),
    ]

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def fetchmany(self, size: int) -> list[dict[str, object]]:
        assert size == MAX_ROWS + 1
        return self.rows[:size]

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeCursor(rows)
        self.commits = 0
        self.read_only_set = False

    def execute(self, sql: str) -> None:
        if sql == "SET TRANSACTION READ ONLY":
            self.read_only_set = True

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_allowed_query_uses_normalized_sql_and_returns_rows() -> None:
    connection = FakeConnection([{"student_id": "S01", "score": 52.0}])
    gateway = RealGateway(connection_factory=lambda _: connection)

    outcome = gateway._execute(handoff())

    assert outcome.decision.decision == "ALLOW"
    assert outcome.decision.reason_code == "POLICY_ALLOW"
    assert outcome.result is not None
    assert outcome.result.rows == [["S01", 52.0]]
    assert outcome.result.row_count == 1
    assert connection.read_only_set is True
    assert connection.cursor_instance.executed == [
        "SELECT student_id, offering_id, score FROM academic.grades WHERE student_id = 'S01'"
    ]


def test_blocked_query_never_opens_a_database_connection() -> None:
    opened = False

    def connection_factory(_: str) -> FakeConnection:
        nonlocal opened
        opened = True
        return FakeConnection([])

    gateway = RealGateway(connection_factory=connection_factory)
    outcome = gateway._execute(handoff("DROP TABLE academic.grades"))

    assert outcome.decision.decision == "BLOCK"
    assert outcome.result is None
    assert opened is False


def test_result_is_truncated_at_max_rows() -> None:
    rows = [{"student_id": "S01", "score": index} for index in range(MAX_ROWS + 1)]
    connection = FakeConnection(rows)
    gateway = RealGateway(connection_factory=lambda _: connection)

    outcome = gateway._execute(handoff())

    assert outcome.result is not None
    assert outcome.result.row_count == MAX_ROWS
    assert outcome.result.truncated is True


def test_database_permission_error_is_safe_and_classified() -> None:
    class PermissionConnection(FakeConnection):
        def cursor(self) -> FakeCursor:
            raise FakeDatabaseError("42501")

    gateway = RealGateway(connection_factory=lambda _: PermissionConnection([]))
    outcome = gateway._execute(handoff())

    assert outcome.decision.decision == "ALLOW"
    assert outcome.error is not None
    assert outcome.error.code == "database_permission_denied"
    assert outcome.error.sqlstate == "42501"
    assert "SELECT" not in outcome.error.message


class FakeDatabaseError(psycopg.Error):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("database failure")
        self.sqlstate = sqlstate
