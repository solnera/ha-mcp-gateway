"""MCP Gateway Manager.

Orchestrates per-device MCP server registrations, manages lifecycle,
port allocation, per-device HTTP servers, and mDNS advertisement.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm
from zeroconf import ServiceInfo

from .api import GetDescriptionTool, MCPGatewayAPI
from .const import DOMAIN, MDNS_SERVICE_TYPE, PORT_RANGE_END, PORT_RANGE_START
from .http import MCPGatewayHttpServer
from .session import SessionManager
from .store import MCPGatewayStore
from .types import DeviceDescription, MCPGatewayEntry

_LOGGER = logging.getLogger(__name__)


def _get_local_ip() -> str:
    """Get the primary local IP address for mDNS registration."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # Connect to a non-routable address to determine default interface
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class MCPGatewayManager:
    """Manages per-device MCP server registrations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self._entries: dict[str, MCPGatewayEntry] = {}
        self._servers: dict[str, MCPGatewayHttpServer] = {}
        self._mdns_infos: dict[str, ServiceInfo] = {}
        self._used_ports: set[int] = set()
        self.store = MCPGatewayStore(hass)
        self._unsub_device_event: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Set up the manager and listen for device events."""
        await self.store.async_load()
        self._unsub_device_event = self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            self._async_handle_device_event,
        )

    async def async_register(
        self,
        device_id: str,
        tools: list[llm.Tool],
        prompt: str | None,
        device_description: DeviceDescription | None = None,
    ) -> Callable[[], None]:
        """Register MCP tools for a device and start its HTTP server.

        Returns an unregister callable.
        """
        # Replace existing registration if present
        if device_id in self._entries:
            _LOGGER.debug("Replacing MCP tools for device %s", device_id)
            await self._async_unregister(device_id)

        # Build device description from registry if not provided
        if device_description is None:
            device_description = self._build_description_from_registry(device_id)

        # Add the get_description tool to the front of the tools list
        all_tools: list[llm.Tool] = [
            GetDescriptionTool(device_description),
            *tools,
        ]

        # Allocate a port
        port = self._allocate_port(device_id)

        # Create and register a device-scoped LLM API
        llm_api_id = f"{DOMAIN}_{device_id}"
        device_prompt = prompt or f"MCP tools for device {device_id}"
        api = MCPGatewayAPI(
            hass=self.hass,
            id=llm_api_id,
            name=f"MCP Gateway ({device_id})",
            device_tools=all_tools,
            device_prompt=device_prompt,
        )
        unregister_api = llm.async_register_api(self.hass, api)

        session_mgr = SessionManager()
        entry = MCPGatewayEntry(
            device_id=device_id,
            tools=all_tools,
            prompt=prompt,
            llm_api_id=llm_api_id,
            unregister_api=unregister_api,
            session_manager=session_mgr,
            port=port,
            device_description=device_description,
        )
        self._entries[device_id] = entry

        # Persist port assignment
        config = self.store.get_device_config(device_id)
        config["port"] = entry.port
        self.store.set_device_config(device_id, config)
        await self.store.async_save()

        # Start server only if device is enabled
        if config.get("enabled", True):
            await self._async_start_server(device_id, entry)
            await self._async_register_mdns(device_id, entry)

        _LOGGER.info(
            "Registered %d MCP tool(s) for device %s on port %d: %s",
            len(all_tools),
            device_id,
            entry.port,
            [t.name for t in all_tools],
        )

        @callback
        def unregister() -> None:
            """Unregister the device's MCP tools."""
            if device_id in self._entries:
                self.hass.async_create_task(self._async_unregister(device_id))

        return unregister

    async def _async_unregister(self, device_id: str) -> None:
        """Unregister a device's MCP tools, stop HTTP server and mDNS."""
        entry = self._entries.pop(device_id, None)
        if entry is None:
            return

        _LOGGER.info("Unregistering MCP tools for device %s", device_id)
        entry.unregister_api()
        entry.session_manager.close()
        self._used_ports.discard(entry.port)

        # Unregister mDNS
        await self._async_unregister_mdns(device_id)

        server = self._servers.pop(device_id, None)
        if server:
            await server.stop()

    async def async_shutdown(self) -> None:
        """Gracefully stop all HTTP servers, mDNS services, and clean up."""
        if self._unsub_device_event:
            self._unsub_device_event()
            self._unsub_device_event = None

        # Unregister all mDNS services
        if self._mdns_infos:
            await asyncio.gather(
                *(self._async_unregister_mdns(did) for did in list(self._mdns_infos)),
                return_exceptions=True,
            )

        # Stop all HTTP servers
        if self._servers:
            await asyncio.gather(
                *(s.stop() for s in self._servers.values()),
                return_exceptions=True,
            )
            self._servers.clear()

        # Then clean up all entries
        for entry in self._entries.values():
            entry.unregister_api()
            entry.session_manager.close()
        self._entries.clear()
        self._used_ports.clear()

    async def async_set_device_enabled(self, device_id: str, enabled: bool) -> None:
        """Enable or disable a device's MCP server."""
        entry = self._entries.get(device_id)
        if entry is None:
            return

        has_server = device_id in self._servers

        if enabled and not has_server:
            # Start server and mDNS
            await self._async_start_server(device_id, entry)
            await self._async_register_mdns(device_id, entry)
            _LOGGER.info("Enabled MCP server for device %s", device_id)
        elif not enabled and has_server:
            # Stop server and mDNS
            await self._async_unregister_mdns(device_id)
            server = self._servers.pop(device_id, None)
            if server:
                await server.stop()
            _LOGGER.info("Disabled MCP server for device %s", device_id)

    @callback
    def async_get_entry(self, device_id: str) -> MCPGatewayEntry | None:
        """Get the MCP entry for a device."""
        return self._entries.get(device_id)

    @callback
    def async_get_all_device_ids(self) -> list[str]:
        """Get all device IDs with registered MCP tools."""
        return list(self._entries.keys())

    # ------------------------------------------------------------------
    # Device description helpers
    # ------------------------------------------------------------------

    def _build_description_from_registry(self, device_id: str) -> DeviceDescription:
        """Build a DeviceDescription from the device registry."""
        dev_reg = dr.async_get(self.hass)
        device_entry = dev_reg.async_get(device_id)
        if device_entry:
            return DeviceDescription(
                alias=device_entry.name_by_user or device_entry.name,
                brand=device_entry.manufacturer,
                model=device_entry.model,
                device_id=device_id,
            )
        return DeviceDescription(device_id=device_id)

    # ------------------------------------------------------------------
    # mDNS registration
    # ------------------------------------------------------------------

    async def _async_register_mdns(self, device_id: str, entry: MCPGatewayEntry) -> None:
        """Register an mDNS service for a device's MCP server."""
        desc = entry.device_description
        service_name = (desc.alias if desc and desc.alias else None) or device_id

        local_ip = await self.hass.async_add_executor_job(_get_local_ip)
        info = ServiceInfo(
            type_=MDNS_SERVICE_TYPE,
            name=f"{service_name}.{MDNS_SERVICE_TYPE}",
            port=entry.port,
            properties={
                "endpoint": f"http://{local_ip}:{entry.port}/mcp/",
            },
            parsed_addresses=[local_ip],
        )

        try:
            zeroconf = await async_get_instance(self.hass)
            await self.hass.async_add_executor_job(zeroconf.register_service, info)
            self._mdns_infos[device_id] = info
            _LOGGER.info(
                "Registered mDNS service '%s' on port %d for device %s",
                service_name,
                entry.port,
                device_id,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to register mDNS for device %s",
                device_id,
                exc_info=True,
            )

    async def _async_unregister_mdns(self, device_id: str) -> None:
        """Unregister the mDNS service for a device."""
        info = self._mdns_infos.pop(device_id, None)
        if info is None:
            return

        try:
            zeroconf = await async_get_instance(self.hass)
            await self.hass.async_add_executor_job(zeroconf.unregister_service, info)
            _LOGGER.debug("Unregistered mDNS for device %s", device_id)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to unregister mDNS for device %s",
                device_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Port allocation
    # ------------------------------------------------------------------

    def _allocate_port(self, device_id: str) -> int:
        """Allocate a port for the device from the configured range."""
        # Try to reuse a previously persisted port
        config = self.store.get_device_config(device_id)
        if "port" in config:
            port = config["port"]
            if port not in self._used_ports:
                self._used_ports.add(port)
                return port

        # Find the next available port
        for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            if port not in self._used_ports:
                self._used_ports.add(port)
                return port

        raise HomeAssistantError(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")

    async def _async_start_server(self, device_id: str, entry: MCPGatewayEntry) -> None:
        """Start the HTTP server for a device, retrying once on port conflict."""
        server = MCPGatewayHttpServer(
            self.hass,
            device_id,
            entry.llm_api_id,
            entry.session_manager,
            entry.port,
        )
        try:
            await server.start()
        except OSError:
            _LOGGER.warning(
                "Port %d unavailable for device %s, allocating a new port",
                entry.port,
                device_id,
            )
            # Keep failed port in _used_ports so it won't be re-allocated
            new_port = self._allocate_port(device_id)
            entry.port = new_port
            server = MCPGatewayHttpServer(
                self.hass,
                device_id,
                entry.llm_api_id,
                entry.session_manager,
                new_port,
            )
            await server.start()

        self._servers[device_id] = server

    # ------------------------------------------------------------------
    # Device registry events
    # ------------------------------------------------------------------

    @callback
    def _async_handle_device_event(self, event: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        """Handle device registry events."""
        if event.data["action"] != "remove":
            return

        device_id = event.data["device_id"]
        if device_id in self._entries:
            _LOGGER.info(
                "Device %s removed from registry, unregistering MCP tools",
                device_id,
            )
            self.hass.async_create_task(self._async_remove_device(device_id))

    async def _async_remove_device(self, device_id: str) -> None:
        """Unregister MCP tools for a device and persist the change."""
        await self._async_unregister(device_id)
        self.store.remove_device(device_id)
        await self.store.async_save()
