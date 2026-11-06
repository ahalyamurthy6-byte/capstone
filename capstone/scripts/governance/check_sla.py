from __future__ import annotations

import asyncio
import json
import time
import urllib.request

from common.db import execute, fetch_all
from graph.runner import get_status, graph_session, start_case
from sla_worker.main import run_sla_job


def _mail_subjects() -> list[str]:
    try:
        with urllib.request.urlopen("http://localhost:8025/api/v1/messages") as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    out: list[str] = []
    for message in messages:
        message_id = message.get("ID") or message.get("id")
        if not message_id:
            continue
        try:
            with urllib.request.urlopen(f"http://localhost:8025/api/v1/message/{message_id}") as resp:
                detail = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        headers = detail.get("Content", {}).get("Headers", {}) if isinstance(detail, dict) else {}
        subject = headers.get("Subject") or headers.get("subject") or detail.get("Subject") or detail.get("subject") or ""
        out.append(str(subject))
    return out


async def _run() -> tuple[bool, list[str]]:
    claim = {
        "policy_number": "POL-1001",
        "claimant_name": "Sample User",
        "claimant_email": "sample@example.com",
        "incident_date": "2026-09-01",
        "claim_type": "hospitalisation",
        "amount": 1500.0,
        "description": "SLA test claim",
    }
    async with graph_session() as graph:
        started = await start_case(graph, claim, [], scenario_or_ui="cli")
        case_id = started["case_id"]
        status = await get_status(graph, case_id)
        if status.get("status") == "AWAITING_APPROVAL":
            execute("UPDATE sla_timers SET due_at = NOW() - INTERVAL '1 minute' WHERE case_id = %s AND kind = 'approval'", (case_id,))
        else:
            execute("INSERT INTO sla_timers (case_id, kind, due_at, breached) VALUES (%s, 'approval', NOW() - INTERVAL '1 minute', false)", (case_id,))
        run_sla_job()
        deadline = time.time() + 10
        found_mail = False
        while time.time() < deadline:
            subjects = _mail_subjects()
            if any(f"SLA breach: {case_id}" in subject for subject in subjects):
                found_mail = True
                break
            time.sleep(0.5)
        rows = fetch_all("SELECT actor, action FROM audit_log WHERE case_id = %s AND action = 'sla_breach' AND actor = 'sla-worker'", (case_id,))
        return found_mail and bool(rows), ["sla breach not observed in Mailpit or audit log"] if not (found_mail and rows) else []


def main() -> None:
    ok, failed = asyncio.run(_run())
    print("PASS" if ok else "FAIL")
    for item in failed:
        print(f"  - {item}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
