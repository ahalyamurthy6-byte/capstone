from __future__ import annotations

import json
import os
from typing import Any

from langgraph.types import Command, Send, interrupt

from agents.mcp_client import load_all_tools
from agents.specialists import run_document, run_intake, run_routing, run_sla_comms, run_summary
from common.db import fetch_one
from common.decisions import record_decision
from graph.guard import expected_next


async def _tool_by_name(name: str, **kwargs: Any) -> Any:
    tools = await load_all_tools()
    tool = next((item for item in tools if item.name == name), None)
    if tool is None:
        raise ValueError(f"Tool not available: {name}")
    return await tool.ainvoke(kwargs)


async def intake(state: dict[str, Any]) -> dict[str, Any]:
    claim = dict((state.get("claim") or {}).copy())
    case_id = state.get("case_id")
    if case_id:
        claim["case_id"] = case_id
    result = await run_intake(claim, list(state.get("file_paths") or []))
    update: dict[str, Any] = {
        "trajectory": ["intake"],
        "token_usage": result.tokens,
        "stage_results": {"intake": result.output},
        "agent_runs": [{
            "name": "intake",
            "tool_calls": [item.get("name") for item in result.tool_calls],
            "tool_errors": result.tool_errors,
            "tokens": result.tokens,
            "error": result.error,
        }],
    }
    if result.error:
        update["errors"] = [{"stage": "intake", "error": result.error}]
        return update
    output = result.output or {}
    status = "REGISTERED"
    if output.get("duplicate_of") is not None:
        update.setdefault("flags", {})["duplicate"] = True
    if not output.get("covered", True):
        update.setdefault("flags", {})["out_of_policy"] = True
    update["status"] = status
    update["case_id"] = output.get("case_id") or case_id
    update["next_step"] = expected_next(update)
    return update


async def document_fanout(state: dict[str, Any]) -> Command:
    case_id = state.get("case_id")
    docs = await _tool_by_name("list_documents", case_id=case_id)
    items = docs if isinstance(docs, list) else []
    if not items:
        update = {
            "flags": {"missing_types": ["documents"]},
            "comms_purpose": "missing_docs",
            "next_step": "doc_join",
            "trajectory": ["document_fanout"],
        }
        return Command(goto="doc_join", update=update)
    sends = [Send("process_doc", {"case_id": case_id, "doc_id": item.get("doc_id")}) for item in items]
    return Command(goto=sends, update={"trajectory": ["document_fanout"]})


async def process_doc(inp: dict[str, Any]) -> dict[str, Any]:
    case_id = str(inp.get("case_id") or "")
    doc_id = str(inp.get("doc_id") or "")
    result = await run_document(case_id, doc_id)
    output = dict(result.output or {})
    doc_row = fetch_one("SELECT file_path FROM documents WHERE doc_id = %s", (doc_id,))
    if doc_row and doc_row.get("file_path"):
        output["filename"] = os.path.basename(str(doc_row.get("file_path")))
    update: dict[str, Any] = {
        "doc_results": [output],
        "trajectory": ["process_doc"],
        "token_usage": result.tokens,
        "agent_runs": [{
            "name": "process_doc",
            "tool_calls": [item.get("name") for item in result.tool_calls],
            "tool_errors": result.tool_errors,
            "tokens": result.tokens,
            "error": result.error,
            "filename": output.get("filename"),
        }],
    }
    if result.error:
        update["errors"] = [{"stage": "process_doc", "error": result.error}]
    return update


