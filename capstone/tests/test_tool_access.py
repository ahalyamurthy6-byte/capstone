from __future__ import annotations

import socket

import pytest

from agents.tool_access import ALLOWED, assert_no_decision_tools, tools_for


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.asyncio
async def test_tool_access_filters_and_blocks_decisions() -> None:
    if not _port_open("localhost", 8001):
        pytest.skip("port 8001 is not reachable; MCP servers are not running")

    from agents.mcp_client import load_all_tools

    all_tools = await load_all_tools()
    for agent, names in ALLOWED.items():
        tool_names = {tool.name for tool in tools_for(agent, all_tools)}
        assert tool_names == names, f"{agent}: expected {names}, got {tool_names}"

    routing_tools = {tool.name for tool in tools_for("routing", all_tools)}
    assert "send_notification" not in routing_tools

    document_tools = {tool.name for tool in tools_for("document", all_tools)}
    assert "save_summary" not in document_tools

    intake_tools = {tool.name for tool in tools_for("intake", all_tools)}
    assert "request_approval" not in intake_tools

    assert_no_decision_tools(all_tools)

    with pytest.raises(KeyError):
        tools_for("unknown", all_tools)
