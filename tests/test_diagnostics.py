"""Tests for MCP Gateway diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.mcp_gateway.const import DOMAIN
from custom_components.mcp_gateway.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.mcp_gateway.manager import MCPGatewayManager
from custom_components.mcp_gateway.types import MCPGatewayEntry


def _make_entry(device_id: str, port: int, tool_names: list[str]) -> MCPGatewayEntry:
    """Create a minimal MCPGatewayEntry."""
    tools = []
    for name in tool_names:
        tool = MagicMock()
        tool.name = name
        tools.append(tool)

    return MCPGatewayEntry(
        device_id=device_id,
        tools=tools,
        prompt="Test",
        llm_api_id=f"mcp_gateway_{device_id}",
        unregister_api=MagicMock(),
        session_manager=MagicMock(),
        port=port,
    )


def _setup_manager(hass, entries):
    """Set up a mock manager."""
    manager = MagicMock(spec=MCPGatewayManager)
    manager.async_get_all_device_ids.return_value = list(entries.keys())
    manager.async_get_entry = lambda did: entries.get(did)
    hass.data[DOMAIN] = manager
    return manager


async def test_diagnostics_output(hass: HomeAssistant) -> None:
    """Test diagnostics returns correct device information."""
    entries = {
        "d1": _make_entry("d1", 20001, ["get_description", "turn_on"]),
        "d2": _make_entry("d2", 20002, ["get_description", "set_volume"]),
    }
    _setup_manager(hass, entries)

    mock_device = MagicMock(spec=dr.DeviceEntry)
    mock_device.name = "Test Device"
    mock_device.name_by_user = None

    with patch("custom_components.mcp_gateway.diagnostics.dr.async_get") as mock_dr:
        mock_dr.return_value.async_get.return_value = mock_device

        # Pass a MagicMock as entry since we don't use it
        result = await async_get_config_entry_diagnostics(hass, MagicMock())

    assert result["device_count"] == 2
    assert len(result["devices"]) == 2
    assert result["devices"][0]["device_id"] == "d1"
    assert result["devices"][0]["port"] == 20001
    assert result["devices"][0]["tool_count"] == 2
    assert result["devices"][0]["tools"] == ["get_description", "turn_on"]


async def test_diagnostics_empty(hass: HomeAssistant) -> None:
    """Test diagnostics with no devices."""
    _setup_manager(hass, {})

    with patch("custom_components.mcp_gateway.diagnostics.dr.async_get"):
        result = await async_get_config_entry_diagnostics(hass, MagicMock())

    assert result["device_count"] == 0
    assert result["devices"] == []


async def test_diagnostics_device_not_in_registry(hass: HomeAssistant) -> None:
    """Test diagnostics when device is not in the device registry."""
    entries = {"d1": _make_entry("d1", 20001, ["tool1"])}
    _setup_manager(hass, entries)

    with patch("custom_components.mcp_gateway.diagnostics.dr.async_get") as mock_dr:
        mock_dr.return_value.async_get.return_value = None

        result = await async_get_config_entry_diagnostics(hass, MagicMock())

    assert result["device_count"] == 1
    assert result["devices"][0]["name"] == "d1"
