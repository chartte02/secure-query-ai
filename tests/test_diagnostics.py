from __future__ import annotations

from app.diagnostics import diagnose_sql
import pytest


def test_read_only_select_is_parsed_without_policy_warning() -> None:
    result = diagnose_sql("SELECT g.score FROM grades AS g WHERE g.student_id = 'S001'")
    assert result.parseable is True
    assert result.statement_types == ["SELECT"]
    assert result.tables == ["grades"]
    assert result.columns == ["score", "student_id"]
    assert result.warnings == []


def test_dangerous_statement_is_diagnostic_not_authorization() -> None:
    result = diagnose_sql("DROP TABLE students")
    assert result.parseable is True
    assert result.statement_types == ["DROP"]
    assert result.warnings == ["non_read_only_candidate"]


def test_multiple_statements_are_visible() -> None:
    result = diagnose_sql("SELECT * FROM grades; DELETE FROM grades")
    assert result.statement_count == 2
    assert "multiple_statements" in result.warnings
    assert "non_read_only_candidate" in result.warnings


def test_invalid_sql_is_reported_without_echoing_parser_details() -> None:
    result = diagnose_sql("SELECT FROM (")
    assert result.parseable is False
    assert result.warnings == ["postgres_parse_error"]


@pytest.mark.parametrize("sql", [";", "-- only a comment", "/* only a comment */"])
def test_empty_ast_does_not_crash(sql: str) -> None:
    result = diagnose_sql(sql)
    assert result.parseable is False
    assert result.statement_count == 0


def test_modifying_cte_is_reported_even_with_select_root() -> None:
    result = diagnose_sql("WITH deleted AS (DELETE FROM grades RETURNING *) SELECT * FROM deleted")
    assert "non_read_only_candidate" in result.warnings


def test_bare_text_is_not_treated_as_a_query() -> None:
    result = diagnose_sql("nonsense")
    assert result.parseable is False


def test_parser_fallback_does_not_log_candidate_sql(caplog) -> None:
    sensitive_marker = "UNIQUE_SECRET_13800138000"
    diagnose_sql(f"EXECUTE {sensitive_marker}")
    assert sensitive_marker not in caplog.text

