from __future__ import annotations

from uuid import UUID

from app.audit_writer import DatabaseAuditWriter


class FakeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.calls.append((statement, params))


class FakeConnection:
    def __init__(self) -> None:
        self.cursor = FakeCursor()

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.cursor.execute(statement, params)

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_audit_writer_inserts_digest_and_decision_without_raw_sql() -> None:
    connection = FakeConnection()
    writer = DatabaseAuditWriter(connection_factory=lambda: connection)

    event_id = writer._append_sync(
        request_id="2f7d8e40-f8e7-4aab-9b8b-9ebf1d8a46b7",
        actor_id="student_s01",
        db_role="sq_student_s01",
        event_type="query_completed",
        decision="ALLOW",
        reason_code="POLICY_ALLOW",
        sql_digest="a" * 64,
    )

    assert UUID(event_id)
    assert len(connection.cursor.calls) == 1
    statement, params = connection.cursor.calls[0]
    assert "INSERT INTO audit.events" in statement
    assert "SELECT" not in statement
    assert "DROP" not in statement
    assert params[3:8] == (
        "sq_student_s01",
        "query_completed",
        "ALLOW",
        "POLICY_ALLOW",
        "a" * 64,
    )
