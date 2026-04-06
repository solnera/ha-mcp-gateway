"""Tests for MCP Gateway integration setup and teardown."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.mcp_gateway import async_setup_entry, async_unload_entry
from custom_components.mcp_gateway.const import DOMAIN


async def test_setup_and_unload(hass: HomeAssistant, config_entry, mock_integration_deps) -> None:
    """Test setting up and unloading a config entry."""
    result = await async_setup_entry(hass, config_entry)

    assert result is True
    assert DOMAIN in hass.data
    mock_integration_deps["manager"].async_setup.assert_called_once()
    mock_integration_deps["discovery"].async_setup.assert_called_once()

    # Unload
    result = await async_unload_entry(hass, config_entry)

    assert result is True
    assert DOMAIN not in hass.data
    mock_integration_deps["manager"].async_shutdown.assert_called_once()
    mock_integration_deps["discovery"].async_teardown.assert_called_once()


async def test_setup_entry_creates_manager(
    hass: HomeAssistant, config_entry, mock_integration_deps
) -> None:
    """Test that setup_entry creates and stores a manager."""
    await async_setup_entry(hass, config_entry)

    assert DOMAIN in hass.data
    mock_integration_deps["manager_cls"].assert_called_once_with(hass)


async def test_unload_without_setup(hass: HomeAssistant, config_entry) -> None:
    """Test unloading when nothing was set up does not error."""
    result = await async_unload_entry(hass, config_entry)
    assert result is True
