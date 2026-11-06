from __future__ import annotations

import json
import logging
import os
import smtplib
import sys
from datetime import datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Literal

from mcp.server.fastmcp import FastMCP

from common.audit import write_audit
from common.config import get_settings
from common.db import execute, fetch_all, fetch_one
from common.models import Ack, Case, StaffLoad, ToolError
from common.tracing import init_tracing

mcp = FastMCP(
    "workflow-mcp",
    host="0.0.0.0",
    port=int(os.getenv("MCP_PORT") or os.getenv("WORKFLOW_MCP_PORT") or os.getenv("WORKFLOW_PORT") or "8004"),
)


def _tool_error(error: str, hint: str | None = None) -> ToolError:
    return ToolError(error=error, hint=hint)


def _to_case(row: dict[str, object] | None) -> Case | None:
    if row is None:
        return None
    return Case.model_validate(row)


def _send_email(to_addr: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = "claims-bot@claims.local"
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.send_message(message)


def _allowed_recipients(case_id: str) -> set[str]:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    recipients = set()
    if case and case.claimant_email:
        recipients.add(str(case.claimant_email).strip().lower())
    for row in fetch_all("SELECT email FROM staff WHERE email IS NOT NULL"):
        recipients.add(str(row.get("email") or "").strip().lower())
    return recipients


def _build_claimant_email(case_id: str, purpose: Literal["missing_docs", "decision"]) -> str:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return ""
    if purpose == "missing_docs":
        return (
            f"Dear {case.claimant_name or 'claimant'},\n\n"
            "We need a few additional documents to continue your claim review. Please send the missing items listed below at your earliest convenience.\n\n"
            "Missing documents: invoice\n\n"
            "Please reply to this email with the requested documents. Thank you for your cooperation."
        )
    return (
        f"Dear {case.claimant_name or 'claimant'},\n\n"
        "We are reviewing your claim and would like to keep the process as clear as possible. Please confirm the information we already have and respond to any follow-up request promptly.\n\n"
        "We will keep our communication brief and focused on the information needed to complete your claim review."
    )


@mcp.tool()
def get_workload(role: Literal["adjuster", "approver", "supervisor"]) -> list[StaffLoad]:
    rows = fetch_all(
        """
        SELECT
            s.staff_id,
            s.name,
            s.role,
            s.approval_limit,
            COUNT(a.case_id) FILTER (
                WHERE c.case_id IS NOT NULL AND c.status NOT IN ('APPROVED', 'REJECTED')
            ) AS open_cases
        FROM staff s
        LEFT JOIN assignments a ON a.adjuster_id = s.staff_id OR a.approver_id = s.staff_id
        LEFT JOIN cases c ON c.case_id = a.case_id
        WHERE s.role = %s
        GROUP BY s.staff_id, s.name, s.role, s.approval_limit
        ORDER BY open_cases ASC, approval_limit ASC
        """,
        (role,),
    )
    return [StaffLoad.model_validate(row) for row in rows]


@mcp.tool()
def assign_case(case_id: str, adjuster_id: str, approver_id: str, actor: str = "agent") -> Ack | ToolError:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return _tool_error(f"Unknown case_id: {case_id}", "Use a valid claim from the cases table.")

    adjuster = fetch_one("SELECT * FROM staff WHERE staff_id = %s AND role = 'adjuster'", (adjuster_id,))
    approver = fetch_one("SELECT * FROM staff WHERE staff_id = %s AND role = 'approver'", (approver_id,))
    if adjuster is None:
        return _tool_error(f"Unknown adjuster_id: {adjuster_id}", "Use a staff member with the adjuster role.")
    if approver is None:
        return _tool_error(f"Unknown approver_id: {approver_id}", "Use a staff member with the approver role.")

    limit = Decimal(str((approver.get("approval_limit") or 0)))
    if limit < Decimal(str(case.amount or 0)):
        return _tool_error(
            "approval limit too low",
            f"choose an approver with approval_limit >= {case.amount}",
        )

    before = fetch_one("SELECT * FROM assignments WHERE case_id = %s", (case_id,))
    execute(
        """
        INSERT INTO assignments (case_id, adjuster_id, approver_id, assigned_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (case_id) DO UPDATE SET
            adjuster_id = EXCLUDED.adjuster_id,
            approver_id = EXCLUDED.approver_id,
            assigned_at = NOW()
        """,
        (case_id, adjuster_id, approver_id),
    )
    execute("UPDATE cases SET status = %s, updated_at = NOW() WHERE case_id = %s", ("ROUTED", case_id))
    after = fetch_one("SELECT * FROM assignments WHERE case_id = %s", (case_id,))
    updated = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    write_audit(case_id, actor, "assign_case", before={"assignment": before, "status": case.status}, after={"assignment": after, "status": updated.status if updated else None})
    return Ack(ok=True, message=f"Case {case_id} assigned to {adjuster_id}/{approver_id}")


@mcp.tool()
def request_approval(case_id: str, approver_id: str, actor: str = "agent") -> Ack | ToolError:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return _tool_error(f"Unknown case_id: {case_id}", "Use a valid claim from the cases table.")

    assignment = fetch_one("SELECT * FROM assignments WHERE case_id = %s", (case_id,))
    if assignment is None:
        return _tool_error(f"No assignment found for {case_id}", "Assign the case before requesting approval.")
    if str(assignment.get("approver_id") or "") != approver_id:
        return _tool_error(
            f"Approver {approver_id} was not assigned to case {case_id}",
            "Use the assigned approver for this case.",
        )

    pending = fetch_one(
        "SELECT * FROM approvals WHERE case_id = %s AND status = 'pending' ORDER BY requested_at DESC LIMIT 1",
        (case_id,),
    )
    if pending is not None:
        return Ack(ok=True, message="Approval request already pending")

    execute(
        "INSERT INTO approvals (case_id, approver_id, status, rationale, requested_at, decided_at) VALUES (%s, %s, 'pending', NULL, NOW(), NULL)",
        (case_id, approver_id),
    )
    execute("UPDATE cases SET status = %s, updated_at = NOW() WHERE case_id = %s", ("AWAITING_APPROVAL", case_id))
    updated = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    write_audit(case_id, actor, "request_approval", before={"status": case.status}, after={"status": updated.status if updated else None, "approver_id": approver_id})
    return Ack(ok=True, message=f"Approval requested for {case_id}")


@mcp.tool()
def schedule_sla(case_id: str, kind: Literal["approval", "documents"], hours: float, actor: str = "agent") -> Ack | ToolError:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return _tool_error(f"Unknown case_id: {case_id}", "Use a valid claim from the cases table.")

    execute(
        "INSERT INTO sla_timers (case_id, kind, due_at, breached) VALUES (%s, %s, NOW() + (%s * interval '1 hour'), false)",
        (case_id, kind, float(hours)),
    )
    write_audit(case_id, actor, "schedule_sla", before=None, after={"kind": kind, "hours": float(hours), "due_at": "now+hours"})
    return Ack(ok=True, message=f"SLA scheduled for {case_id}: {kind} in {hours} hours")


@mcp.tool()
def send_notification(case_id: str, to: str, subject: str, body: str, actor: str = "agent") -> Ack | ToolError:
    """Send a notification to the claimant, a staff member by staff_id, or a direct email address.

    Agents should pass either "claimant" or a staff_id so they never need to handle real email addresses.
    """
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return _tool_error(f"Unknown case_id: {case_id}", "Use a valid claim from the cases table.")

    target = str(to).strip()
    if target.lower() == "claimant":
        target = str(case.claimant_email or "").strip()
    elif target:
        staff = fetch_one("SELECT email FROM staff WHERE staff_id = %s", (target,))
        if staff and str(staff.get("email") or "").strip():
            target = str(staff.get("email") or "").strip()

    allowed = _allowed_recipients(case_id)
    if not target or target.lower() not in allowed:
        return _tool_error("recipient not allowed", "Use claimant, a staff_id, or a known staff email.")

    try:
        _send_email(target, subject, body)
    except Exception as exc:  # pragma: no cover
        return _tool_error("notification send failed", str(exc))

    execute(
        "INSERT INTO notifications (case_id, to_addr, subject, body, sent_at) VALUES (%s, %s, %s, %s, NOW())",
        (case_id, target, subject, body),
    )
    write_audit(case_id, actor, "send_notification", before=None, after={"to": target, "subject": subject})
    return Ack(ok=True, message=f"Notification sent to {target}")


@mcp.tool()
def request_documents(case_id: str, missing_types: list[str], actor: str = "agent") -> Ack | ToolError:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return _tool_error(f"Unknown case_id: {case_id}", "Use a valid claim from the cases table.")

    recipient = str(case.claimant_email or "").strip()
    if not recipient:
        return _tool_error("claimant email missing", "Add a claimant email before requesting documents.")

    items = ", ".join(str(item).strip() for item in missing_types if str(item).strip())
    body = _build_claimant_email(case_id, "missing_docs")
    if items:
        body = body.replace("Missing documents: invoice", f"Missing documents: {items}")
    try:
        _send_email(recipient, "Missing claim documents", body)
    except Exception as exc:  # pragma: no cover
        return _tool_error("document request failed", str(exc))

    execute(
        "INSERT INTO notifications (case_id, to_addr, subject, body, sent_at) VALUES (%s, %s, %s, %s, NOW())",
        (case_id, recipient, "Missing claim documents", body),
    )
    execute("UPDATE cases SET status = %s, updated_at = NOW() WHERE case_id = %s", ("AWAITING_DOCUMENTS", case_id))
    execute(
        "INSERT INTO sla_timers (case_id, kind, due_at, breached) VALUES (%s, 'documents', NOW() + interval '72 hours', false)",
        (case_id,),
    )
    updated = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    write_audit(case_id, actor, "request_documents", before={"status": case.status}, after={"status": updated.status if updated else None, "missing_types": missing_types})
    return Ack(ok=True, message=f"Document request sent for {case_id}")


@mcp.resource("staff://directory")
def read_staff_directory() -> str:
    rows = fetch_all("SELECT staff_id, name, role, approval_limit FROM staff ORDER BY role, staff_id")
    return json.dumps(rows, default=str)


@mcp.resource("sla://rules")
def read_sla_rules() -> str:
    payload = {"approval_hours": 24, "documents_hours": 72, "escalate_to_role": "supervisor"}
    return json.dumps(payload, default=str)


@mcp.prompt()
def claimant_letter(case_id: str, purpose: Literal["missing_docs", "decision"]) -> str:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    case_line = f"Claim: {case.case_id} ({case.claimant_name})" if case else f"Claim: {case_id}"
    if purpose == "missing_docs":
        return (
            f"Write a short, clear, polite letter to the claimant for {case_line}. "
            "Ask for the missing documents needed to continue the claim. "
            "Never mention internal flags, risk scores, fraud suspicion or agent names. "
            "Do not promise any outcome or timing beyond the SLA. "
            "Keep it plain text and under 150 words."
        )
    return (
        f"Write a short, clear, polite letter to the claimant for {case_line}. "
        "Explain the decision or next step in plain language. "
        "Never mention internal flags, risk scores, fraud suspicion or agent names. "
        "Do not promise any outcome or timing beyond the SLA. "
        "Keep it plain text and under 150 words."
    )


@mcp.prompt()
def approver_brief(case_id: str) -> str:
    case = _to_case(fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,)))
    if case is None:
        return f"No case found for {case_id}."
    return (
        f"Write a concise brief for the approver on claim {case_id}. "
        f"Include claim amount, policy, key facts, risks with clause ids, missing information, and recommended next action. "
        "The decision is yours."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
