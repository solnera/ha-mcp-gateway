"""The MCP Gateway integration.

Provides per-device MCP (Model Context Protocol) server endpoints.

Integrations can expose MCP tools for their devices by providing an ``mcp.py``
module with an ``async_get_device_tools`` function. This integration discovers
those modules automatically and registers tools when devices appear.

Each device gets its own standalone HTTP server on a unique port (20000-30000)
with the MCP endpoint at ``/mcp/``. Each device is also advertised via mDNS
(``_mcp._tcp.local.``) for automatic discovery.

Manual registration is also available via the public API:

    from custom_components.mcp_gateway.api import async_register_device_tools

    unsub = await async_register_device_tools(hass, device_id, tools, prompt)
    entry.async_on_unload(unsub)
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import integration_platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .discovery import MCPGatewayDiscovery
from .manager import MCPGatewayManager
from .websocket import async_register_websocket_commands

__all__ = ["DOMAIN"]

PLATFORM_NAME = "mcp"
FRONTEND_URL = f"/{DOMAIN}_panel"
PANEL_URL = f"/{DOMAIN}_static"
PANEL_DIR = Path(__file__).parent / "frontend"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up MCP Gateway (called once per HA session).

    Registers the frontend panel and static paths here so they survive
    config entry reload without duplicate registration errors.
    """
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(PANEL_DIR), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=FRONTEND_URL.lstrip("/"),
        webcomponent_name="mcp-gateway-panel",
        sidebar_title="MCP Gateway",
        sidebar_icon="mdi:api",
        js_url=f"{PANEL_URL}/panel.js",
        require_admin=True,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MCP Gateway from a config entry."""
    manager = MCPGatewayManager(hass)
    hass.data[DOMAIN] = manager
    await manager.async_setup()

    # WebSocket API for frontend panel
    async_register_websocket_commands(hass)

    # Platform discovery: find integrations that provide mcp.py
    discovery = MCPGatewayDiscovery(hass)
    await discovery.async_setup()
    hass.data[f"{DOMAIN}_discovery"] = discovery

    await integration_platform.async_process_integration_platforms(
        hass, PLATFORM_NAME, discovery.async_register_platform
    )

    async def _async_shutdown(event: Event) -> None:
        """Clean up on Home Assistant shutdown."""
        discovery.async_teardown()
        await manager.async_shutdown()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload MCP Gateway config entry."""
    discovery = hass.data.pop(f"{DOMAIN}_discovery", None)
    if discovery:
        discovery.async_teardown()

    manager = hass.data.pop(DOMAIN, None)
    if manager:
        await manager.async_shutdown()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove MCP Gateway config entry and clean up persisted storage."""
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    await store.async_remove()
