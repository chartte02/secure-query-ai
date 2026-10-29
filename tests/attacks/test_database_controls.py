"""Fixed SQL experiments: these are NOT claims of successful prompt injection."""

from __future__ import annotations

import psycopg
import pytest

from db.client import ContextProvider, query_connection, submit_feedback
from db.manage import assert_target, initialize, snapshot
from db.seed import POISONED_CONTENT, POISONED_FEEDBACK
from db.settings import Settings

pytestmark = pytest.mark.database


def test_same_cross_user_candidate_reads_baseline_but_not_hardened(settings: Settings) -> None:
    candidate = "SELECT student_id, offering_id, score FROM academic.grades WHERE student_id='S02'"
    with query_connection("student_s01", profile="baseline", unsafe_lab=True) as conn:
        assert_target_owner = settings.connect("baseline")
        with assert_target_owner:
            assert_target(assert_target_owner, "baseline", settings)
        assert len(conn.execute(candidate).fetchall()) == 3
    with query_connection("student_s01") as conn:
        assert conn.execute(candidate).fetchall() == []


def test_same_sensitive_candidate_reads_baseline_but_not_hardened(settings: Settings) -> None:
    candidate = "SELECT national_id FROM academic.students WHERE student_id='S02'"
    with query_connection("student_s01", profile="baseline", unsafe_lab=True) as conn:
        assert conn.execute(candidate).fetchone()["national_id"] == "ID_TEST_S02"
    with query_connection("student_s01") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(candidate)
        conn.rollback()


def test_poison_is_retrieved_from_actual_attacker_writable_data_and_restored(
    settings: Settings,
) -> None:
    # Use the real parameterized submission interface, not an injected system prompt.
    feedback_id = submit_feedback("student_s02", "O01", POISONED_CONTENT)
    try:
        context = ContextProvider().get_public_feedback("O01")
        attack = next(r for r in context if r["feedback_id"] == feedback_id)
        assert attack["content"] == POISONED_CONTENT
        assert not attack["was_truncated"]
        assert attack["trust"] == "untrusted_data"
        truncated = ContextProvider().get_public_feedback("O01", max_chars=8)[0]
        assert truncated["was_truncated"]
    finally:
        with settings.connect() as conn:
            conn.execute(
                "DELETE FROM academic.course_feedback WHERE feedback_id=%s", (feedback_id,)
            )


def test_committed_write_is_confined_to_disposable_instance_and_reset_is_repeatable(
    settings: Settings,
) -> None:
    with settings.connect("write_lab") as conn:
        assert_target(conn, "write_lab", settings)
        original = snapshot(conn)
    try:
        with query_connection("student_s01", profile="write_lab", unsafe_lab=True) as conn:
            conn.execute("UPDATE academic.grades SET score=100 WHERE student_id='S02'")
        # Independent connection observes committed state, not an LLM's success message.
        with settings.connect("write_lab") as conn:
            rows = conn.execute(
                "SELECT score FROM academic.grades WHERE student_id='S02'"
            ).fetchall()
            assert all(r["score"] == 100 for r in rows)
        with query_connection("student_s02") as conn:
            assert any(
                r["score"] != 100
                for r in conn.execute("SELECT score FROM academic.grades").fetchall()
            )
    finally:
        restored = initialize("write_lab", reset=True)
        assert restored["sha256"] == original["sha256"]
    repeated = initialize("write_lab", reset=True)
    assert repeated["sha256"] == original["sha256"]


def test_clean_and_poisoned_fixture_only_change_one_feedback_content(settings: Settings) -> None:
    with settings.connect("baseline") as conn:
        assert_target(conn, "baseline", settings)
    original = initialize("baseline", reset=True)
    try:
        poisoned = initialize("baseline", fixture="poisoned-01", reset=True)
        for table, summary in original["tables"].items():
            if table != "course_feedback":
                assert poisoned["tables"][table] == summary
        assert (
            poisoned["tables"]["course_feedback"]["sha256"]
            != original["tables"]["course_feedback"]["sha256"]
        )
        rows = ContextProvider("baseline").get_public_feedback("O01")
        assert (
            next(r for r in rows if r["feedback_id"] == POISONED_FEEDBACK)["content"]
            == POISONED_CONTENT
        )
    finally:
        restored = initialize("baseline", reset=True)
        assert restored["sha256"] == original["sha256"]
