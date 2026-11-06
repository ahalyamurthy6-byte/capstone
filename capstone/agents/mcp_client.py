from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from common.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PORTS = {"case": 8001, "policy": 8002, "documents": 8003, "workflow": 8004}

_client: MultiServerMCPClient | None = None
_cached_tools: list[BaseTool] | None = None


def server_config() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    host = os.getenv("MCP_HOST", "localhost")
    mode = (settings.MCP_MODE or "http").lower()

    if mode == "http":
        urls = {
            "case": os.getenv("MCP_URL_CASE") or f"http://{host}:{SERVER_PORTS['case']}/mcp",
            "policy": os.getenv("MCP_URL_POLICY") or f"http://{host}:{SERVER_PORTS['policy']}/mcp",
            "documents": os.getenv("MCP_URL_DOCUMENTS") or f"http://{host}:{SERVER_PORTS['documents']}/mcp",
            "workflow": os.getenv("MCP_URL_WORKFLOW") or f"http://{host}:{SERVER_PORTS['workflow']}/mcp",
        }
        return {
            name: {"transport": "streamable_http", "url": urls[name]}
            for name in SERVER_PORTS
        }

    if mode == "stdio":
        return {
            name: {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", f"mcp_servers.{name}.server"],
                "cwd": str(PROJECT_ROOT),
                "env": {**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "MCP_TRANSPORT": "stdio"},
            }
            for name in SERVER_PORTS
        }

    raise ValueError(f"Unsupported MCP_MODE: {settings.MCP_MODE!r}")


def get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient(server_config())
    return _client


async def load_all_tools() -> list[BaseTool]:
    global _cached_tools
    tools = await get_client().get_tools()
    _cached_tools = list(tools)
    return _cached_tools


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                if "text" in part:
                    pieces.append(str(part["text"]))
            elif hasattr(part, "text"):
                pieces.append(str(part.text))
        return "".join(pieces)
    if hasattr(message, "text"):
        return str(message.text)
    return str(message)


async def get_prompt_text(server: str, name: str, args: dict[str, Any]) -> str:
    messages = await get_client().get_prompt(server, name, arguments=args)
    return "\n".join(_message_text(message) for message in messages)


async def read_resource_text(server: str, uri: str) -> str:
    blobs = await get_client().get_resources(server, uris=[uri])
    if not blobs:
        return ""
    return str(blobs[0].as_string())
