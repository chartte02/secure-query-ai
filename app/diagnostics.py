from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.models import SqlDiagnostics


def diagnose_sql(sql: str | None) -> SqlDiagnostics:
    if not sql:
        return SqlDiagnostics(
            parseable=False,
            statement_count=0,
            statement_types=[],
            tables=[],
            columns=[],
            warnings=["no_candidate_sql"],
        )

    try:
        # SQLGlot's unsupported-command warning otherwise includes a SQL excerpt.
        # Keep parser diagnostics, but remove query text from third-party logs.
        statements = [
            statement
            for statement in sqlglot.parse(sql, read="postgres", error_message_context=0)
            if statement
        ]
    except (ParseError, RecursionError):
        return SqlDiagnostics(
            parseable=False,
            statement_count=0,
            statement_types=[],
            tables=[],
            columns=[],
            warnings=["postgres_parse_error"],
        )

    if not statements:
        return diagnose_sql(None)
    statement_types = [statement.key.upper() for statement in statements]
    # SQLGlot also accepts expressions such as a bare identifier. Those are not
    # SQL statements and must not be mistaken for a generated query.
    statement_classes = (exp.Query, exp.DML, exp.DDL, exp.Command, exp.Drop, exp.Alter)
    if not all(isinstance(statement, statement_classes) for statement in statements):
        return SqlDiagnostics(
            parseable=False, statement_count=len(statements),
            statement_types=statement_types, tables=[], columns=[],
            warnings=["not_sql_statement"],
        )
    tables = sorted(
        {
            table.name
            for statement in statements
            for table in statement.find_all(exp.Table)
            if table.name
        }
    )
    columns = sorted(
        {
            column.name
            for statement in statements
            for column in statement.find_all(exp.Column)
            if column.name
        }
    )
    warnings: list[str] = []
    if len(statements) != 1:
        warnings.append("multiple_statements")
    if any(isinstance(statement, exp.Command) for statement in statements):
        warnings.append("unsupported_statement_syntax")
    modifying_nodes = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Into,
    )
    if any(not isinstance(statement, exp.Query) for statement in statements) or any(
        isinstance(node, modifying_nodes) for statement in statements for node in statement.walk()
    ):
        warnings.append("non_read_only_candidate")
    return SqlDiagnostics(
        parseable=True,
        statement_count=len(statements),
        statement_types=statement_types,
        tables=tables,
        columns=columns,
        warnings=warnings,
    )

