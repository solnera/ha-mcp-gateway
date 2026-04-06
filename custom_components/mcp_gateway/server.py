"""MCP Gateway Server implementation.

Creates an MCP Server scoped to a single device's LLM API.
Adapted from homeassistant.components.mcp_server.server.
"""

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from mcp import types
from mcp.server import Server
from voluptuous_openapi import convert

_LOGGER = logging.getLogger(__name__)


def _format_tool(tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None) -> types.Tool:
    """Format tool specification."""
    input_schema = convert(tool.parameters, custom_serializer=custom_serializer)
    return types.Tool(
        name=tool.name,
        description=tool.description or "",
        inputSchema={
            "type": "object",
            "properties": input_schema["properties"],
        },
    )


async def create_device_server(
    hass: HomeAssistant, llm_api_id: str, llm_context: llm.LLMContext
) -> Server:
    """Create a new MCP Server scoped to a specific device's tools.

    The llm_api_id should point to the MCPGatewayAPI registered for this device.
    """
    server = Server[Any]("home-assistant-device")

    async def get_api_instance() -> llm.APIInstance:
        """Get the device-scoped LLM API."""
        return await llm.async_get_api(hass, llm_api_id, llm_context)

    @server.list_prompts()  # type: ignore[no-untyped-call,untyped-decorator]
    async def handle_list_prompts() -> list[types.Prompt]:
        llm_api = await get_api_instance()
        return [
            types.Prompt(
                name=llm_api.api.name,
                description=f"MCP Gateway prompt for {llm_api.api.name}",
            )
        ]

    @server.get_prompt()  # type: ignore[no-untyped-call,untyped-decorator]
    async def handle_get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        llm_api = await get_api_instance()
        if name != llm_api.api.name:
            raise ValueError(f"Unknown prompt: {name}")

        return types.GetPromptResult(
            description=f"MCP Gateway prompt for {llm_api.api.name}",
            messages=[
                types.PromptMessage(
                    role="assistant",
                    content=types.TextContent(
                        type="text",
                        text=llm_api.api_prompt,
                    ),
                )
            ],
        )

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        """List available tools for this device."""
        llm_api = await get_api_instance()
        return [_format_tool(tool, llm_api.custom_serializer) for tool in llm_api.tools]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict) -> Sequence[types.TextContent]:
        """Handle calling a device tool."""
        llm_api = await get_api_instance()
        tool_input = llm.ToolInput(tool_name=name, tool_args=arguments)
        _LOGGER.info("Tool call: %s(%s)", tool_input.tool_name, tool_input.tool_args)

        try:
            tool_response = await llm_api.async_call_tool(tool_input)
        except (HomeAssistantError, vol.Invalid) as e:
            _LOGGER.warning("Tool call %s failed: %s", name, e)
            raise HomeAssistantError(f"Error calling tool: {e}") from e

        _LOGGER.debug("Tool call %s result: %s", name, tool_response)
        return [
            types.TextContent(
                type="text",
                text=json.dumps(tool_response, ensure_ascii=False),
            )
        ]

    return server
