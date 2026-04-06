"""Tests for MCP Gateway config flow."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mcp_gateway.config_flow import MCPGatewayConfigFlow


async def test_user_flow(hass: HomeAssistant) -> None:
    """Test the user config flow shows form then creates entry."""
    flow = MCPGatewayConfigFlow()
    flow.hass = hass

    # Step 1: show form
    result = await flow.async_step_user()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # Step 2: submit creates entry
    result = await flow.async_step_user(user_input={})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MCP Gateway"
    assert result["data"] == {}
