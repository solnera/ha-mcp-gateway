"""Public API for the MCP Gateway integration.

Other integrations call async_register_device_tools() to register
MCP tools for their devices.

Every registered tool must declare both an input schema (`parameters`) and a
response schema (`response_schema`), each a voluptuous schema. They are
published to MCP clients as the tool's inputSchema and outputSchema, and a
tool without a response schema is not exposed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN
from .types import DeviceDescription

if TYPE_CHECKING:
    from .manager import MCPGatewayManager


@dataclass(kw_only=True)
class MCPGatewayAPI(llm.API):
    """LLM API scoped to a single device's MCP tools."""

    device_tools: list[llm.Tool]
    device_prompt: str

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        """Return the API instance with device-scoped tools."""
        return llm.APIInstance(
            api=self,
            api_prompt=self.device_prompt,
            llm_context=llm_context,
            tools=self.device_tools,
        )


# Every field of DeviceDescription is optional, to_dict() drops the unset ones.
_DESCRIPTION_RESPONSE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_type"): str,
        vol.Optional("brand"): str,
        vol.Optional("model"): str,
        vol.Optional("alias"): str,
        vol.Optional("description"): str,
        vol.Optional("device_id"): str,
        vol.Optional("serial"): str,
        vol.Optional("mac"): str,
    }
)


class GetDescriptionTool(llm.Tool):
    """MCP tool that returns device metadata per the Wand integration guide."""

    def __init__(self, description: DeviceDescription) -> None:
        """Initialize the get_description tool."""
        self.name = "get_description"
        self.description = "Get device description and metadata"
        self.parameters = vol.Schema({})
        self.response_schema = _DESCRIPTION_RESPONSE_SCHEMA
        self._data = description.to_dict()

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Return the device description as JSON."""
        return self._data


async def async_register_device_tools(
    hass: HomeAssistant,
    device_id: str,
    tools: list[llm.Tool],
    prompt: str | None = None,
    device_description: DeviceDescription | None = None,
) -> Callable[[], None]:
    """Register MCP tools for a specific device.

    Call this in your integration's async_setup_entry() after registering the
    device via device_registry.async_get_or_create().

    Every tool must declare a response schema; a tool without one is dropped
    with an error in the log instead of being published.

    Returns a callable that unregisters the tools. Add it to
    entry.async_on_unload() for automatic cleanup.

    Example::

        from custom_components.mcp_gateway.api import async_register_device_tools
        from custom_components.mcp_gateway.types import DeviceDescription

        async def async_setup_entry(hass, entry):
            device = dr.async_get(hass).async_get_or_create(...)
            unsub = await async_register_device_tools(
                hass,
                device_id=device.id,
                tools=[MyTool()],
                prompt="Device control tools.",
                device_description=DeviceDescription(
                    brand="Acme", model="LED-100", alias="Bedroom Light",
                ),
            )
            entry.async_on_unload(unsub)
    """
    if DOMAIN not in hass.data:
        raise HomeAssistantError(
            f"The {DOMAIN} integration is not set up. Ensure it is listed in your configuration."
        )
    manager: MCPGatewayManager = hass.data[DOMAIN]
    return await manager.async_register(device_id, tools, prompt, device_description)
