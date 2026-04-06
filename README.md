# MCP Gateway

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that provides standalone [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server endpoints for each device.

## Features

- **Per-device MCP servers** — Each registered device gets its own HTTP server on a unique port (20000-30000) serving MCP protocol endpoints
- **Auto-discovery** — Devices are advertised via mDNS (`_mcp._tcp.local.`) for automatic discovery
- **Platform integration** — Other integrations can automatically register device MCP tools by providing an `mcp.py` module
- **Manual registration API** — Register device tools programmatically via `async_register_device_tools()`
- **Admin panel** — Sidebar panel to view and manage registered MCP devices
- **Streamable HTTP and SSE transport support**

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed
2. Click the menu in the top right corner of HACS and select **Custom repositories**
3. Enter `https://github.com/solnera/ha-mcp-gateway` as the repository URL and select **Integration** as the category
4. Click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/mcp_gateway` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for **MCP Gateway** and follow the prompts

After setup, an **MCP Gateway** panel will appear in the sidebar.

## Providing MCP Tools from Your Integration

### Option 1: Platform Auto-discovery

Create an `mcp.py` file in your integration:

```python
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr, llm

async def async_get_device_tools(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> tuple[list[llm.Tool], str] | None:
    """Return MCP tools and prompt for a device."""
    tools = [MyTool()]
    prompt = "Control tools for this device."
    return tools, prompt
```

### Option 2: Manual Registration

```python
from custom_components.mcp_gateway.api import async_register_device_tools

async def async_setup_entry(hass, entry):
    device = dr.async_get(hass).async_get_or_create(...)
    unsub = await async_register_device_tools(
        hass,
        device_id=device.id,
        tools=[MyTool()],
        prompt="Device control tools.",
    )
    entry.async_on_unload(unsub)
```

## License

[MIT](LICENSE)
