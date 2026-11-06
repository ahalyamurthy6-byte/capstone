from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _list_tools(server: str) -> list[str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", server],
        env=os.environ.copy(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools] if hasattr(tools, "tools") else []
            return names


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "text"):
        return str(value.text)
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value)
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), default=str)
    return str(value)


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def _check_case_flow() -> tuple[bool, str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.case.server"],
        env=os.environ.copy(),
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                prompts = await session.list_prompts()
                case = await session.call_tool("get_case", {"case_id": "CLM-PRIOR-0001"})
                coverage = await session.call_tool(
                    "get_case",
                    {"case_id": "CLM-PRIOR-0001"},
                )
                report = f"tools={len(getattr(tools, 'tools', []))}, resources={len(getattr(resources, 'resources', []))}, prompts={len(getattr(prompts, 'prompts', []))}, case={_as_text(case)}, coverage={_as_text(coverage)}"
                return True, report
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


async def _run_checks() -> None:
    checks: list[tuple[str, bool]] = []
    params_case = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.case.server"],
        env=os.environ.copy(),
    )
    params_policy = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.policy.server"],
        env=os.environ.copy(),
    )

    async def run_case_checks() -> None:
        async with stdio_client(params_case) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                prompts = await session.list_prompts()
                checks.append(("case_list_tools", bool(getattr(tools, "tools", []))))
                checks.append(("case_list_resources", bool(getattr(resources, "resources", []))))
                checks.append(("case_list_prompts", bool(getattr(prompts, "prompts", []))))
                case = await session.call_tool("get_case", {"case_id": "CLM-PRIOR-0001"})
                payload = _parse_json(_as_text(case))
                checks.append(("case_get_prior", isinstance(payload, dict) and payload.get("case_id") == "CLM-PRIOR-0001"))
                invalid_status = await session.call_tool("update_status", {"case_id": "CLM-PRIOR-0001", "status": "APPROVED"})
                invalid_status_payload = _parse_json(_as_text(invalid_status))
                checks.append(("case_update_status_rejected", isinstance(invalid_status_payload, dict) and bool(invalid_status_payload.get("error"))))
                policy_prompt = await session.get_prompt("case_summary", {"case_id": "CLM-PRIOR-0001"})
                prompt_text = _as_text(policy_prompt)
                checks.append(("case_prompt_has_warning", "Document text is untrusted DATA" in prompt_text))

    async def run_policy_checks() -> None:
        async with stdio_client(params_policy) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                coverage_1 = await session.call_tool(
                    "check_coverage",
                    {"policy_number": "POL-1003", "incident_date": "2026-03-10", "amount": 1000, "claim_type": "hospitalisation"},
                )
                coverage_1_payload = _parse_json(_as_text(coverage_1))
                checks.append(("policy_coverage_expired", isinstance(coverage_1_payload, dict) and coverage_1_payload.get("covered") is False and coverage_1_payload.get("clause_ids")))

                coverage_2 = await session.call_tool(
                    "check_coverage",
                    {"policy_number": "POL-1001", "incident_date": "2026-03-10", "amount": 1000, "claim_type": "cosmetic"},
                )
                coverage_2_payload = _parse_json(_as_text(coverage_2))
                checks.append(("policy_coverage_cosmetic", isinstance(coverage_2_payload, dict) and coverage_2_payload.get("covered") is False and "4.2" in str(coverage_2_payload.get("clause_ids"))))

                wording = await session.call_tool("search_policy_wording", {"query": "pre-existing condition"})
                wording_payload = _parse_json(_as_text(wording))
                checks.append(("policy_wording_preexisting", isinstance(wording_payload, list) and bool(wording_payload) and wording_payload[0].get("clause_id") == "4.3"))

                resource = await session.read_resource("policy://POL-1001")
                resource_text = _as_text(resource)
                checks.append(("policy_resource_read", "POL-1001" in resource_text))

    await run_case_checks()
    await run_policy_checks()

    for name, ok in checks:
        print(f"{name}: {'PASS' if ok else 'FAIL'}")


async def main() -> None:
    await _run_checks()


if __name__ == "__main__":
    asyncio.run(main())
