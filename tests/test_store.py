"""Tests for MCP Gateway persistent storage."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.mcp_gateway.store import MCPGatewayStore


async def test_load_empty(hass: HomeAssistant) -> None:
    """Test loading when no data exists."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    assert store.get_device_config("nonexistent") == {}


async def test_set_and_get_device_config(hass: HomeAssistant) -> None:
    """Test setting and getting device configuration."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    store.set_device_config("device_1", {"port": 20001, "enabled": True})
    config = store.get_device_config("device_1")

    assert config["port"] == 20001
    assert config["enabled"] is True


async def test_save_and_reload(hass: HomeAssistant) -> None:
    """Test that data persists after save and reload."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    store.set_device_config("device_1", {"port": 20001})
    await store.async_save()

    # Create a new store instance and reload
    store2 = MCPGatewayStore(hass)
    await store2.async_load()

    config = store2.get_device_config("device_1")
    assert config["port"] == 20001


async def test_remove_device(hass: HomeAssistant) -> None:
    """Test removing a device configuration."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    store.set_device_config("device_1", {"port": 20001})
    store.remove_device("device_1")

    assert store.get_device_config("device_1") == {}


async def test_remove_nonexistent_device(hass: HomeAssistant) -> None:
    """Test removing a device that doesn't exist does not error."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    store.remove_device("nonexistent")  # Should not raise


async def test_multiple_devices(hass: HomeAssistant) -> None:
    """Test storing configs for multiple devices."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    store.set_device_config("device_1", {"port": 20001})
    store.set_device_config("device_2", {"port": 20002})
    await store.async_save()

    store2 = MCPGatewayStore(hass)
    await store2.async_load()

    assert store2.get_device_config("device_1")["port"] == 20001
    assert store2.get_device_config("device_2")["port"] == 20002


async def test_overwrite_device_config(hass: HomeAssistant) -> None:
    """Test overwriting an existing device config."""
    store = MCPGatewayStore(hass)
    await store.async_load()

    store.set_device_config("device_1", {"port": 20001})
    store.set_device_config("device_1", {"port": 20099, "enabled": False})

    config = store.get_device_config("device_1")
    assert config["port"] == 20099
    assert config["enabled"] is False
