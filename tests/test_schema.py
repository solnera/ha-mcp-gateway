"""Tests for the tool schema helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import voluptuous as vol

from custom_components.mcp_gateway.schema import has_response_schema, to_json_schema

# ---------------------------------------------------------------------------
# has_response_schema
# ---------------------------------------------------------------------------


def test_has_response_schema() -> None:
    """Test that only a non-empty voluptuous schema is accepted."""
    tool = MagicMock()
    tool.response_schema = vol.Schema({vol.Required("value"): int})
    assert has_response_schema(tool) is True


def test_has_response_schema_empty() -> None:
    """Test that an empty schema does not count as a response schema."""
    tool = MagicMock()
    tool.response_schema = vol.Schema({})
    assert has_response_schema(tool) is False


def test_has_response_schema_missing() -> None:
    """Test a tool that declares no response schema at all."""

    class _Tool:
        name = "no_schema"

    assert has_response_schema(_Tool()) is False


def test_has_response_schema_wrong_type() -> None:
    """Test that a plain dict is not accepted as a response schema."""
    tool = MagicMock()
    tool.response_schema = {"value": int}
    assert has_response_schema(tool) is False


# ---------------------------------------------------------------------------
# to_json_schema
# ---------------------------------------------------------------------------


def test_to_json_schema_nullable_type() -> None:
    """Test that OpenAPI's nullable becomes a JSON Schema null type."""
    assert to_json_schema({"type": "integer", "nullable": True}) == {"type": ["integer", "null"]}


def test_to_json_schema_nullable_enum() -> None:
    """Test that a nullable enum accepts null as well."""
    assert to_json_schema({"type": "integer", "enum": [1, 2], "nullable": True}) == {
        "type": ["integer", "null"],
        "enum": [1, 2, None],
    }


def test_to_json_schema_keeps_untouched_schema() -> None:
    """Test that a schema without nullable is returned unchanged."""
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    assert to_json_schema(schema) == schema


def test_to_json_schema_nested() -> None:
    """Test that nested properties, items and sub-schemas are converted."""
    schema = {
        "type": "object",
        "properties": {
            "result": {
                "type": "object",
                "properties": {"code": {"type": "integer", "nullable": True}},
            },
            "list": {"type": "array", "items": {"type": "string", "nullable": True}},
            "either": {"anyOf": [{"type": "boolean", "nullable": True}]},
        },
    }
    converted = to_json_schema(schema)
    props = converted["properties"]
    assert props["result"]["properties"]["code"] == {"type": ["integer", "null"]}
    assert props["list"]["items"] == {"type": ["string", "null"]}
    assert props["either"]["anyOf"] == [{"type": ["boolean", "null"]}]


def test_to_json_schema_typeless_nullable() -> None:
    """Test that a nullable schema without a type keeps accepting anything."""
    assert to_json_schema({"nullable": True}) == {}


def test_to_json_schema_non_dict() -> None:
    """Test that a non-dict schema is passed through."""
    assert to_json_schema(True) is True
