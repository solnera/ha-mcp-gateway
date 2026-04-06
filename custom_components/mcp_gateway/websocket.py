"""WebSocket API for the MCP Gateway panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .manager import MCPGatewayManager


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket commands for the panel."""
    websocket_api.async_register_command(hass, ws_get_devices)
    websocket_api.async_register_command(hass, ws_get_device_tools)
    websocket_api.async_register_command(hass, ws_update_device)


@websocket_api.websocket_command({vol.Required("type"): "mcp_gateway/get_devices"})
@websocket_api.require_admin
@callback
def ws_get_devices(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all registered MCP devices."""
    manager: MCPGatewayManager = hass.data[DOMAIN]
    dev_reg = dr.async_get(hass)
    store = manager.store

    devices: list[dict[str, Any]] = []
    for device_id in manager.async_get_all_device_ids():
        entry = manager.async_get_entry(device_id)
        if entry is None:
            continue

        # Get device info from registry
        device_entry = dev_reg.async_get(device_id)
        name = device_entry.name_by_user or device_entry.name if device_entry else device_id
        model = device_entry.model if device_entry else None
        manufacturer = device_entry.manufacturer if device_entry else None

        # Get stored config (enabled, custom_prompt)
        config = store.get_device_config(device_id)

        devices.append(
            {
                "device_id": device_id,
                "name": name,
                "model": model,
                "manufacturer": manufacturer,
                "tool_count": len(entry.tools),
                "enabled": config.get("enabled", True),
                "custom_prompt": config.get("custom_prompt", ""),
                "port": entry.port,
            }
        )

    connection.send_result(msg["id"], {"devices": devices})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "mcp_gateway/get_device_tools",
        vol.Required("device_id"): str,
    }
)
@websocket_api.require_admin
@callback
def ws_get_device_tools(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return tool details for a specific device."""
    manager: MCPGatewayManager = hass.data[DOMAIN]
    entry = manager.async_get_entry(msg["device_id"])

    if entry is None:
        connection.send_error(msg["id"], "not_found", "Device not found")
        return

    tools = [{"name": tool.name, "description": tool.description or ""} for tool in entry.tools]

    connection.send_result(
        msg["id"],
        {
            "device_id": msg["device_id"],
            "prompt": entry.prompt,
            "tools": tools,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "mcp_gateway/update_device",
        vol.Required("device_id"): str,
        vol.Optional("enabled"): bool,
        vol.Optional("custom_prompt"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_update_device(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update device configuration (enabled, custom_prompt)."""
    manager: MCPGatewayManager = hass.data[DOMAIN]
    device_id = msg["device_id"]
    store = manager.store

    entry = manager.async_get_entry(device_id)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Device not found")
        return

    config = store.get_device_config(device_id)

    if "enabled" in msg:
        config["enabled"] = msg["enabled"]
    if "custom_prompt" in msg:
        config["custom_prompt"] = msg["custom_prompt"]

    store.set_device_config(device_id, config)
    await store.async_save()

    # Start or stop the MCP server based on enabled state
    if "enabled" in msg:
        await manager.async_set_device_enabled(device_id, msg["enabled"])

    connection.send_result(msg["id"], {"success": True})
