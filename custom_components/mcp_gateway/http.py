"""Per-device standalone MCP Gateway HTTP servers.

Each registered device gets its own aiohttp server on a unique port,
serving the MCP protocol at /mcp (Streamable HTTP) and /sse (SSE).
"""

import asyncio
import logging
from dataclasses import dataclass
from http import HTTPStatus

import anyio
from aiohttp import web
from aiohttp_sse import sse_response
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from mcp import JSONRPCRequest, types
from mcp.server import Server
from mcp.shared.message import SessionMessage

from .const import CONTENT_TYPE_JSON, DOMAIN, MCP_PATH, SSE_PATH, TIMEOUT
from .server import create_device_server
from .session import Session, SessionManager

_LOGGER = logging.getLogger(__name__)


@dataclass
class _Streams:
    """Pairs of streams for MCP server communication."""

    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]
    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]


def _create_streams() -> _Streams:
    """Create a new pair of streams for MCP server communication."""
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)
    return _Streams(
        read_stream=read_stream,
        read_stream_writer=read_stream_writer,
        write_stream=write_stream,
        write_stream_reader=write_stream_reader,
    )


class MCPGatewayHttpServer:
    """Standalone HTTP server for a single device's MCP endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        llm_api_id: str,
        session_manager: SessionManager,
        port: int,
    ) -> None:
        """Initialize the per-device HTTP server."""
        self.hass = hass
        self.device_id = device_id
        self.llm_api_id = llm_api_id
        self.session_manager = session_manager
        self.port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        """Start listening on the assigned port."""
        app = web.Application()
        # Register both /mcp/ (spec default) and /mcp for compatibility
        app.router.add_post(MCP_PATH, self._handle_post)
        app.router.add_post(MCP_PATH.rstrip("/"), self._handle_post)
        app.router.add_get(SSE_PATH, self._handle_sse)
        app.router.add_post("/messages/{session_id}", self._handle_messages)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await self._site.start()
        _LOGGER.info(
            "MCP server for device %s started on port %d",
            self.device_id,
            self.port,
        )

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._runner = None
        self._site = None
        _LOGGER.info(
            "MCP server for device %s stopped (port %d)",
            self.device_id,
            self.port,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_server(self) -> tuple[Server, object]:
        """Create a fresh MCP server instance for this device."""
        llm_context = llm.LLMContext(
            platform=DOMAIN,
            context=Context(),
            language="*",
            assistant=None,
            device_id=self.device_id,
        )
        server = await create_device_server(self.hass, self.llm_api_id, llm_context)
        options = await self.hass.async_add_executor_job(server.create_initialization_options)
        return server, options

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    async def _handle_post(self, request: web.Request) -> web.Response:
        """Handle Streamable HTTP POST /mcp."""
        if CONTENT_TYPE_JSON not in request.headers.get("accept", ""):
            return web.Response(
                status=HTTPStatus.BAD_REQUEST,
                text=f"Client must accept {CONTENT_TYPE_JSON}",
            )
        if request.content_type != CONTENT_TYPE_JSON:
            return web.Response(
                status=HTTPStatus.BAD_REQUEST,
                text=f"Content-Type must be {CONTENT_TYPE_JSON}",
            )
        try:
            json_data = await request.json()
            message = types.JSONRPCMessage.model_validate(json_data)
        except ValueError:
            return web.Response(
                status=HTTPStatus.BAD_REQUEST,
                text="Request must be a JSON-RPC message",
            )

        # Notifications / responses: accept and discard
        if not isinstance(message.root, JSONRPCRequest):
            return web.Response(status=HTTPStatus.ACCEPTED)

        method = message.root.method
        _LOGGER.info(
            "Device %s: incoming request method=%s",
            self.device_id,
            method,
        )

        server, options = await self._create_server()
        streams = _create_streams()

        async def run_server() -> None:
            await server.run(
                streams.read_stream,
                streams.write_stream,
                options,
                stateless=True,
            )

        async with asyncio.timeout(TIMEOUT), anyio.create_task_group() as tg:
            tg.start_soon(run_server)
            await streams.read_stream_writer.send(SessionMessage(message))
            session_message = await anext(streams.write_stream_reader)
            tg.cancel_scope.cancel()

        _LOGGER.debug(
            "Device %s: response for method=%s: %s",
            self.device_id,
            method,
            session_message.message.model_dump_json(by_alias=True, exclude_none=True),
        )

        return web.json_response(
            data=session_message.message.model_dump(by_alias=True, exclude_none=True),
        )

    async def _handle_sse(self, request: web.Request) -> web.StreamResponse:
        """Handle SSE session establishment GET /sse."""
        _LOGGER.info("Device %s: SSE session requested", self.device_id)
        server, options = await self._create_server()
        streams = _create_streams()

        async with (
            sse_response(request) as response,
            self.session_manager.create(
                Session(
                    device_id=self.device_id,
                    read_stream_writer=streams.read_stream_writer,
                )
            ) as session_id,
        ):
            session_uri = f"/messages/{session_id}"
            _LOGGER.info(
                "Device %s: SSE session %s established",
                self.device_id,
                session_id,
            )
            await response.send(session_uri, event="endpoint")

            async def sse_reader() -> None:
                async for session_message in streams.write_stream_reader:
                    await response.send(
                        session_message.message.model_dump_json(by_alias=True, exclude_none=True),
                        event="message",
                    )

            async with anyio.create_task_group() as tg:
                tg.start_soon(sse_reader)
                await server.run(streams.read_stream, streams.write_stream, options)

            return response

    async def _handle_messages(self, request: web.Request) -> web.Response:
        """Handle SSE message posting POST /messages/{session_id}."""
        session_id = request.match_info["session_id"]
        session = self.session_manager.get(session_id)
        if session is None:
            _LOGGER.warning(
                "Device %s: message for unknown session %s",
                self.device_id,
                session_id,
            )
            return web.Response(
                status=HTTPStatus.NOT_FOUND,
                text=f"Could not find session ID '{session_id}'",
            )

        try:
            json_data = await request.json()
            message = types.JSONRPCMessage.model_validate(json_data)
        except ValueError:
            return web.Response(
                status=HTTPStatus.BAD_REQUEST,
                text="Could not parse message",
            )

        _LOGGER.debug(
            "Device %s: SSE message received on session %s",
            self.device_id,
            session_id,
        )
        await session.read_stream_writer.send(SessionMessage(message))
        return web.Response(status=HTTPStatus.OK)
