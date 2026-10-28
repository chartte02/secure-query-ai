from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from db.client import ContextProvider, query_connection, submit_feedback
from db.manage import actor_roles
from db.seed import seed_rows
from db.settings import Settings

pytestmark = pytest.mark.database


def test_search_path_resolves_public_course_catalog_without_writable_schemas(
    settings: Settings,
) -> None:
    with query_connection("student_s01") as conn:
        assert conn.execute("SELECT count(*) AS n FROM courses").fetchone()["n"] == 6
        assert conn.execute("SHOW search_path").fetchone()["search_path"] == (
            "pg_catalog, academic, api"
        )


@pytest.mark.parametrize("number", range(1, 21))
def test_student_can_read_self_but_never_another_student(settings: Settings, number: int) -> None:
    student = f"S{number:02}"
    with query_connection(f"student_s{number:02}") as conn:
        rows = conn.execute(
            "SELECT student_id, offering_id, score FROM academic.grades "
            "WHERE student_id = %s OR true",
            (student,),
        ).fetchall()
        assert len(rows) == 3
        assert {row["student_id"] for row in rows} == {student}
        assert (
            conn.execute(
                "SELECT student_id FROM academic.grades WHERE student_id <> %s",
                (student,),
            ).fetchall()
            == []
        )
        assert conn.execute("SELECT count(*) AS n FROM academic.grades").fetchone()["n"] == 3
        own = conn.execute("SELECT student_id FROM academic.students").fetchall()
        assert own == [{"student_id": student}]


@pytest.mark.parametrize("teacher", ("T01", "T02", "T03"))
def test_teacher_can_read_taught_offerings_only(settings: Settings, teacher: str) -> None:
    seed = seed_rows()
    offerings = {r[0] for r in seed["course_offerings"] if r[2] == teacher}
    expected = {(r[0], r[1]) for r in seed["grades"] if r[1] in offerings}
    with query_connection(f"teacher_{teacher.lower()}") as conn:
        rows = conn.execute("SELECT student_id, offering_id FROM academic.grades").fetchall()
        assert {(r["student_id"], r["offering_id"]) for r in rows} == expected
        forbidden = "O02" if teacher == "T01" else "O01"
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM academic.grades WHERE offering_id = %s",
                (forbidden,),
            ).fetchone()["n"]
            == 0
        )
        # RLS must also apply inside a join and an aggregate/subquery.
        result = conn.execute(
            "SELECT count(*) AS n FROM (SELECT g.student_id FROM academic.grades g "
            "JOIN academic.course_offerings o USING (offering_id) "
            "WHERE o.teacher_id <> %s) q",
            (teacher,),
        ).fetchone()
        assert result["n"] == 0


@pytest.mark.parametrize("actor", ("student_s01", "teacher_t01"))
@pytest.mark.parametrize(
    "query",
    (
        "SELECT phone FROM academic.students",
        "SELECT national_id AS harmless FROM academic.students",
        "SELECT 'prefix:' || phone FROM academic.students",
        "SELECT student_id FROM academic.students WHERE national_id = 'ID_TEST_S02'",
        "SELECT student_id FROM academic.students ORDER BY phone",
        "SELECT grader_note FROM academic.grades",
    ),
)
def test_sensitive_fields_are_denied_even_in_expressions(
    settings: Settings, actor: str, query: str
) -> None:
    with query_connection(actor) as conn:
        assert conn.execute("SELECT course_id FROM academic.courses LIMIT 1").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(query)
        conn.rollback()


@pytest.mark.parametrize("number", (1, 2, 11, 20))
def test_masked_view_is_self_only_and_base_phone_stays_forbidden(
    settings: Settings, number: int
) -> None:
    with query_connection(f"student_s{number:02}") as conn:
        assert conn.execute("SELECT * FROM api.my_contact").fetchall() == [
            {"student_id": f"S{number:02}", "phone_masked": "PHONE_TEST_***"}
        ]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT phone FROM academic.students")
        conn.rollback()


@pytest.mark.parametrize(
    "query",
    (
        "UPDATE academic.grades SET score = 100 WHERE student_id = 'S01'",
        "DELETE FROM academic.grades WHERE student_id = 'S01'",
        "INSERT INTO academic.courses VALUES ('XX', 'x', 'x', 1)",
        "DROP TABLE academic.grades",
        "CREATE TABLE public.attacker(x integer)",
        "CREATE TEMP TABLE attacker(x integer)",
    ),
)
def test_query_role_has_no_write_privileges_even_if_readonly_is_turned_off(
    settings: Settings, query: str
) -> None:
    with query_connection("student_s01") as conn:
        conn.read_only = False
        assert conn.execute("SELECT score FROM academic.grades LIMIT 1").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(query)
        conn.rollback()


def test_readonly_transaction_independently_rejects_a_write(settings: Settings) -> None:
    with query_connection("student_s01") as conn:
        assert (
            conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        )
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM academic.grades")
        conn.rollback()


def test_user_context_is_bound_to_login_not_mutable_session_variables(settings: Settings) -> None:
    with query_connection("student_s01") as conn:
        conn.execute("SELECT set_config('app.student_id', 'S02', true)")
        conn.execute("SET ROLE sq_student_reader")
        assert (
            conn.execute("SELECT private_auth.student_id_for_session() AS id").fetchone()["id"]
            == "S01"
        )
        assert {
            r["student_id"] for r in conn.execute("SELECT student_id FROM academic.grades")
        } == {"S01"}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SET ROLE sq_student_s02")
        conn.rollback()


