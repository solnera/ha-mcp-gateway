"""Constants for the MCP Gateway integration."""

DOMAIN = "mcp_gateway"
STORAGE_KEY = "mcp_gateway"
STORAGE_VERSION = 1

# Per-device standalone MCP server
MCP_PATH = "/mcp/"  # Trailing slash per MCP device integration spec
SSE_PATH = "/sse"
MESSAGES_PATH = "/messages/{session_id}"

PORT_RANGE_START = 20000
PORT_RANGE_END = 30000

TIMEOUT = 60  # Seconds

CONTENT_TYPE_JSON = "application/json"

# mDNS service type for device discovery
MDNS_SERVICE_TYPE = "_mcp._tcp.local."
