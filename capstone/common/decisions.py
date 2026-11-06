from __future__ import annotations

from typing import Literal

from common.audit import write_audit
from common.db import execute, fetch_one


def record_decision(
    case_id: str,
    decision: Literal["approve", "reject", "more_info"],
    rationale: str,
    approver_id: str,
    checkpoint_id: str | None = None,
) -> None:
    case = fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,))
    if case is None:
        raise ValueError(f"Unknown case_id: {case_id}")

    status_map = {
        "approve": "APPROVED",
        "reject": "REJECTED",
        "more_info": "MORE_INFO",
    }
    approval_status_map = {
        "approve": "approved",
        "reject": "rejected",
        "more_info": "more_info",
    }

    pending = fetch_one(
        "SELECT * FROM approvals WHERE case_id = %s AND status = 'pending' ORDER BY requested_at DESC LIMIT 1",
        (case_id,),
    )
    before = pending.copy() if pending else None

    normalized = status_map[decision]
    approval_status = approval_status_map[decision]

    if pending is not None:
        execute(
            "UPDATE approvals SET status = %s, rationale = %s, decided_at = NOW() WHERE id = %s",
            (approval_status, rationale, pending["id"]),
        )
    else:
        execute(
            "INSERT INTO approvals (case_id, approver_id, status, rationale, requested_at, decided_at) VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (case_id, approver_id, approval_status, rationale),
        )

    execute("UPDATE cases SET status = %s, updated_at = NOW() WHERE case_id = %s", (normalized, case_id))
    updated_case = fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,))
    write_audit(
        case_id,
        approver_id,
        "human_decision",
        before=before,
        after=updated_case,
        checkpoint_id=checkpoint_id,
    )
