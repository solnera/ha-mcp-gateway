"""Tests for MCP Gateway WebSocket API.

Tests the handler functions directly to avoid environment setup issues.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.mcp_gateway.const import DOMAIN
from custom_components.mcp_gateway.manager import MCPGatewayManager
from custom_components.mcp_gateway.store import MCPGatewayStore
from custom_components.mcp_gateway.types import MCPGatewayEntry
from custom_components.mcp_gateway.websocket import (
    ws_get_device_tools,
    ws_get_devices,
    ws_update_device,
)


def _make_entry(device_id: str, port: int, tools: list | None = None) -> MCPGatewayEntry:
    """Create a minimal MCPGatewayEntry for testing."""
    if tools is None:
        tool = MagicMock()
        tool.name = "test_tool"
        tool.description = "A test tool"
        tools = [tool]

    return MCPGatewayEntry(
        device_id=device_id,
        tools=tools,
        prompt="Test prompt",
        llm_api_id=f"mcp_gateway_{device_id}",
        unregister_api=MagicMock(),
        session_manager=MagicMock(),
        port=port,
    )


async def _setup_manager(hass: HomeAssistant, entries: dict[str, MCPGatewayEntry]) -> MagicMock:
    """Set up a mock manager in hass.data."""
    manager = MagicMock(spec=MCPGatewayManager)
    manager.async_get_all_device_ids.return_value = list(entries.keys())
    manager.async_get_entry = lambda did: entries.get(did)
    manager.store = MCPGatewayStore(hass)
    await manager.store.async_load()
    manager.async_set_device_enabled = AsyncMock()
    hass.data[DOMAIN] = manager
    return manager


def _mock_connection():
    """Create a mock websocket connection."""
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


async def test_get_devices(hass: HomeAssistant) -> None:
    """Test ws_get_devices returns device list."""
    entries = {
        "d1": _make_entry("d1", 20001),
        "d2": _make_entry("d2", 20002),
    }
    await _setup_manager(hass, entries)

    mock_device = MagicMock()
    mock_device.name = "Device One"
    mock_device.name_by_user = None
    mock_device.model = "Model-X"
    mock_device.manufacturer = "Acme"

    conn = _mock_connection()
    msg = {"id": 1, "type": "mcp_gateway/get_devices"}

    with patch("custom_components.mcp_gateway.websocket.dr.async_get") as mock_dr:
        mock_dr.return_value.async_get.return_value = mock_device
        ws_get_devices(hass, conn, msg)

    conn.send_result.assert_called_once()
    result = conn.send_result.call_args[0]
    assert result[0] == 1  # msg id
    devices = result[1]["devices"]
    assert len(devices) == 2
    assert devices[0]["device_id"] == "d1"
    assert devices[0]["port"] == 20001
    assert devices[0]["tool_count"] == 1
    assert devices[0]["name"] == "Device One"


async def test_get_device_tools(hass: HomeAssistant) -> None:
    """Test ws_get_device_tools returns tool details."""
    tool = MagicMock()
    tool.name = "my_tool"
    tool.description = "Does things"
    entries = {"d1": _make_entry("d1", 20001, [tool])}
    await _setup_manager(hass, entries)

    conn = _mock_connection()
    msg = {"id": 1, "type": "mcp_gateway/get_device_tools", "device_id": "d1"}

    ws_get_device_tools(hass, conn, msg)

    conn.send_result.assert_called_once()
    result = conn.send_result.call_args[0][1]
    assert result["device_id"] == "d1"
    assert result["prompt"] == "Test prompt"
    assert len(result["tools"]) == 1
    assert result["tools"][0]["name"] == "my_tool"


async def test_get_device_tools_not_found(hass: HomeAssistant) -> None:
    """Test ws_get_device_tools with unknown device."""
    await _setup_manager(hass, {})

    conn = _mock_connection()
    msg = {"id": 1, "type": "mcp_gateway/get_device_tools", "device_id": "nonexistent"}

    ws_get_device_tools(hass, conn, msg)

    conn.send_error.assert_called_once()
    assert conn.send_error.call_args[0][1] == "not_found"


async def test_update_device_enabled(hass: HomeAssistant) -> None:
    """Test ws_update_device toggles enabled state."""
    entries = {"d1": _make_entry("d1", 20001)}
    manager = await _setup_manager(hass, entries)

    conn = _mock_connection()
    msg = {
        "id": 1,
        "type": "mcp_gateway/update_device",
        "device_id": "d1",
        "enabled": False,
    }

    # @async_response makes this sync — it schedules as a task
    ws_update_device(hass, conn, msg)
    await hass.async_block_till_done()

    conn.send_result.assert_called_once()
    manager.async_set_device_enabled.assert_called_once_with("d1", False)

    config = manager.store.get_device_config("d1")
    assert config["enabled"] is False


async def test_update_device_custom_prompt(hass: HomeAssistant) -> None:
    """Test ws_update_device saves custom prompt."""
    entries = {"d1": _make_entry("d1", 20001)}
    manager = await _setup_manager(hass, entries)

    conn = _mock_connection()
    msg = {
        "id": 1,
        "type": "mcp_gateway/update_device",
        "device_id": "d1",
        "custom_prompt": "You are a helpful assistant.",
    }

    ws_update_device(hass, conn, msg)
    await hass.async_block_till_done()

    conn.send_result.assert_called_once()
    config = manager.store.get_device_config("d1")
    assert config["custom_prompt"] == "You are a helpful assistant."


async def test_update_device_not_found(hass: HomeAssistant) -> None:
    """Test ws_update_device with unknown device."""
    await _setup_manager(hass, {})

    conn = _mock_connection()
    msg = {
        "id": 1,
        "type": "mcp_gateway/update_device",
        "device_id": "nonexistent",
        "enabled": False,
    }

    ws_update_device(hass, conn, msg)
    await hass.async_block_till_done()

    conn.send_error.assert_called_once()
    assert conn.send_error.call_args[0][1] == "not_found"
