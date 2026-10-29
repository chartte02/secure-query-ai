"""Trusted B-to-A/C boundary. No model-generated SQL execution API is supplied here."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from db.settings import Profile, Settings


@dataclass(frozen=True)
class Actor:
    actor_id: str
    actor_type: str
    student_id: str | None
    teacher_id: str | None
    db_role: str


ACTORS = {
    **{
        f"student_s{n:02}": Actor(
            f"student_s{n:02}", "student", f"S{n:02}", None, f"sq_student_s{n:02}"
        )
        for n in range(1, 21)
    },
    **{
        f"teacher_t{n:02}": Actor(
            f"teacher_t{n:02}", "teacher", None, f"T{n:02}", f"sq_teacher_t{n:02}"
        )
        for n in range(1, 4)
    },
}


def resolve_actor(actor_id: str) -> Actor:
    try:
        return ACTORS[actor_id]
    except KeyError:
        raise ValueError(
            "Unknown preset actor; natural language cannot create identities."
        ) from None


def query_connection(
    actor_id: str, *, profile: Profile = "hardened", unsafe_lab: bool = False
) -> psycopg.Connection:
    """C uses the connection only after its SQL gateway allows a candidate."""
    actor = resolve_actor(actor_id)
    role = actor.db_role
    if profile != "hardened":
        if not unsafe_lab:
            raise ValueError("Non-hardened connections require explicit unsafe_lab=True.")
        role = "sq_lab_reader" if profile == "baseline" else "sq_lab_writer"
    return Settings.load().connect(profile, role)


class ContextProvider:
    """Only public data; no grade/student-PII credentials and no arbitrary SQL input."""

    def __init__(self, profile: Profile = "hardened") -> None:
        if profile == "write_lab":
            raise ValueError("The disposable write lab has no model context endpoint.")
        self.profile = profile

    def get_public_feedback(
        self, offering_id: str, max_rows: int = 3, max_chars: int = 512
    ) -> list[dict]:
        if not 1 <= max_rows <= 10 or not 1 <= max_chars <= 2000:
            raise ValueError("Context bounds: 1..10 rows, 1..2000 characters.")
        with Settings.load().connect(self.profile, "sq_context_reader") as conn:
            rows = conn.execute(
                "SELECT feedback_id, offering_id, content FROM academic.course_feedback "
                "WHERE offering_id = %s AND visibility = 'public' "
                "ORDER BY created_at DESC, feedback_id LIMIT %s",
                (offering_id, max_rows),
            ).fetchall()
        return [
            {
                **row,
                "content": row["content"][:max_chars],
                "source_kind": "database_feedback",
                "was_truncated": len(row["content"]) > max_chars,
                "content_digest": hashlib.sha256(row["content"].encode()).hexdigest(),
                "trust": "untrusted_data",
            }
            for row in rows
        ]

    def get_course_catalog(self) -> list[dict]:
        with Settings.load().connect(self.profile, "sq_context_reader") as conn:
            return conn.execute(
                "SELECT course_id, course_name, description, credits "
                "FROM academic.courses ORDER BY course_id"
            ).fetchall()


def submit_feedback(actor_id: str, offering_id: str, content: str, *, public: bool = True) -> str:
    """A separate business operation, not an LLM SQL tool. RLS checks actor/enrollment."""
    actor = resolve_actor(actor_id)
    if actor.student_id is None:
        raise ValueError("Only students can submit course feedback.")
    if not 1 <= len(content) <= 2000:
        raise ValueError("Feedback must contain 1..2000 characters.")
    feedback_id = f"FB_USER_{uuid4().hex}"
    with Settings.load().connect("hardened", f"sq_feedback_{actor.student_id.lower()}") as conn:
        conn.execute(
            "INSERT INTO academic.course_feedback "
            "(feedback_id, student_id, offering_id, content, visibility, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                feedback_id,
                actor.student_id,
                offering_id,
                content,
                "public" if public else "private",
                datetime.now(UTC),
            ),
        )
    return feedback_id


def public_actor_contract(actor_id: str) -> dict:
    """Safe metadata only; no credential, DSN or role selection supplied by the caller."""
    actor = asdict(resolve_actor(actor_id))
    actor.pop("db_role")
    return actor
