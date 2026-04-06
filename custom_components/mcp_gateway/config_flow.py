"""Config flow for MCP Gateway."""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class MCPGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for MCP Gateway."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle a user-initiated flow."""
        if user_input is not None:
            return self.async_create_entry(title="MCP Gateway", data={})
        return self.async_show_form(step_id="user")
