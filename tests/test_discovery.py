"""Tests for MCP Gateway platform discovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.mcp_gateway.const import DOMAIN
from custom_components.mcp_gateway.discovery import MCPGatewayDiscovery
from custom_components.mcp_gateway.manager import MCPGatewayManager


def _make_device(device_id: str, domain: str, config_entry_id: str) -> MagicMock:
    """Create a mock DeviceEntry."""
    device = MagicMock(spec=dr.DeviceEntry)
    device.id = device_id
    device.identifiers = {(domain, "serial_123")}
    device.config_entries = {config_entry_id}
    return device


def _make_platform(tools_result=None):
    """Create a mock MCP platform module."""
    platform = MagicMock()
    platform.async_get_device_tools = AsyncMock(return_value=tools_result)
    return platform


# ---------------------------------------------------------------------------
# Platform registration
# ---------------------------------------------------------------------------


async def test_register_platform(hass: HomeAssistant) -> None:
    """Test that a valid platform module is registered."""
    discovery = MCPGatewayDiscovery(hass)

    platform = _make_platform()

    with patch.object(discovery, "_async_process_existing_devices", new_callable=AsyncMock):
        discovery.async_register_platform(hass, "my_integration", platform)

    assert "my_integration" in discovery._platforms


async def test_register_platform_missing_function(hass: HomeAssistant) -> None:
    """Test that a platform without async_get_device_tools is rejected."""
    discovery = MCPGatewayDiscovery(hass)

    platform = MagicMock(spec=[])  # No attributes
    del platform.async_get_device_tools

    discovery.async_register_platform(hass, "bad_integration", platform)

    assert "bad_integration" not in discovery._platforms


# ---------------------------------------------------------------------------
# Device event handling
# ---------------------------------------------------------------------------


async def test_device_create_event_triggers_registration(
    hass: HomeAssistant,
) -> None:
    """Test that a device create event triggers tool registration."""
    # Set up manager in hass.data
    manager = MagicMock(spec=MCPGatewayManager)
    manager.async_register = AsyncMock(return_value=MagicMock())
    hass.data[DOMAIN] = manager

    discovery = MCPGatewayDiscovery(hass)
    await discovery.async_setup()

    # Register a platform
    tool = MagicMock()
    tool.name = "tool1"
    platform = _make_platform(([tool], "Device prompt"))

    with patch.object(discovery, "_async_process_existing_devices", new_callable=AsyncMock):
        discovery.async_register_platform(hass, "my_integration", platform)

    # Set up device registry mock
    device = _make_device("dev_1", "my_integration", "entry_1")
    config_entry = MagicMock()
    config_entry.domain = "my_integration"

    with (
        patch.object(dr, "async_get") as mock_dr,
        patch.object(hass.config_entries, "async_get_entry", return_value=config_entry),
    ):
        mock_dr.return_value.async_get.return_value = device

        # Fire device create event
        hass.bus.async_fire(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            {"action": "create", "device_id": "dev_1"},
        )
        await hass.async_block_till_done()

    manager.async_register.assert_called_once()
    call_args = manager.async_register.call_args
    assert call_args[0][0] == "dev_1"  # device_id


async def test_device_remove_event_unregisters(hass: HomeAssistant) -> None:
    """Test that a device remove event unregisters its tools."""
    manager = MagicMock(spec=MCPGatewayManager)
    manager.async_register = AsyncMock(return_value=MagicMock())
    hass.data[DOMAIN] = manager

    discovery = MCPGatewayDiscovery(hass)
    await discovery.async_setup()

    # Simulate an auto-registered device
    unsub = MagicMock()
    discovery._auto_unsubs["dev_1"] = unsub

    hass.bus.async_fire(
        dr.EVENT_DEVICE_REGISTRY_UPDATED,
        {"action": "remove", "device_id": "dev_1"},
    )
    await hass.async_block_till_done()

    unsub.assert_called_once()
    assert "dev_1" not in discovery._auto_unsubs

    discovery.async_teardown()


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


async def test_teardown_cleans_up(hass: HomeAssistant) -> None:
    """Test that teardown unsubscribes all listeners and auto-unsubs."""
    discovery = MCPGatewayDiscovery(hass)
    await discovery.async_setup()

    unsub1 = MagicMock()
    unsub2 = MagicMock()
    discovery._auto_unsubs["d1"] = unsub1
    discovery._auto_unsubs["d2"] = unsub2

    discovery.async_teardown()

    unsub1.assert_called_once()
    unsub2.assert_called_once()
    assert discovery._auto_unsubs == {}


# ---------------------------------------------------------------------------
# Platform returns 3-tuple with description
# ---------------------------------------------------------------------------


async def test_platform_returns_description(hass: HomeAssistant) -> None:
    """Test handling platform that returns a 3-tuple with description."""
    from custom_components.mcp_gateway.types import DeviceDescription

    manager = MagicMock(spec=MCPGatewayManager)
    manager.async_register = AsyncMock(return_value=MagicMock())
    hass.data[DOMAIN] = manager

    discovery = MCPGatewayDiscovery(hass)
    await discovery.async_setup()

    desc = DeviceDescription(brand="Test", model="M1")
    tool = MagicMock()
    tool.name = "tool1"
    platform = _make_platform(([tool], "Prompt", desc))

    with patch.object(discovery, "_async_process_existing_devices", new_callable=AsyncMock):
        discovery.async_register_platform(hass, "my_integration", platform)

    device = _make_device("dev_1", "my_integration", "entry_1")
    config_entry = MagicMock()
    config_entry.domain = "my_integration"

    with (
        patch.object(dr, "async_get") as mock_dr,
        patch.object(hass.config_entries, "async_get_entry", return_value=config_entry),
    ):
        mock_dr.return_value.async_get.return_value = device

        hass.bus.async_fire(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            {"action": "create", "device_id": "dev_1"},
        )
        await hass.async_block_till_done()

    call_args = manager.async_register.call_args
    assert call_args[0][3] is desc  # device_description

    discovery.async_teardown()
