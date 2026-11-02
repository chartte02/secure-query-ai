from __future__ import annotations

import pytest

from app.models import GatewayHandoff
from app.sql_policy import authorize_candidate, parse_candidate_sql


def handoff(sql: str, principal_id: str = "student_s01") -> GatewayHandoff:
    return GatewayHandoff(
        request_id="req-policy",
        principal_id=principal_id,
        candidate_sql=sql,
        schema_version="campus_lab_v1",
    )


def test_allows_single_read_query_with_known_objects() -> None:
    parsed = parse_candidate_sql(
        "SELECT c.course_name, g.score "
        "FROM academic.grades AS g "
        "JOIN academic.course_offerings AS o ON o.offering_id = g.offering_id "
        "JOIN academic.courses AS c ON c.course_id = o.course_id "
        "WHERE g.student_id = 'S01'"
    )

    decision = authorize_candidate(handoff(parsed.normalized_sql))

    assert decision.decision == "ALLOW"
    assert decision.reason_code == "POLICY_ALLOW"
    assert decision.tables == (
        "academic.grades",
        "academic.course_offerings",
        "academic.courses",
    )
    assert decision.normalized_sql


@pytest.mark.parametrize(
    ("sql", "reason_code"),
    [
        ("SELECT 1; SELECT 2", "MULTIPLE_STATEMENTS"),
        ("DROP TABLE academic.grades", "NON_READ_ONLY"),
        ("DELETE FROM academic.grades WHERE score < 60", "NON_READ_ONLY"),
        ("UPDATE academic.grades SET score = 100", "NON_READ_ONLY"),
        ("CREATE TABLE academic.tmp (id int)", "NON_READ_ONLY"),
        (
            "WITH changed AS (DELETE FROM academic.grades RETURNING student_id) "
            "SELECT * FROM changed",
            "NON_READ_ONLY",
        ),
    ],
)
def test_blocks_non_read_only_or_multi_statement_sql(sql: str, reason_code: str) -> None:
    decision = authorize_candidate(handoff(sql))

    assert decision.decision == "BLOCK"
    assert decision.reason_code == reason_code


def test_comments_do_not_hide_a_second_statement() -> None:
    decision = authorize_candidate(handoff("SELECT 1 /* safe */; -- second\nSELECT 2"))

    assert decision.decision == "BLOCK"
    assert decision.reason_code == "MULTIPLE_STATEMENTS"


def test_blocks_invalid_sql_without_database_access() -> None:
    decision = authorize_candidate(handoff("SELECT FROM"))

    assert decision.decision == "BLOCK"
    assert decision.reason_code == "SQL_PARSE_ERROR"
    assert decision.normalized_sql is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT national_id FROM academic.students",
        "SELECT phone FROM academic.students",
        "SELECT grader_note FROM academic.grades",
        "SELECT * FROM academic.students",
    ],
)
def test_blocks_sensitive_or_ambiguous_columns(sql: str) -> None:
    decision = authorize_candidate(handoff(sql))

    assert decision.decision == "BLOCK"
    assert decision.reason_code in {"COLUMN_DENIED", "SELECT_STAR_DENIED"}


def test_allows_masked_contact_view_and_marks_mask_column() -> None:
    decision = authorize_candidate(
        handoff("SELECT student_id, phone_masked FROM api.my_contact")
    )

    assert decision.decision == "MASK"
    assert decision.reason_code == "MASKED_VIEW"
    assert decision.mask_columns == ("phone_masked",)


def test_blocks_private_objects_and_unknown_columns() -> None:
    private_decision = authorize_candidate(handoff("SELECT * FROM private_auth.actor_map"))
    unknown_decision = authorize_candidate(
        handoff("SELECT academic.students.secret FROM academic.students")
    )

    assert private_decision.reason_code == "TABLE_DENIED"
    assert unknown_decision.reason_code == "COLUMN_DENIED"


def test_leaves_row_scope_to_postgres_rls() -> None:
    decision = authorize_candidate(
        handoff(
            "SELECT student_id, offering_id, score "
            "FROM academic.grades WHERE student_id = 'S02'"
        )
    )

    assert decision.decision == "ALLOW"
