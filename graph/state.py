from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def merge_dicts(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    return {**(a or {}), **(b or {})}


class ClaimState(TypedDict, total=False):
    case_id: str
    claim: dict[str, Any]
    file_paths: list[str]
    messages: Annotated[list, add_messages]
    status: str
    next_step: str
    hops: int
    stage_results: Annotated[dict[str, Any], merge_dicts]
    doc_results: Annotated[list[dict[str, Any]], operator.add]
    flags: Annotated[dict[str, Any], merge_dicts]
    human_decision: dict[str, Any] | None
    errors: Annotated[list[dict[str, Any]], operator.add]
    token_usage: Annotated[int, operator.add]
    trajectory: Annotated[list[str], operator.add]
    routes: Annotated[list[dict[str, Any]], operator.add]
    agent_runs: Annotated[list[dict[str, Any]], operator.add]
    comms_purpose: str | None
