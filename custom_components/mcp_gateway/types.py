"""Type definitions for the MCP Gateway integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.helpers import llm

from .session import SessionManager


@dataclass
class DeviceDescription:
    """Device metadata returned by the get_description MCP tool.

    Fields follow the Wand MCP Device Integration Guide.
    """

    device_type: str | None = None
    brand: str | None = None
    model: str | None = None
    alias: str | None = None
    description: str | None = None
    # Unique identifiers (any one suffices)
    device_id: str | None = None
    serial: str | None = None
    mac: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None values."""
        result: dict[str, Any] = {}
        for key in (
            "device_type",
            "brand",
            "model",
            "alias",
            "description",
            "device_id",
            "serial",
            "mac",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass
class MCPGatewayEntry:
    """Runtime entry for a device with MCP Gateway tools."""

    device_id: str
    tools: list[llm.Tool]
    prompt: str | None
    llm_api_id: str
    unregister_api: Callable[[], None]
    session_manager: SessionManager
    port: int
    device_description: DeviceDescription | None = None
