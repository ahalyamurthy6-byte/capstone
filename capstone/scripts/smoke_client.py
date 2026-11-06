from __future__ import annotations

import asyncio
import contextlib
import io
import re
import socket
import sys
import time
from collections import defaultdict

from agents.mcp_client import get_prompt_text, load_all_tools, read_resource_text
from agents.tool_access import ALLOWED, assert_no_decision_tools, tools_for
from scripts.load_pack import main as load_pack_main


async def _server_ready(host: str = "localhost", port: int = 8001, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _invoke(tool_map: dict[str, object], name: str, payload: dict) -> object:
    tool = tool_map[name]
    if hasattr(tool, "ainvoke"):
        return await tool.ainvoke(payload)
    return tool(payload)


async def main() -> int:
    if not await _server_ready():
        print("MCP servers are not running. Start them with ./scripts/run_servers.sh")
        return 1

    all_tools = await load_all_tools()
    grouped: dict[str, list[str]] = defaultdict(list)
    for agent_name in ALLOWED:
        grouped[agent_name] = [tool.name for tool in tools_for(agent_name, all_tools)]

    for agent_name, names in grouped.items():
        print(f"{agent_name}: {', '.join(names)}")

    assert_no_decision_tools(all_tools)

    stdout = io.StringIO()
    argv = sys.argv[:]
    try:
        sys.argv = ["load_pack.py", "--scenario", "clean"]
        with contextlib.redirect_stdout(stdout):
            load_pack_main()
    finally:
        sys.argv = argv

    output = stdout.getvalue().strip()
    match = re.search(r"case_id=(TEST-[A-Za-z0-9-]+)", output)
    if not match:
        print("FAIL: load_pack --scenario clean did not return a case_id")
        return 1
    case_id = match.group(1)
    print(f"case_id={case_id}")

    tool_map = {tool.name: tool for tool in all_tools}
    checks: list[tuple[str, object, str]] = []

    async def run_check(label: str, fn, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
            elapsed = time.perf_counter() - start
            ok = bool(result)
            print(f"{label}: {elapsed:.3f}s -> {'PASS' if ok else 'FAIL'}")
            checks.append((label, result, "PASS" if ok else "FAIL"))
        except Exception as exc:  # pragma: no cover - smoke output only
            elapsed = time.perf_counter() - start
            print(f"{label}: {elapsed:.3f}s -> FAIL ({exc})")
            checks.append((label, exc, "FAIL"))

    await run_check("get_case", _invoke, tool_map, "get_case", {"case_id": case_id})
    await run_check(
        "search_policy_wording",
        _invoke,
        tool_map,
        "search_policy_wording",
        {"query": "cosmetic procedures", "k": 4},
    )
    await run_check("list_documents", _invoke, tool_map, "list_documents", {"case_id": case_id})
    await run_check("resource_case", read_resource_text, "case", f"case://{case_id}")
    await run_check("resource_timeline", read_resource_text, "case", f"case://{case_id}/timeline")
    await run_check("prompt_case_summary", get_prompt_text, "case", "case_summary", {"case_id": case_id})
    await run_check("prompt_claimant_letter", get_prompt_text, "workflow", "claimant_letter", {"case_id": case_id, "purpose": "missing_docs"})

    for label, value, status in checks:
        if status == "FAIL":
            print(f"FAIL: {label}")
            return 1

    print("PASS: all smoke checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
