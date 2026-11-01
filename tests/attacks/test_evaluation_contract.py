"""S4 frozen evaluation set: structure, diversity, and machine-checkable expectations."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal

import psycopg.errors
import pytest

from db.client import ACTORS, query_connection
from db.settings import ROOT, Settings

EVALUATION = json.loads(
    (ROOT / "tests" / "attacks" / "cases" / "evaluation.json").read_text(encoding="utf-8")
)
CASES = EVALUATION["cases"]
BY_CATEGORY = Counter(case["category"] for case in CASES)
EXPECTED_COUNTS = {
    "normal": 20,
    "cross_user_read": 10,
    "sensitive_column_read": 8,
    "direct_injection": 8,
    "indirect_injection": 6,
    "indirect_injection_clean_control": 2,
    "dangerous_operation": 6,
}
EFFECT_VALUES = {
    "no_other_student_rows",
    "no_out_of_scope_rows",
    "only_own_rows_visible",
    "database_column_permission_denied",
    "database_column_permission_denied_or_no_rows",
    "identity_remains_student_s01",
    "no_committed_change",
    "authorized_course_answer",
}


def test_evaluation_set_is_frozen_with_expected_totals() -> None:
    assert EVALUATION["status"] == "frozen_20261101_not_tuning_target"
    assert EVALUATION["seed_version"] == "20261028-v1"
    assert EVALUATION["model_results"] is None
    assert len(CASES) == 60
    assert dict(BY_CATEGORY) == EXPECTED_COUNTS


def test_case_ids_are_unique_and_stable() -> None:
    ids = [case["case_id"] for case in CASES]
    assert len(set(ids)) == 60
    prefixes = {"EN", "ER", "EC", "ED", "EI", "EW"}
    assert {case_id.split("-")[0] for case_id in ids} == prefixes


def test_every_actor_is_a_preset_identity() -> None:
    for case in CASES:
        assert case["actor_id"] in ACTORS, case["case_id"]
        if "attacker_id" in case:
            assert case["attacker_id"] in ACTORS, case["case_id"]
            assert case["attacker_id"] != case["actor_id"], case["case_id"]


def test_attack_cases_carry_machine_checkable_expectations() -> None:
    for case in CASES:
        if case["category"] == "normal":
            assert "expected_hardened_rows" in case, case["case_id"]
            continue
        assert case["expected_hardened_effect"] in EFFECT_VALUES, case["case_id"]
        assert case.get("effect_tags"), case["case_id"]


def test_dangerous_operations_declare_disposable_scope() -> None:
    for case in CASES:
        if case["category"] == "dangerous_operation":
            assert case["execution_scope"] == "only_disposable_write_lab_for_unsafe_experiment"


def test_indirect_injection_pairs_and_contexts() -> None:
    poisoned = [case for case in CASES if case["fixture"] == "poisoned-01"]
    controls = [case for case in CASES if case["category"] == "indirect_injection_clean_control"]
    assert len(poisoned) == 6
    assert len(controls) == 2
    by_id = {case["case_id"]: case for case in CASES}
    for case in poisoned + controls:
        assert case["context_offering_id"] == "O01"
        assert case["required_context_ids"] == ["FB_ATTACK_01"]
    for control in controls:  # each clean control pairs a poisoned case with the same question
        paired = by_id[control["paired_case_id"]]
        assert paired["fixture"] == "poisoned-01"
        assert paired["question"] == control["question"]


def test_question_texts_are_diverse_within_attack_categories() -> None:
    for category, expected in (("cross_user_read", 10), ("sensitive_column_read", 8)):
        questions = [case["question"] for case in CASES if case["category"] == category]
        assert len(set(questions)) == expected, "no duplicate phrasings within a category"
    direct = [case["question"] for case in CASES if case["category"] == "direct_injection"]
    assert any("\u4e00" <= ch <= "\u9fff" for ch in "".join(direct))
    assert any(all(not ("\u4e00" <= ch <= "\u9fff") for ch in q) for q in direct), (
        "direct injection must include non-Chinese variants"
    )


@pytest.mark.database
@pytest.mark.parametrize(
    "case", [case for case in CASES if "reference_sql" in case], ids=lambda case: case["case_id"]
)
def test_normal_reference_results_are_executable_and_permission_correct(
    settings: Settings, case: dict
) -> None:
    with query_connection(case["actor_id"]) as conn:
        rows = conn.execute(case["reference_sql"]).fetchall()
    normalized = [
        {key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()}
        for row in rows
    ]
    assert normalized == case["expected_hardened_rows"]


@pytest.mark.database
@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["category"] == "sensitive_column_read"],
    ids=lambda case: case["case_id"],
)
def test_sensitive_candidates_are_denied_on_hardened(settings: Settings, case: dict) -> None:
    """Fixed candidates prove column denial; NL-only cases rely on tag EC effects at runtime."""
    if "fixed_candidate_sql" not in case:
        pytest.skip("no fixed candidate; machine-checked via category expectation")
    with query_connection(case["actor_id"]) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as excinfo:
            conn.execute(case["fixed_candidate_sql"])
        assert excinfo.value.sqlstate == "42501"
