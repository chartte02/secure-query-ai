"""Independent parser and authorization policy for model-generated SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.catalog import SCHEMA_VERSION
from app.models import GatewayHandoff

Decision = Literal["ALLOW", "MASK", "BLOCK"]

_POLICY_VERSION = "campus_policy_v1"
_MASKED_VIEW = "api.my_contact"
_SENSITIVE_COLUMNS = {
    "phone",
    "national_id",
    "grader_note",
}
_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "academic.students": frozenset({"student_id", "display_name", "department"}),
    "academic.teachers": frozenset({"teacher_id", "display_name", "department"}),
    "academic.courses": frozenset(
        {"course_id", "course_name", "description", "credits"}
    ),
    "academic.course_offerings": frozenset(
        {"offering_id", "course_id", "teacher_id", "term"}
    ),
    "academic.enrollments": frozenset({"student_id", "offering_id", "enrolled_at"}),
    "academic.grades": frozenset({"student_id", "offering_id", "score"}),
    "academic.course_feedback": frozenset(
        {"feedback_id", "offering_id", "content", "visibility", "created_at"}
    ),
    _MASKED_VIEW: frozenset({"student_id", "phone_masked"}),
}
_DENIED_TABLES = frozenset({"private_auth.actor_map", "audit.events"})


@dataclass(frozen=True)
class ParsedSql:
    normalized_sql: str
    statement: exp.Expression
    tables: tuple[str, ...]
    columns: tuple[str, ...]


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reason_code: str
    tables: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    mask_columns: tuple[str, ...] = ()
    normalized_sql: str | None = None
    policy_version: str = _POLICY_VERSION


def parse_candidate_sql(sql: str) -> ParsedSql:
    """Parse exactly one PostgreSQL statement and expose normalized metadata."""

    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1:
        raise ValueError("MULTIPLE_STATEMENTS")
    statement = statements[0]
    tables = _table_names(statement)
    columns = _column_names(statement)
    return ParsedSql(
        normalized_sql=statement.sql(dialect="postgres"),
        statement=statement,
        tables=tables,
        columns=columns,
    )


def authorize_candidate(handoff: GatewayHandoff) -> PolicyDecision:
    """Return a decision without database I/O or trust in model refusal."""

    if handoff.schema_version != SCHEMA_VERSION:
        return _blocked("SCHEMA_VERSION_UNSUPPORTED")
    try:
        parsed = parse_candidate_sql(handoff.candidate_sql)
    except ValueError as exc:
        reason = str(exc)
        if reason == "MULTIPLE_STATEMENTS":
            return _blocked(reason)
        return _blocked("SQL_PARSE_ERROR")
    except ParseError:
        return _blocked("SQL_PARSE_ERROR")

    statement = parsed.statement
    if not isinstance(statement, exp.Query) or isinstance(
        statement, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Alter, exp.Drop)
    ):
        return _blocked("NON_READ_ONLY", parsed)
    if any(
        isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Alter, exp.Drop))
        for node in statement.walk()
    ):
        return _blocked("NON_READ_ONLY", parsed)
    if statement.find(exp.Into):
        return _blocked("NON_READ_ONLY", parsed)

    if any(table in _DENIED_TABLES for table in parsed.tables):
        return _blocked("TABLE_DENIED", parsed)
    if any(table not in _TABLE_COLUMNS for table in parsed.tables):
        return _blocked("TABLE_DENIED", parsed)
    if any(isinstance(node, exp.Star) for node in statement.walk()):
        return _blocked("SELECT_STAR_DENIED", parsed)

    aliases = _table_aliases(statement)
    for column in statement.find_all(exp.Column):
        name = column.name.lower()
        if name in _SENSITIVE_COLUMNS:
            return _blocked("COLUMN_DENIED", parsed)
        if not _column_is_known(column, parsed.tables, aliases):
            return _blocked("COLUMN_DENIED", parsed)

    if _MASKED_VIEW in parsed.tables:
        return PolicyDecision(
            decision="MASK",
            reason_code="MASKED_VIEW",
            tables=parsed.tables,
            columns=parsed.columns,
            mask_columns=("phone_masked",),
            normalized_sql=parsed.normalized_sql,
        )
    return PolicyDecision(
        decision="ALLOW",
        reason_code="POLICY_ALLOW",
        tables=parsed.tables,
        columns=parsed.columns,
        normalized_sql=parsed.normalized_sql,
    )


def _blocked(reason_code: str, parsed: ParsedSql | None = None) -> PolicyDecision:
    return PolicyDecision(
        decision="BLOCK",
        reason_code=reason_code,
        tables=parsed.tables if parsed else (),
        columns=parsed.columns if parsed else (),
        normalized_sql=parsed.normalized_sql if parsed else None,
    )


def _table_names(statement: exp.Expression) -> tuple[str, ...]:
    names: list[str] = []
    for table in statement.find_all(exp.Table):
        name = ".".join(part for part in (table.db, table.name) if part)
        name = name.lower()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _column_names(statement: exp.Expression) -> tuple[str, ...]:
    names: list[str] = []
    for column in statement.find_all(exp.Column):
        name = column.name.lower()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _table_aliases(statement: exp.Expression) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        full_name = ".".join(part for part in (table.db, table.name) if part).lower()
        aliases[table.alias_or_name.lower()] = full_name
        aliases[table.name.lower()] = full_name
    return aliases


def _column_is_known(
    column: exp.Column, tables: tuple[str, ...], aliases: dict[str, str]
) -> bool:
    qualifier = column.table.lower() if column.table else None
    candidate_tables = (aliases[qualifier],) if qualifier in aliases else tables
    return any(column.name.lower() in _TABLE_COLUMNS.get(table, ()) for table in candidate_tables)


