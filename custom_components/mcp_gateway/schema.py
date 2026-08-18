"""Schema helpers for MCP tool definitions.

A tool declares its input schema as `parameters` and its response schema as
`response_schema`, both voluptuous schemas. Both are required: a tool without
a response schema is not exposed (see manager.async_register).

voluptuous_openapi renders a voluptuous schema as an OpenAPI 3.0 schema, while
MCP clients — and the mcp library itself, which validates every tool result
against the tool's outputSchema — expect plain JSON Schema. The rendered
schema is therefore normalized here, most notably OpenAPI's `nullable` flag,
which JSON Schema expresses as a `"null"` type instead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.helpers import llm
from voluptuous_openapi import convert

# Schema keywords holding a list of sub-schemas.
_SUBSCHEMA_LISTS = ("anyOf", "oneOf", "allOf")


def has_response_schema(tool: llm.Tool) -> bool:
    """Check that a tool declares a usable response schema."""
    schema = getattr(tool, "response_schema", None)
    return isinstance(schema, vol.Schema) and bool(schema.schema)


def to_json_schema(schema: Any) -> Any:
    """Convert an OpenAPI 3.0 style schema into plain JSON Schema."""
    if not isinstance(schema, dict):
        return schema

    result = {key: value for key, value in schema.items() if key != "nullable"}
    if isinstance(result.get("properties"), dict):
        result["properties"] = {
            name: to_json_schema(value) for name, value in result["properties"].items()
        }
    if "items" in result:
        result["items"] = to_json_schema(result["items"])
    for key in _SUBSCHEMA_LISTS:
        if isinstance(result.get(key), list):
            result[key] = [to_json_schema(item) for item in result[key]]

    if not schema.get("nullable"):
        return result

    # A schema without a type already accepts null.
    type_ = result.get("type")
    if isinstance(type_, str):
        result["type"] = [type_, "null"]
    elif isinstance(type_, list) and "null" not in type_:
        result["type"] = [*type_, "null"]
    if isinstance(result.get("enum"), list) and None not in result["enum"]:
        result["enum"] = [*result["enum"], None]
    return result


def convert_schema(
    schema: vol.Schema, custom_serializer: Callable[[Any], Any] | None = None
) -> dict[str, Any]:
    """Render a voluptuous schema as a JSON Schema object."""
    return to_json_schema(convert(schema, custom_serializer=custom_serializer))
