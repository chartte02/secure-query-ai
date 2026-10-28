from __future__ import annotations

import json
from decimal import Decimal

import pytest

from db.client import query_connection
from db.settings import ROOT, Settings

CASES = json.loads(
    (ROOT / "tests" / "attacks" / "cases" / "development.json").read_text(encoding="utf-8")
)["cases"]


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
