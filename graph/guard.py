from __future__ import annotations

from typing import Any

NODES = [
    "intake",
    "document_fanout",
    "summary",
    "routing",
    "sla_comms",
    "human_review",
    "await_documents",
    "manual_review",
]


def expected_next(state: dict[str, Any]) -> str:
    errors = state.get("errors") or []
    if len(errors) >= 2 or int(state.get("hops", 0) or 0) > 15:
        return "manual_review"

    status = str(state.get("status") or "NEW")
    flags = state.get("flags") or {}

    if status == "NEW":
        return "intake"
    if status == "REGISTERED":
        return "document_fanout"
    if status == "DOCS_PROCESSED":
        if flags.get("low_confidence"):
            return "manual_review"
        if flags.get("missing_types"):
            return "sla_comms"
        return "summary"
    if status == "AWAITING_DOCUMENTS":
        return "await_documents"
    if status == "DOCS_VALIDATED":
        return "summary"
    if status == "SUMMARISED":
        return "routing"
    if status == "AWAITING_APPROVAL":
        stage_results = state.get("stage_results") or {}
        if stage_results.get("comms_approval") is True:
            return "human_review"
        return "sla_comms"
    if status == "MANUAL_REVIEW":
        return "manual_review"
    return "manual_review"


def allowed_moves(state: dict[str, Any]) -> set[str]:
    return {expected_next(state), "manual_review"}


def check_move(state: dict[str, Any], proposed: str) -> tuple[str, bool]:
    allowed = allowed_moves(state)
    if proposed in allowed:
        return proposed, False
    expected = expected_next(state)
    return expected, True
