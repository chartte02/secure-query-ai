"""Keep member A's model-visible schema aligned with member B's database lab."""

from __future__ import annotations

import re

from app.catalog import (
    CONTEXTS,
    PRINCIPALS,
    SCENARIOS,
    SCHEMA_SQL,
    SCHEMA_VERSION,
)
from db.client import ACTORS
from db.seed import POISONED_CONTENT


def test_schema_version_matches_the_database_lab() -> None:
    assert SCHEMA_VERSION == "campus_lab_v1"


def test_model_visible_schema_hides_sensitive_base_columns() -> None:
    assert "national_id" not in SCHEMA_SQL
    assert "grader_note" not in SCHEMA_SQL
    assert re.search(r"\bphone\b", SCHEMA_SQL) is None


def test_model_visible_schema_exposes_contract_columns() -> None:
    for column in (
        "offering_id",
        "course_name",
        "display_name",
        "credits",
        "term",
        "enrolled_at",
        "visibility",
        "phone_masked",
    ):
        assert column in SCHEMA_SQL


def test_every_principal_exists_in_the_database_actor_map() -> None:
    assert set(PRINCIPALS) <= set(ACTORS)


def test_scenarios_use_known_principals_and_contexts() -> None:
    for scenario in SCENARIOS:
        assert scenario["principal_id"] in PRINCIPALS
        assert scenario["context_profile"] in CONTEXTS


def test_poisoned_context_is_the_database_seed_payload() -> None:
    assert CONTEXTS["poisoned_course_note"] == POISONED_CONTENT
