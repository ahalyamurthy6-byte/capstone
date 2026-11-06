from __future__ import annotations

import os
import sys

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_no_decision_tools() -> None:
    for module in [
        "mcp_servers.case.server",
        "mcp_servers.policy.server",
        "mcp_servers.documents.server",
        "mcp_servers.workflow.server",
    ]:
        params = StdioServerParameters(command=sys.executable, args=["-m", module], env=os.environ.copy())
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [tool.name.lower() for tool in tools.tools]
                forbidden = {"approve", "reject", "settle", "finalize"}
                assert not any(name in forbidden for name in names), f"Sensitive tool names unexpectedly present in {module}: {names}"
                assert not any("approve" in name or "reject" in name or "settle" in name or "finalize" in name for name in names), names

    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.case.server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("update_status", {"case_id": "CLM-PRIOR-0001", "status": "APPROVED"})
            payload = result.structuredContent if hasattr(result, "structuredContent") else result.content[0].text
            text = payload if isinstance(payload, str) else str(payload)
            assert "error" in text.lower() or "unsupported status" in text.lower(), f"APPROVED status should be rejected: {result}"
