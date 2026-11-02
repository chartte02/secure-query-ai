"""Ollama format schema must not carry length constraints (llamarunner crash)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.models import ModelGeneration
from app.providers import OLLAMA_FORMAT_SCHEMA, _strip_length_constraints


def test_source_schema_carries_max_length_but_ollama_format_does_not() -> None:
    source = ModelGeneration.model_json_schema()
    assert "maxLength" in json.dumps(source), "precondition: the project schema has limits"
    assert "maxLength" not in json.dumps(OLLAMA_FORMAT_SCHEMA)
    assert "minLength" not in json.dumps(OLLAMA_FORMAT_SCHEMA)


def test_stripping_preserves_schema_structure() -> None:
    source = ModelGeneration.model_json_schema()
    stripped = _strip_length_constraints(source)
    assert isinstance(stripped, dict)
    assert stripped["type"] == source["type"]
    assert set(stripped["properties"]) == set(source["properties"])
    assert set(stripped["properties"]["sql"]["anyOf"][0]) == {"type"}  # only maxLength dropped


def test_length_limits_remain_enforced_by_pydantic() -> None:
    ok = ModelGeneration.model_validate({"sql": "SELECT 1", "refusal_reason": None})
    assert ok.sql == "SELECT 1"
    with pytest.raises(ValidationError):
        ModelGeneration.model_validate({"sql": "S" * 10001, "refusal_reason": None})
    with pytest.raises(ValidationError):
        ModelGeneration.model_validate({"sql": "SELECT 1", "refusal_reason": "r" * 1001})


def test_stripping_recurses_into_nested_lists_and_dicts() -> None:
    schema = {
        "properties": {"a": {"anyOf": [{"type": "string", "maxLength": 5}, {"type": "null"}]}},
        "enums": [{"maxLength": 3, "type": "string"}],
        "title": "T",
    }
    stripped = _strip_length_constraints(schema)
    dumped = json.dumps(stripped)
    assert "maxLength" not in dumped
    assert stripped["title"] == "T"
    assert stripped["properties"]["a"]["anyOf"][1] == {"type": "null"}
