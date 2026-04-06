"""Platform discovery for MCP Gateway tools.

Discovers integrations that provide an `mcp.py` module with
`async_get_device_tools(hass, config_entry, device_entry)`.
When a device is created or updated in the device registry,
automatically calls the provider and registers tools.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm

from .types import DeviceDescription

_LOGGER = logging.getLogger(__name__)

# Platform return type: (tools, prompt) or (tools, prompt, description)
PlatformResult: TypeAlias = (  # noqa: UP040
    tuple[list[llm.Tool], str] | tuple[list[llm.Tool], str, DeviceDescription] | None
)


class MCPGatewayPlatformProtocol(Protocol):
    """Protocol for mcp.py platform modules."""

    async def async_get_device_tools(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_entry: dr.DeviceEntry,
    ) -> PlatformResult:
        """Return MCP tools, prompt, and optional description for a device."""
        ...


class MCPGatewayDiscovery:
    """Discovers and manages MCP platform providers."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize discovery."""
        self.hass = hass
        self._platforms: dict[str, Any] = {}  # domain -> mcp module
        self._unsub_device_event: Callable[[], None] | None = None
        self._unsub_started_event: Callable[[], None] | None = None
        self._auto_unsubs: dict[str, Callable[[], None]] = {}  # device_id -> unsub

    @callback
    def async_register_platform(self, hass: HomeAssistant, domain: str, platform: Any) -> None:
        """Register a discovered mcp.py platform module."""
        if not hasattr(platform, "async_get_device_tools"):
            _LOGGER.warning(
                "Integration %s has mcp.py but missing async_get_device_tools",
                domain,
            )
            return

        self._platforms[domain] = platform
        _LOGGER.info("Discovered MCP platform for integration: %s", domain)

        # Process existing devices for this integration
        hass.async_create_task(self._async_process_existing_devices(domain))

    async def async_setup(self) -> None:
        """Start listening for device registry events."""
        self._unsub_device_event = self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            self._async_handle_device_event,
        )
        # Re-scan all platforms after HA is fully started, because
        # async_get_device_tools may depend on data populated during
        # async_setup_entry which runs after EVENT_COMPONENT_LOADED.
        if self.hass.state is CoreState.not_running:
            self._unsub_started_event = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                self._async_handle_started,
            )

    @callback
    def async_teardown(self) -> None:
        """Clean up listeners and auto-registered tools."""
        if self._unsub_device_event:
            self._unsub_device_event()
            self._unsub_device_event = None

        if self._unsub_started_event:
            self._unsub_started_event()
            self._unsub_started_event = None

        for unsub in self._auto_unsubs.values():
            unsub()
        self._auto_unsubs.clear()

    async def _async_handle_started(self, _event: Event) -> None:
        """Re-scan all platforms after HA is fully started."""
        self._unsub_started_event = None
        for domain in list(self._platforms):
            await self._async_process_existing_devices(domain)

    async def _async_process_existing_devices(self, domain: str) -> None:
        """Process all existing devices for a newly discovered platform."""
        dev_reg = dr.async_get(self.hass)
        for device_entry in dev_reg.devices.values():
            if any(ident[0] == domain for ident in device_entry.identifiers):
                await self._async_register_device(device_entry)

    async def _async_handle_device_event(
        self, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle device registry create/remove events."""
        action = event.data["action"]
        device_id = event.data["device_id"]

        if action == "create":
            dev_reg = dr.async_get(self.hass)
            device_entry = dev_reg.async_get(device_id)
            if device_entry:
                await self._async_register_device(device_entry)
        elif action == "remove":
            self._async_unregister_device(device_id)

    async def _async_register_device(self, device_entry: dr.DeviceEntry) -> None:
        """Try to register MCP tools for a device."""
        if device_entry.id in self._auto_unsubs:
            return  # Already registered

        # Find which integration owns this device
        domain = self._find_domain(device_entry)
        if domain is None or domain not in self._platforms:
            return

        platform = self._platforms[domain]

        # Find the config entry for this device
        config_entry = self._find_config_entry(device_entry, domain)
        if config_entry is None:
            return

        try:
            result = await platform.async_get_device_tools(self.hass, config_entry, device_entry)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Error getting MCP tools from %s for device %s",
                domain,
                device_entry.id,
                exc_info=True,
            )
            return

        if result is None:
            return

        # Support both 2-tuple (tools, prompt) and 3-tuple (tools, prompt, description)
        device_description: DeviceDescription | None = None
        if len(result) == 3:
            tools, prompt, device_description = result
        else:
            tools, prompt = result

        if not tools:
            return

        # Import here to avoid circular dependency
        from .const import DOMAIN  # noqa: PLC0415
        from .manager import MCPGatewayManager  # noqa: PLC0415

        manager: MCPGatewayManager = self.hass.data[DOMAIN]
        unsub = await manager.async_register(device_entry.id, tools, prompt, device_description)
        self._auto_unsubs[device_entry.id] = unsub

        _LOGGER.debug(
            "Auto-registered %d MCP tools for device %s (via %s)",
            len(tools),
            device_entry.id,
            domain,
        )

    @callback
    def _async_unregister_device(self, device_id: str) -> None:
        """Unregister auto-discovered MCP tools for a device."""
        unsub = self._auto_unsubs.pop(device_id, None)
        if unsub:
            unsub()

    def _find_domain(self, device_entry: dr.DeviceEntry) -> str | None:
        """Find the integration domain that owns a device."""
        for identifier in device_entry.identifiers:
            domain = identifier[0]
            if domain in self._platforms:
                return domain
        return None

    def _find_config_entry(self, device_entry: dr.DeviceEntry, domain: str) -> ConfigEntry | None:
        """Find the config entry for a device."""
        for entry_id in device_entry.config_entries:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == domain:
                return entry
        return None
