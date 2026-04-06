"""Tests for MCP Gateway Manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.mcp_gateway.const import PORT_RANGE_START
from custom_components.mcp_gateway.manager import MCPGatewayManager
from custom_components.mcp_gateway.types import DeviceDescription

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


async def test_register_device(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test registering MCP tools for a device."""
    unsub = await manager.async_register(
        "device_1", sample_tools, "Test prompt", sample_description
    )

    assert "device_1" in manager.async_get_all_device_ids()
    entry = manager.async_get_entry("device_1")
    assert entry is not None
    assert entry.port == PORT_RANGE_START
    assert entry.prompt == "Test prompt"
    # get_description tool + sample_tools
    assert len(entry.tools) == 2
    assert entry.tools[0].name == "get_description"
    assert entry.tools[1].name == "test_tool"

    # HTTP server started
    mock_http_server.return_value.start.assert_called_once()

    unsub()
    await hass.async_block_till_done()


async def test_register_without_description(
    hass: HomeAssistant, manager, sample_tools, mock_http_server
) -> None:
    """Test registering a device without a description builds from registry."""
    # Mock device registry
    mock_device = MagicMock()
    mock_device.name = "My Device"
    mock_device.name_by_user = None
    mock_device.manufacturer = "Acme"
    mock_device.model = "X100"

    with patch.object(dr, "async_get") as mock_dr:
        mock_dr.return_value.async_get.return_value = mock_device
        await manager.async_register("device_1", sample_tools, "Prompt")

    entry = manager.async_get_entry("device_1")
    assert entry is not None
    assert entry.device_description.alias == "My Device"
    assert entry.device_description.brand == "Acme"


async def test_register_replaces_existing(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test that re-registering a device replaces the old entry."""
    await manager.async_register("device_1", sample_tools, "Old prompt", sample_description)
    await manager.async_register("device_1", sample_tools, "New prompt", sample_description)

    entry = manager.async_get_entry("device_1")
    assert entry is not None
    assert entry.prompt == "New prompt"
    assert len(manager.async_get_all_device_ids()) == 1


async def test_unregister_device(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test unregistering a device stops server and cleans up."""
    unsub = await manager.async_register("device_1", sample_tools, "Prompt", sample_description)

    unsub()
    await hass.async_block_till_done()

    assert manager.async_get_entry("device_1") is None
    assert "device_1" not in manager.async_get_all_device_ids()
    mock_http_server.return_value.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Port allocation
# ---------------------------------------------------------------------------


async def test_port_allocation_sequential(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test that ports are allocated sequentially."""
    await manager.async_register("device_1", sample_tools, "P1", sample_description)
    await manager.async_register("device_2", sample_tools, "P2", sample_description)

    e1 = manager.async_get_entry("device_1")
    e2 = manager.async_get_entry("device_2")
    assert e1.port == PORT_RANGE_START
    assert e2.port == PORT_RANGE_START + 1


async def test_port_reuse_from_store(
    hass: HomeAssistant, mock_zeroconf, mock_http_server, mock_llm_register
) -> None:
    """Test that a persisted port is reused after restart."""
    mgr = MCPGatewayManager(hass)
    await mgr.async_setup()

    # Pre-populate store with a port
    mgr.store.set_device_config("device_1", {"port": 25000})
    await mgr.store.async_save()

    tool = MagicMock()
    tool.name = "t"
    tool.description = ""
    desc = DeviceDescription(device_id="device_1")

    await mgr.async_register("device_1", [tool], "P", desc)

    entry = mgr.async_get_entry("device_1")
    assert entry.port == 25000
    await mgr.async_shutdown()


async def test_port_retry_on_conflict(
    hass: HomeAssistant, mock_zeroconf, mock_llm_register
) -> None:
    """Test port retry when the first port is unavailable."""
    with patch("custom_components.mcp_gateway.manager.MCPGatewayHttpServer") as mock_cls:
        instance = mock_cls.return_value
        # First start fails, second succeeds
        instance.start = AsyncMock(side_effect=[OSError("port in use"), None])
        instance.stop = AsyncMock()

        mgr = MCPGatewayManager(hass)
        await mgr.async_setup()

        tool = MagicMock()
        tool.name = "t"
        tool.description = ""
        desc = DeviceDescription(device_id="device_1")

        await mgr.async_register("device_1", [tool], "P", desc)

        entry = mgr.async_get_entry("device_1")
        # Should have gotten the second port after first failed
        assert entry.port == PORT_RANGE_START + 1
        await mgr.async_shutdown()


# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------


async def test_disable_device_stops_server(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test disabling a device stops its HTTP server."""
    await manager.async_register("device_1", sample_tools, "P", sample_description)
    mock_http_server.return_value.start.assert_called_once()

    await manager.async_set_device_enabled("device_1", False)

    mock_http_server.return_value.stop.assert_called_once()


async def test_enable_device_starts_server(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test enabling a previously disabled device starts its server."""
    # Set device as disabled in store before registration
    manager.store.set_device_config("device_1", {"enabled": False})

    await manager.async_register("device_1", sample_tools, "P", sample_description)
    # Server should NOT have started (disabled)
    mock_http_server.return_value.start.assert_not_called()

    await manager.async_set_device_enabled("device_1", True)

    mock_http_server.return_value.start.assert_called_once()


async def test_enable_already_enabled_noop(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test enabling an already-enabled device is a no-op."""
    await manager.async_register("device_1", sample_tools, "P", sample_description)
    assert mock_http_server.return_value.start.call_count == 1

    await manager.async_set_device_enabled("device_1", True)

    # Should not start a second time
    assert mock_http_server.return_value.start.call_count == 1


async def test_disable_nonexistent_device_noop(hass: HomeAssistant, manager) -> None:
    """Test disabling a nonexistent device does not error."""
    await manager.async_set_device_enabled("nonexistent", False)


# ---------------------------------------------------------------------------
# Device registry events
# ---------------------------------------------------------------------------


async def test_device_removal_event(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test that removing a device from registry unregisters its tools."""
    await manager.async_register("device_1", sample_tools, "P", sample_description)

    # Fire device removal event
    hass.bus.async_fire(
        dr.EVENT_DEVICE_REGISTRY_UPDATED,
        {"action": "remove", "device_id": "device_1"},
    )
    await hass.async_block_till_done()

    assert manager.async_get_entry("device_1") is None
    mock_http_server.return_value.stop.assert_called()


async def test_device_update_event_ignored(
    hass: HomeAssistant, manager, sample_tools, sample_description, mock_http_server
) -> None:
    """Test that non-removal device events are ignored."""
    await manager.async_register("device_1", sample_tools, "P", sample_description)

    hass.bus.async_fire(
        dr.EVENT_DEVICE_REGISTRY_UPDATED,
        {"action": "update", "device_id": "device_1"},
    )
    await hass.async_block_till_done()

    assert manager.async_get_entry("device_1") is not None


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


async def test_shutdown(
    hass: HomeAssistant, mock_zeroconf, mock_http_server, mock_llm_register
) -> None:
    """Test graceful shutdown stops all servers."""
    mgr = MCPGatewayManager(hass)
    await mgr.async_setup()

    tool = MagicMock()
    tool.name = "t"
    tool.description = ""
    desc = DeviceDescription(device_id="d1")

    await mgr.async_register("d1", [tool], "P", desc)
    await mgr.async_register("d2", [tool], "P", desc)

    await mgr.async_shutdown()

    assert mgr.async_get_all_device_ids() == []
    assert mock_http_server.return_value.stop.call_count >= 2
