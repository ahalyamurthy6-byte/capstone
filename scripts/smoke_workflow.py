from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]


def _load_pack(scenario: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.load_pack", "--scenario", scenario],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    for line in proc.stdout.strip().splitlines():
        if line.startswith("case_id="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"No case_id returned for {scenario}: {proc.stdout!r}")


def _parse_payload(result: object) -> object:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, (dict, list)):
        return structured
    content = getattr(result, "content", [])
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return text
            return payload
    return result


async def _call_workflow(tool_name: str, payload: dict[str, object]) -> object:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.workflow.server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool_name, payload)


async def _read_resource(uri: str) -> str:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.workflow.server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.read_resource(uri)
            return result.contents[0].text if getattr(result, "contents", None) else ""


async def _get_prompt(name: str, kwargs: dict[str, object]) -> str:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.workflow.server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            prompt = await session.get_prompt(name, kwargs)
            return getattr(prompt, "description", "") or str(prompt)


async def main() -> None:
    checks: list[tuple[str, bool]] = []

    case_a = _load_pack("clean")
    case_b = _load_pack("high_value")

    workload_result = await _call_workflow("get_workload", {"role": "approver"})
    workload_payload = _parse_payload(workload_result)
    checks.append(("approver_workload_count", isinstance(workload_payload, list) and len(workload_payload) == 3))

    assign_a = await _call_workflow("assign_case", {"case_id": case_a, "adjuster_id": "ADJ-1", "approver_id": "APR-1"})
    assign_a_payload = _parse_payload(assign_a)
    checks.append(("assign_case_a_ok", isinstance(assign_a_payload, dict) and bool(assign_a_payload.get("ok"))))

    assign_b_low = await _call_workflow("assign_case", {"case_id": case_b, "adjuster_id": "ADJ-1", "approver_id": "APR-1"})
    assign_b_low_payload = _parse_payload(assign_b_low)
    checks.append(("assign_case_b_limit_error", isinstance(assign_b_low_payload, dict) and "approval limit too low" in str(assign_b_low_payload.get("error", "")).lower()))

    assign_b = await _call_workflow("assign_case", {"case_id": case_b, "adjuster_id": "ADJ-2", "approver_id": "APR-3"})
    assign_b_payload = _parse_payload(assign_b)
    checks.append(("assign_case_b_ok", isinstance(assign_b_payload, dict) and bool(assign_b_payload.get("ok"))))

    request_approval_a = await _call_workflow("request_approval", {"case_id": case_a, "approver_id": "APR-1"})
    request_approval_a_payload = _parse_payload(request_approval_a)
    checks.append(("request_approval_a_ok", isinstance(request_approval_a_payload, dict) and bool(request_approval_a_payload.get("ok"))))

    from common.db import fetch_one

    case_state_a = fetch_one("SELECT status FROM cases WHERE case_id = %s", (case_a,))
    checks.append(("case_a_awaiting_approval", bool(case_state_a) and case_state_a.get("status") == "AWAITING_APPROVAL"))

    claimant_email = fetch_one("SELECT claimant_email FROM cases WHERE case_id = %s", (case_a,))
    send_ok = await _call_workflow("send_notification", {"case_id": case_a, "to": claimant_email["claimant_email"], "subject": "Test", "body": "Hello"})
    send_ok_payload = _parse_payload(send_ok)
    checks.append(("send_notification_claimant_ok", isinstance(send_ok_payload, dict) and bool(send_ok_payload.get("ok"))))

    send_block = await _call_workflow("send_notification", {"case_id": case_a, "to": "attacker@evil.com", "subject": "x", "body": "y"})
    send_block_payload = _parse_payload(send_block)
    checks.append(("send_notification_blocked", isinstance(send_block_payload, dict) and "recipient not allowed" in str(send_block_payload.get("error", "")).lower()))

    request_docs = await _call_workflow("request_documents", {"case_id": case_a, "missing_types": ["invoice"]})
    request_docs_payload = _parse_payload(request_docs)
    checks.append(("request_documents_ok", isinstance(request_docs_payload, dict) and bool(request_docs_payload.get("ok"))))

    schedule_b = await _call_workflow("schedule_sla", {"case_id": case_b, "kind": "approval", "hours": 0.0003})
    schedule_b_payload = _parse_payload(schedule_b)
    checks.append(("schedule_sla_ok", isinstance(schedule_b_payload, dict) and bool(schedule_b_payload.get("ok"))))

    approval_b = await _call_workflow("request_approval", {"case_id": case_b, "approver_id": "APR-3"})
    approval_b_payload = _parse_payload(approval_b)
    checks.append(("request_approval_b_ok", isinstance(approval_b_payload, dict) and bool(approval_b_payload.get("ok"))))

    time.sleep(3)
    from sla_worker.main import run_sla_job

    run_sla_job()

    with urllib.request.urlopen("http://localhost:8025/api/v1/messages", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    messages = payload.get("messages", payload if isinstance(payload, list) else [])
    subjects = [str(item.get("Subject", item.get("subject", ""))) for item in messages if isinstance(item, dict)]
    checks.append(("mailpit_has_sla_breach", len(messages) >= 3 and any(subject.startswith("SLA breach") for subject in subjects)))

    staff_json = await _read_resource("staff://directory")
    sla_json = await _read_resource("sla://rules")
    checks.append(("staff_resource_ok", "ADJ-1" in staff_json and "APR-3" in staff_json))
    checks.append(("sla_resource_ok", '"approval_hours": 24' in sla_json and '"documents_hours": 72' in sla_json))

    claimant_prompt = await _get_prompt("claimant_letter", {"case_id": case_a, "purpose": "missing_docs"})
    approver_prompt = await _get_prompt("approver_brief", {"case_id": case_a})
    checks.append(("claimant_prompt_ok", "missing documents" in claimant_prompt.lower()))
    checks.append(("approver_prompt_ok", "The decision is yours." in approver_prompt))

    for name, ok in checks:
        print(f"{name}: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