async def doc_join(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    validation = await _tool_by_name("validate_case_documents", case_id=case_id)
    payload = validation if isinstance(validation, dict) else {}
    flags = {}
    if payload.get("low_confidence_docs"):
        flags["low_confidence"] = True
    if payload.get("injection_docs"):
        flags["injection"] = True
    if payload.get("mismatches"):
        flags["mismatch"] = True
    if payload.get("missing_types"):
        flags["missing_types"] = payload["missing_types"]

    update: dict[str, Any] = {
        "flags": flags,
        "trajectory": ["doc_join"],
        "stage_results": {"validation": payload},
        "status": "DOCS_PROCESSED",
        "next_step": expected_next({**state, **{"status": "DOCS_PROCESSED", "flags": flags}}),
    }
    return update


async def summary(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    result = await run_summary(str(case_id))
    update: dict[str, Any] = {
        "trajectory": ["summary"],
        "token_usage": result.tokens,
        "stage_results": {"summary": result.output},
        "status": "SUMMARISED",
        "agent_runs": [{
            "name": "summary",
            "tool_calls": [item.get("name") for item in result.tool_calls],
            "tool_errors": result.tool_errors,
            "tokens": result.tokens,
            "error": result.error,
        }],
    }
    if result.error:
        update["errors"] = [{"stage": "summary", "error": result.error}]
        update["status"] = state.get("status")
    return update


async def routing(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    result = await run_routing(str(case_id))
    update: dict[str, Any] = {
        "trajectory": ["routing"],
        "token_usage": result.tokens,
        "stage_results": {"routing": result.output},
        "agent_runs": [{
            "name": "routing",
            "tool_calls": [item.get("name") for item in result.tool_calls],
            "tool_errors": result.tool_errors,
            "tokens": result.tokens,
            "error": result.error,
        }],
    }
    if result.error:
        update["errors"] = [{"stage": "routing", "error": result.error}]
        return update
    output = result.output or {}
    update["status"] = "AWAITING_APPROVAL" if output.get("approval_requested") else "ROUTED"
    return update


async def sla_comms(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    purpose = state.get("comms_purpose") or ("approval" if state.get("status") == "AWAITING_APPROVAL" else "missing_docs")
    missing = state.get("flags", {}).get("missing_types") or []
    approver_id = (state.get("stage_results") or {}).get("routing", {}).get("approver_id")
    result = await run_sla_comms(str(case_id), purpose, missing_types=list(missing) if isinstance(missing, list) else None, approver_id=approver_id)
    update: dict[str, Any] = {
        "trajectory": ["sla_comms"],
        "token_usage": result.tokens,
        "stage_results": {f"comms_{purpose}": True},
        "agent_runs": [{
            "name": "sla_comms",
            "tool_calls": [item.get("name") for item in result.tool_calls],
            "tool_errors": result.tool_errors,
            "tokens": result.tokens,
            "error": result.error,
        }],
    }
    if result.error:
        update["errors"] = [{"stage": "sla_comms", "error": result.error}]
        return update
    if purpose == "missing_docs":
        update["status"] = "AWAITING_DOCUMENTS"
    elif purpose == "approval":
        update["status"] = "AWAITING_APPROVAL"
    return update


async def human_review(state: dict[str, Any]) -> Command:
    payload = {
        "case_id": state.get("case_id"),
        "amount": (state.get("claim") or {}).get("amount"),
        "approver_id": (state.get("stage_results") or {}).get("routing", {}).get("approver_id"),
        "summary": (state.get("stage_results") or {}).get("summary", {}),
        "flags": state.get("flags") or {},
    }
    value = interrupt(payload)
    decision = str((value or {}).get("decision") or "").strip().lower()
    rationale = str((value or {}).get("rationale") or "").strip()
    approver_id = str((value or {}).get("approver_id") or payload["approver_id"] or "")
    if decision not in {"approve", "reject", "more_info"} or not rationale:
        return Command(goto="human_review", update={"errors": [{"stage": "human_review", "error": "Invalid human decision"}], "trajectory": ["human_review"]})

    staff = fetch_one("SELECT role, approval_limit FROM staff WHERE staff_id = %s", (approver_id,))
    amount = float((state.get("claim") or {}).get("amount") or 0)
    if not staff or str(staff.get("role") or "") != "approver":
        return Command(goto="human_review", update={"errors": [{"stage": "human_review", "error": "Approver role mismatch"}], "trajectory": ["human_review"]})
    if float(staff.get("approval_limit") or 0) < amount:
        return Command(goto="human_review", update={"errors": [{"stage": "human_review", "error": "Approver limit too low"}], "trajectory": ["human_review"]})

    update = {
        "human_decision": {"decision": decision, "rationale": rationale, "approver_id": approver_id},
        "trajectory": ["human_review"],
        "next_step": "finalize",
    }
    return Command(goto="finalize", update=update)


async def await_documents(state: dict[str, Any]) -> Command:
    payload = {"case_id": state.get("case_id"), "missing_types": state.get("flags", {}).get("missing_types", [])}
    value = interrupt(payload)
    file_paths = value.get("file_paths", []) if isinstance(value, dict) else []
    for file_path in file_paths:
        await _tool_by_name("attach_document", case_id=state.get("case_id"), file_path=file_path)
    return Command(
        goto="supervisor",
        update={
            "status": "REGISTERED",
            "flags": {"missing_types": []},
            "trajectory": ["await_documents"],
            "next_step": "supervisor",
        },
    )


async def finalize(state: dict[str, Any], config: dict[str, Any] | None = None) -> Command:
    decision = (state.get("human_decision") or {}).get("decision")
    rationale = (state.get("human_decision") or {}).get("rationale")
    approver_id = (state.get("human_decision") or {}).get("approver_id")
    if not decision or not rationale or not approver_id:
        return Command(goto="human_review", update={"errors": [{"stage": "finalize", "error": "Missing human decision"}]})

    checkpoint_id = None
    if config:
        configurable = config.get("configurable") or {}
        checkpoint_id = configurable.get("checkpoint_id")
    record_decision(state.get("case_id"), decision, rationale, approver_id, checkpoint_id)
    if decision == "more_info":
        return Command(goto="sla_comms", update={"comms_purpose": "missing_docs", "trajectory": ["finalize"], "next_step": "sla_comms"})
    return Command(goto="notify_decision", update={"trajectory": ["finalize"], "next_step": "notify_decision"})


async def notify_decision(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    result = await run_sla_comms(str(case_id), "decision")
    update: dict[str, Any] = {
        "trajectory": ["notify_decision"],
        "token_usage": result.tokens,
        "stage_results": {"decision_notice": result.output},
        "agent_runs": [{
            "name": "notify_decision",
            "tool_calls": [item.get("name") for item in result.tool_calls],
            "tool_errors": result.tool_errors,
            "tokens": result.tokens,
            "error": result.error,
        }],
    }
    if result.error:
        update["errors"] = [{"stage": "notify_decision", "error": result.error}]
    return update


async def manual_review(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    await _tool_by_name("update_status", case_id=case_id, status="MANUAL_REVIEW")
    await _tool_by_name("send_notification", case_id=case_id, to="SUP-1", subject="Manual review required", body="A claim requires manual review.")
    return {"status": "MANUAL_REVIEW", "trajectory": ["manual_review"], "next_step": "END"}
