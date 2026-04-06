"""Diagnostics support for MCP Gateway."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .manager import MCPGatewayManager


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    manager: MCPGatewayManager = hass.data[DOMAIN]
    dev_reg = dr.async_get(hass)

    devices = []
    for device_id in manager.async_get_all_device_ids():
        mcp_entry = manager.async_get_entry(device_id)
        if mcp_entry is None:
            continue

        device_entry = dev_reg.async_get(device_id)
        devices.append(
            {
                "device_id": device_id,
                "name": (
                    device_entry.name_by_user or device_entry.name if device_entry else device_id
                ),
                "port": mcp_entry.port,
                "tool_count": len(mcp_entry.tools),
                "tools": [t.name for t in mcp_entry.tools],
            }
        )

    return {
        "device_count": len(devices),
        "devices": devices,
    }