@pytest.mark.parametrize(
    "query",
    (
        "SET ROLE sq_owner",
        "SET SESSION AUTHORIZATION sq_student_s02",
        "SELECT * FROM private_auth.actor_map",
        "SELECT * FROM audit.events",
    ),
)
def test_identity_and_audit_boundaries(settings: Settings, query: str) -> None:
    with query_connection("student_s01") as conn:
        assert conn.execute("SELECT count(*) AS n FROM academic.courses").fetchone()["n"] == 6
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(query)
        conn.rollback()


def test_context_account_sees_public_feedback_but_no_private_or_personal_data(
    settings: Settings,
) -> None:
    provider = ContextProvider()
    assert len(provider.get_course_catalog()) == 6
    feedback = provider.get_public_feedback("O01")
    assert [r["feedback_id"] for r in feedback] == ["FB_ATTACK_01", "FB10", "FB09"]
    assert not any(r["feedback_id"] == "FB12" for r in provider.get_public_feedback("O02"))
    with settings.connect("hardened", "sq_context_reader") as conn:
        assert (
            conn.execute(
                "SELECT feedback_id FROM academic.course_feedback WHERE visibility = 'private'"
            ).fetchall()
            == []
        )
        for query in (
            "SELECT score FROM academic.grades",
            "SELECT phone FROM academic.students",
            "SELECT student_id FROM academic.course_feedback",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(query)
            conn.rollback()
    # A crafted offering identifier is a value, not executable SQL.
    assert provider.get_public_feedback("O01' OR true --") == []


def test_feedback_writer_can_submit_own_enrollment_but_not_other_users(settings: Settings) -> None:
    with settings.connect("hardened", "sq_feedback_s01") as conn:
        insert = "INSERT INTO academic.course_feedback VALUES (%s, %s, %s, %s, %s, %s)"
        now = datetime.now(UTC)
        conn.execute(insert, ("TEST_FEEDBACK", "S01", "O01", "synthetic", "public", now))
        conn.rollback()
        for student, offering in (("S02", "O01"), ("S01", "O02")):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(insert, ("TEST_FORBIDDEN", student, offering, "x", "public", now))
            conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE academic.grades SET score = 100")
        conn.rollback()


def test_parameterized_feedback_interface_accepts_untrusted_text_as_data(
    settings: Settings,
) -> None:
    content = "合成反馈'); DELETE FROM academic.grades; --"
    feedback_id = submit_feedback("student_s01", "O01", content)
    try:
        with settings.connect() as conn:
            assert conn.execute("SELECT count(*) AS n FROM academic.grades").fetchone()["n"] == 60
            stored = conn.execute(
                "SELECT student_id, content FROM academic.course_feedback WHERE feedback_id = %s",
                (feedback_id,),
            ).fetchone()
            assert stored == {"student_id": "S01", "content": content}
    finally:
        with settings.connect() as conn:
            conn.execute(
                "DELETE FROM academic.course_feedback WHERE feedback_id = %s", (feedback_id,)
            )


def test_audit_writer_can_append_but_not_read_update_or_delete(settings: Settings) -> None:
    with settings.connect("hardened", "sq_audit_writer") as conn:
        conn.execute(
            "INSERT INTO audit.events VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                uuid4(),
                "student_s01",
                "sq_student_s01",
                "gateway",
                "BLOCK",
                "COLUMN_DENIED",
                hashlib.sha256(b"synthetic").hexdigest(),
                datetime.now(UTC),
            ),
        )
        conn.rollback()
        for statement in (
            "SELECT * FROM audit.events",
            "DELETE FROM audit.events",
            "UPDATE audit.events SET decision = 'ALLOW'",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
            conn.rollback()


def test_actual_role_flags_view_owner_and_public_grants(settings: Settings) -> None:
    roles = [*actor_roles(), "sq_context_reader", "sq_audit_writer", "sq_view_owner"]
    with settings.connect() as conn:
        observed = conn.execute(
            "SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
            "FROM pg_roles WHERE rolname = ANY(%s)",
            (roles,),
        ).fetchall()
        assert len(observed) == len(roles)
        assert all(
            not any(row[k] for k in ("rolsuper", "rolbypassrls", "rolcreaterole", "rolcreatedb"))
            for row in observed
        )
        for role in roles:
            assert not conn.execute(
                "SELECT has_database_privilege(%s, current_database(), 'TEMP') AS allowed",
                (role,),
            ).fetchone()["allowed"]
        owners = conn.execute(
            "SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE (n.nspname='academic' AND c.relkind='r') OR n.nspname='api'"
        ).fetchall()
        assert {r["owner"] for r in owners if r["nspname"] == "academic"} == {"sq_owner"}
        assert next(r for r in owners if r["relname"] == "my_contact")["owner"] == "sq_view_owner"
    with query_connection("student_s01") as conn:
        for role in ("sq_owner", "sq_view_owner", "sq_feedback_writer", "sq_teacher_reader"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            conn.rollback()
