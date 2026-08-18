"""Tests for MCP Gateway Server (MCP protocol layer).

Since the mcp library has pydantic v2 conflicts in the test env,
we test the server's internal logic by calling the registered handlers
directly via the mock Server's captured callbacks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import voluptuous as vol


def _make_api_instance(tools=None, prompt="Test prompt"):
    """Create a mock LLM APIInstance."""
    api = MagicMock()
    api.api = MagicMock()
    api.api.name = "test_api"
    api.api_prompt = prompt
    api.tools = tools or []
    api.custom_serializer = None
    return api


async def test_get_description_tool() -> None:
    """Test the GetDescriptionTool returns device metadata."""
    from custom_components.mcp_gateway.api import GetDescriptionTool
    from custom_components.mcp_gateway.types import DeviceDescription

    desc = DeviceDescription(brand="Acme", model="X100", alias="My Device", device_id="d1")
    tool = GetDescriptionTool(desc)

    assert tool.name == "get_description"

    result = await tool.async_call(MagicMock(), MagicMock(), MagicMock())
    assert result["brand"] == "Acme"
    assert result["model"] == "X100"
    assert result["alias"] == "My Device"
    assert result["device_id"] == "d1"


async def test_get_description_tool_response_schema() -> None:
    """Test the GetDescriptionTool declares a schema matching its response."""
    from custom_components.mcp_gateway.api import GetDescriptionTool
    from custom_components.mcp_gateway.schema import has_response_schema
    from custom_components.mcp_gateway.types import DeviceDescription

    tool = GetDescriptionTool(DeviceDescription(brand="Acme", device_id="d1"))

    assert has_response_schema(tool) is True
    result = await tool.async_call(MagicMock(), MagicMock(), MagicMock())
    # The unset fields are dropped, so the schema must not require them.
    assert tool.response_schema(result) == result


def test_format_tool_publishes_both_schemas() -> None:
    """Test that a tool is published with an input and an output schema."""
    from custom_components.mcp_gateway import server as server_mod

    tool = MagicMock()
    tool.name = "my_tool"
    tool.description = "Do something"
    tool.parameters = vol.Schema({vol.Required("value"): int})
    tool.response_schema = vol.Schema({vol.Required("success"): bool})

    schemas = {
        "in": {"type": "object", "properties": {"value": {"type": "integer"}}},
        "out": {"type": "object", "properties": {"success": {"type": "boolean"}}},
    }
    with (
        patch.object(server_mod, "convert_schema", side_effect=[schemas["in"], schemas["out"]]),
        patch.object(server_mod.types, "Tool") as mock_tool,
    ):
        server_mod._format_tool(tool, None)

    kwargs = mock_tool.call_args.kwargs
    assert kwargs["name"] == "my_tool"
    assert kwargs["inputSchema"] == {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
    }
    assert kwargs["outputSchema"] == schemas["out"]


def test_format_tool_without_response_schema() -> None:
    """Test that a tool without a response schema gets no output schema."""
    from custom_components.mcp_gateway import server as server_mod

    tool = MagicMock()
    tool.name = "my_tool"
    tool.description = "Do something"
    tool.parameters = vol.Schema({})
    tool.response_schema = None

    with (
        patch.object(server_mod, "convert_schema", return_value={"properties": {}}),
        patch.object(server_mod.types, "Tool") as mock_tool,
    ):
        server_mod._format_tool(tool, None)

    assert mock_tool.call_args.kwargs["outputSchema"] is None


async def test_mcp_gateway_api_instance() -> None:
    """Test MCPGatewayAPI returns an APIInstance with the right tools."""
    from custom_components.mcp_gateway.api import MCPGatewayAPI

    tool = MagicMock()
    tool.name = "my_tool"

    api = MCPGatewayAPI(
        hass=MagicMock(),
        id="test_id",
        name="Test API",
        device_tools=[tool],
        device_prompt="Do things",
    )

    instance = await api.async_get_api_instance(MagicMock())
    assert instance.tools == [tool]
    assert instance.api_prompt == "Do things"
