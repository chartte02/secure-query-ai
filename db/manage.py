"""Initialize/reset only the three owned lab databases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from db.seed import COLUMNS, SEED_VERSION, TABLES, canonical_digest, seed_rows
from db.settings import ROOT, TARGETS, Profile, Settings

SCHEMA_VERSION = 1
GROUPS = (
    "sq_owner",
    "sq_student_reader",
    "sq_teacher_reader",
    "sq_feedback_writer",
    "sq_view_owner",
)


def actor_roles() -> dict[str, tuple[str, str | None, str | None, str]]:
    """role -> actor_id, student_id, teacher_id, group; trusted server-side map."""
    roles = {}
    for number in range(1, 21):
        student = f"S{number:02}"
        actor = f"student_s{number:02}"
        roles[f"sq_{actor}"] = (actor, student, None, "sq_student_reader")
        roles[f"sq_feedback_s{number:02}"] = (actor, student, None, "sq_feedback_writer")
    for number in range(1, 4):
        teacher = f"T{number:02}"
        roles[f"sq_teacher_t{number:02}"] = (
            f"teacher_t{number:02}",
            None,
            teacher,
            "sq_teacher_reader",
        )
    return roles


def assert_target(conn: psycopg.Connection, profile: Profile, settings: Settings) -> None:
    observed = conn.execute("SELECT current_database() AS name").fetchone()
    if observed is None or observed["name"] != TARGETS[profile][1]:
        raise RuntimeError("Refusing operation on an unexpected database.")
    marker = conn.execute(
        "SELECT installation_id, profile, schema_version FROM lab_meta.installation"
    ).fetchone()
    if marker is None or (
        str(marker["installation_id"]) != settings.installation_id
        or marker["profile"] != profile
        or marker["schema_version"] != SCHEMA_VERSION
    ):
        raise RuntimeError("Refusing operation: lab ownership marker does not match.")


def _create_roles(conn: psycopg.Connection, settings: Settings, profile: Profile) -> None:
    logins = {"sq_context_reader", "sq_audit_writer"}
    if profile == "hardened":
        logins.update(actor_roles())
    elif profile == "baseline":
        logins.add("sq_lab_reader")
    else:
        logins.add("sq_lab_writer")
    for role in (*GROUPS, *sorted(logins)):
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        login = sql.SQL("LOGIN") if role in logins else sql.SQL("NOLOGIN")
        conn.execute(
            sql.SQL(
                "ALTER ROLE {} {} INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(role), login)
        )
        if role in logins:
            conn.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role),
                    sql.Literal(settings.role_password(role)),
                )
            )
            readonly = role not in {"sq_audit_writer", "sq_lab_writer"} and not role.startswith(
                "sq_feedback_"
            )
            for setting, value in (
                ("default_transaction_read_only", "on" if readonly else "off"),
                ("statement_timeout", "5000"),
                ("lock_timeout", "1000"),
                ("idle_in_transaction_session_timeout", "15000"),
            ):
                conn.execute(
                    sql.SQL("ALTER ROLE {} SET {} TO {}").format(
                        sql.Identifier(role),
                        sql.Identifier(setting),
                        sql.Literal(value),
                    )
                )
            conn.execute(
                sql.SQL("ALTER ROLE {} SET search_path TO pg_catalog, academic, api").format(
                    sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(TARGETS[profile][1]),
                    sql.Identifier(role),
                )
            )
    if profile == "hardened":
        for role, (_, _, _, group) in actor_roles().items():
            conn.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(group),
                    sql.Identifier(role),
                )
            )


def _load_seed(conn: psycopg.Connection, fixture: str) -> None:
    for table, rows in seed_rows(fixture).items():
        statement = sql.SQL("INSERT INTO academic.{} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, COLUMNS[table])),
            sql.SQL(", ").join(sql.Placeholder() for _ in COLUMNS[table]),
        )
        with conn.cursor() as cursor:
            cursor.executemany(statement, rows)
    for role, (actor, student, teacher, _) in actor_roles().items():
        conn.execute(
            "INSERT INTO private_auth.actor_map VALUES (%s, %s, %s, %s, %s)",
            (role, actor, "student" if student else "teacher", student, teacher),
        )


def snapshot(conn: psycopg.Connection) -> dict[str, Any]:
    tables = {}
    for table in TABLES:
        records = conn.execute(
            sql.SQL("SELECT {} FROM academic.{}").format(
                sql.SQL(", ").join(map(sql.Identifier, COLUMNS[table])),
                sql.Identifier(table),
            )
        ).fetchall()
        records.sort(key=lambda record: json.dumps(record, sort_keys=True, default=str))
        tables[table] = {"rows": len(records), "sha256": canonical_digest(records)}
    return {"seed_version": SEED_VERSION, "tables": tables, "sha256": canonical_digest(tables)}


def initialize(
    profile: Profile = "hardened", *, fixture: str = "clean", reset: bool = False
) -> dict[str, Any]:
    seed_rows(fixture)  # Validate before connecting or changing anything.
    settings = Settings.load()
    with settings.connect(profile) as conn:
        exists = conn.execute("SELECT to_regclass('lab_meta.installation') AS name").fetchone()
        if exists and exists["name"]:
            assert_target(conn, profile, settings)
            if not reset:
                current = conn.execute("SELECT fixture FROM lab_meta.installation").fetchone()
                return {
                    "profile": profile,
                    "fixture": current["fixture"],
                    "status": "already_initialized",
                    **snapshot(conn),
                }
            for schema in ("api", "audit", "private_auth", "academic"):
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        else:
            if reset:
                raise RuntimeError("Refusing reset: target has no matching lab ownership marker.")
            user_objects = conn.execute(
                "SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%%'"
            ).fetchone()
            if user_objects and user_objects["n"]:
                raise RuntimeError("Refusing initial setup in a nonempty unmarked database.")
            conn.execute("CREATE SCHEMA lab_meta")
            conn.execute(
                "CREATE TABLE lab_meta.installation (installation_id uuid NOT NULL, "
                "profile text NOT NULL, schema_version integer NOT NULL, fixture text NOT NULL)"
            )
            conn.execute(
                "INSERT INTO lab_meta.installation VALUES (%s, %s, %s, %s)",
                (settings.installation_id, profile, SCHEMA_VERSION, fixture),
            )
        conn.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(TARGETS[profile][1]),
            )
        )
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        _create_roles(conn, settings, profile)
        migrations = Path(__file__).parent / "migrations"
        for path in sorted(migrations.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
        _load_seed(conn, fixture)
        conn.execute(
            (Path(__file__).parent / "profiles" / f"{profile}.sql").read_text(encoding="utf-8")
        )
        conn.execute("UPDATE lab_meta.installation SET fixture = %s", (fixture,))
        return {
            "profile": profile,
            "fixture": fixture,
            "status": "reset" if reset else "created",
            **snapshot(conn),
        }


def write_seed_manifest(report: dict[str, Any]) -> None:
    target = ROOT / "db" / "seed" / "manifest.json"
    target.parent.mkdir(exist_ok=True)
    contents = {key: report[key] for key in ("seed_version", "tables", "sha256")}
    target.write_text(json.dumps(contents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
