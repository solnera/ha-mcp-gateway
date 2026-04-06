"""Persistent storage for MCP Gateway configuration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


class MCPGatewayStore:
    """Persistent storage for MCP Gateway configuration.

    Stores user-facing configuration only (enabled/disabled, custom prompts).
    Tool definitions are NOT persisted — they are re-registered by integrations
    at runtime.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Load data from storage."""
        stored = await self._store.async_load()
        if stored and "devices" in stored:
            self._data = stored["devices"]

    async def async_save(self) -> None:
        """Save data to storage."""
        await self._store.async_save({"devices": self._data})

    def get_device_config(self, device_id: str) -> dict[str, Any]:
        """Get configuration for a device."""
        return self._data.get(device_id, {})

    def set_device_config(self, device_id: str, config: dict[str, Any]) -> None:
        """Set configuration for a device."""
        self._data[device_id] = config

    def remove_device(self, device_id: str) -> None:
        """Remove a device configuration."""
        self._data.pop(device_id, None)
