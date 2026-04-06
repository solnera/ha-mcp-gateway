"""Shared fixtures for MCP Gateway tests.

Mocks modules unavailable in the installed HA version (2024.3) so that the
custom component code can be imported in the test environment.
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from dataclasses import dataclass as _dc
from dataclasses import field as _field
from types import ModuleType
from typing import Any as _Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components import http as _http_mod
from homeassistant.util import json as _json_mod

# ---------------------------------------------------------------------------
# Mock missing third-party and HA modules BEFORE any custom_components import
# ---------------------------------------------------------------------------


def _ensure_module(name: str, attrs: dict | None = None) -> ModuleType:
    """Create a mock module in sys.modules if it doesn't already exist."""
    if name in sys.modules:
        return sys.modules[name]
    mod = ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# homeassistant.helpers.llm


@_dc(kw_only=True)
class _MockAPI:
    hass: _Any = None
    id: str = ""
    name: str = ""


@_dc(kw_only=True)
class _MockAPIInstance:
    api: _Any = None
    api_prompt: str = ""
    llm_context: _Any = None
    tools: list = _field(default_factory=list)
    custom_serializer: _Any = None


class _MockTool:
    name: str = ""
    description: str = ""
    parameters: _Any = None


_mock_llm = _ensure_module(
    "homeassistant.helpers.llm",
    {
        "Tool": _MockTool,
        "API": _MockAPI,
        "APIInstance": _MockAPIInstance,
        "LLMContext": MagicMock,
        "ToolInput": MagicMock,
        "async_register_api": MagicMock(return_value=MagicMock()),
        "async_get_api": AsyncMock(),
    },
)

# homeassistant.components.http.StaticPathConfig
if not hasattr(_http_mod, "StaticPathConfig"):
    _http_mod.StaticPathConfig = type(
        "StaticPathConfig", (), {"__init__": lambda self, *a, **k: None}
    )

# homeassistant.util.json.JsonObjectType
if not hasattr(_json_mod, "JsonObjectType"):
    _json_mod.JsonObjectType = dict

# voluptuous_openapi
_ensure_module("voluptuous_openapi", {"convert": MagicMock(return_value={"properties": {}})})

# mcp and sub-modules (pydantic v2 conflict)
_mock_types = _ensure_module(
    "mcp.types",
    {
        "Tool": MagicMock,
        "Prompt": MagicMock,
        "PromptMessage": MagicMock,
        "GetPromptResult": MagicMock,
        "TextContent": MagicMock,
        "JSONRPCMessage": MagicMock,
    },
)
_ensure_module(
    "mcp",
    {
        "types": _mock_types,
        "JSONRPCRequest": MagicMock,
    },
)
_ensure_module("mcp.server", {"Server": MagicMock})
_ensure_module("mcp.shared", {})
_ensure_module("mcp.shared.message", {"SessionMessage": MagicMock})

# aiohttp_sse
_ensure_module("aiohttp_sse", {"sse_response": MagicMock})

# anyio sub-modules
_ensure_module("anyio", {"create_memory_object_stream": MagicMock, "create_task_group": MagicMock})
_ensure_module("anyio.streams", {})
_ensure_module(
    "anyio.streams.memory",
    {
        "MemoryObjectReceiveStream": MagicMock,
        "MemoryObjectSendStream": MagicMock,
    },
)


# ---------------------------------------------------------------------------
# Now safe to import from the custom component
# ---------------------------------------------------------------------------

from homeassistant.core import HomeAssistant  # noqa: E402

from custom_components.mcp_gateway.const import DOMAIN  # noqa: E402
from custom_components.mcp_gateway.types import DeviceDescription  # noqa: E402

# ---------------------------------------------------------------------------
# Config flow fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock async_setup_entry for config flow tests."""
    with patch(
        f"custom_components.{DOMAIN}.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Config entry fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def config_entry(hass: HomeAssistant):
    """Create and add a config entry to hass."""
    try:
        from pytest_homeassistant_custom_component.common import MockConfigEntry
    except ImportError:
        from unittest.mock import MagicMock

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.domain = DOMAIN
        entry.data = {}
        entry.title = "MCP Gateway"
        entry.async_on_unload = MagicMock()
        hass.config_entries._entries[entry.entry_id] = entry
        return entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MCP Gateway",
        data={},
        entry_id="test_entry",
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# Manager-related fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_zeroconf() -> Generator[MagicMock]:
    """Mock zeroconf instance and local IP detection."""
    mock_zc = MagicMock()
    mock_zc.register_service = MagicMock()
    mock_zc.unregister_service = MagicMock()
    with (
        patch(
            "custom_components.mcp_gateway.manager.async_get_instance",
            new_callable=AsyncMock,
            return_value=mock_zc,
        ),
        patch(
            "custom_components.mcp_gateway.manager._get_local_ip",
            return_value="192.168.1.100",
        ),
    ):
        yield mock_zc


@pytest.fixture
def mock_http_server() -> Generator[MagicMock]:
    """Mock MCPGatewayHttpServer."""
    with patch("custom_components.mcp_gateway.manager.MCPGatewayHttpServer") as mock_cls:
        instance = mock_cls.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        yield mock_cls


@pytest.fixture
def mock_llm_register() -> Generator[MagicMock]:
    """Mock llm.async_register_api."""
    unregister = MagicMock()
    with patch(
        "custom_components.mcp_gateway.manager.llm.async_register_api",
        return_value=unregister,
    ) as mock:
        mock.unregister = unregister
        yield mock


@pytest.fixture
async def manager(
    hass: HomeAssistant,
    mock_zeroconf,
    mock_http_server,
    mock_llm_register,
):
    """Create a fully mocked MCPGatewayManager."""
    from custom_components.mcp_gateway.manager import MCPGatewayManager  # noqa: E402

    mgr = MCPGatewayManager(hass)
    await mgr.async_setup()
    yield mgr
    await mgr.async_shutdown()


# ---------------------------------------------------------------------------
# LLM tool fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tools():
    """Create sample LLM tools for testing."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "A test tool"
    tool.parameters = {}
    return [tool]


@pytest.fixture
def sample_description() -> DeviceDescription:
    """Create a sample DeviceDescription."""
    return DeviceDescription(
        brand="TestBrand",
        model="TestModel",
        alias="Test Device",
        device_id="test_device_1",
    )


# ---------------------------------------------------------------------------
# Integration setup fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_integration_deps():
    """Mock all external dependencies for full integration setup."""
    with (
        patch("custom_components.mcp_gateway.MCPGatewayManager") as mock_manager_cls,
        patch("custom_components.mcp_gateway.MCPGatewayDiscovery") as mock_discovery_cls,
        patch("custom_components.mcp_gateway.async_register_websocket_commands"),
        patch(
            "custom_components.mcp_gateway.panel_custom.async_register_panel",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.mcp_gateway.integration_platform"
            ".async_process_integration_platforms",
            new_callable=AsyncMock,
        ),
    ):
        mock_manager = mock_manager_cls.return_value
        mock_manager.async_setup = AsyncMock()
        mock_manager.async_shutdown = AsyncMock()

        mock_discovery = mock_discovery_cls.return_value
        mock_discovery.async_setup = AsyncMock()
        mock_discovery.async_teardown = AsyncMock()

        yield {
            "manager_cls": mock_manager_cls,
            "manager": mock_manager,
            "discovery_cls": mock_discovery_cls,
            "discovery": mock_discovery,
        }
