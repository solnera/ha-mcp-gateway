"""Tests for MCP Gateway Server (MCP protocol layer).

Since the mcp library has pydantic v2 conflicts in the test env,
we test the server's internal logic by calling the registered handlers
directly via the mock Server's captured callbacks.
"""

from __future__ import annotations

from unittest.mock import MagicMock


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
