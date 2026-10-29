from __future__ import annotations

import pytest

from db.client import public_actor_contract, query_connection, resolve_actor
from db.settings import Settings


def test_arbitrary_identity_or_unsafe_profile_is_not_accepted() -> None:
    assert resolve_actor("student_s01").student_id == "S01"
    with pytest.raises(ValueError, match="Unknown preset actor"):
        resolve_actor("administrator; SET ROLE sq_owner")
    with pytest.raises(ValueError, match="explicit unsafe_lab"):
        query_connection("student_s01", profile="baseline")
    with pytest.raises(ValueError, match="Unknown lab profile"):
        Settings("unused", "unused", "unused").connect("production")


def test_public_identity_contract_has_no_connection_secrets() -> None:
    assert public_actor_contract("student_s01") == {
        "actor_id": "student_s01",
        "actor_type": "student",
        "student_id": "S01",
        "teacher_id": None,
    }
