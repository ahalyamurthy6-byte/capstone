from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel

from common.llm import structured
from graph.guard import check_move, expected_next


class Route(BaseModel):
    next: Literal[
        "intake",
        "document_fanout",
        "summary",
        "routing",
        "sla_comms",
        "human_review",
        "await_documents",
        "manual_review",
    ]
    reason: str


async def supervisor(state: dict[str, Any]) -> Command:
    status = state.get("status") or "NEW"
    flags = state.get("flags") or {}
    stage_results = state.get("stage_results") or {}
    errors = state.get("errors") or []
    compact = {
        "status": status,
        "flags": flags,
        "stage_results": sorted(stage_results.keys()),
        "error_count": len(errors),
    }
    system_prompt = (
        "You choose the next workflow stage. Follow this order: intake -> document_fanout -> summary -> routing -> sla_comms -> human_review -> finalize -> notify_decision. "
        "Use expected_next state rules, avoid out-of-order moves, and pass through manual_review only for errors or low-confidence cases."
    )
    model = structured("mid", Route)
    try:
        route = await model.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=str(compact)),
            ]
        )
        route_obj = route if isinstance(route, Route) else Route.model_validate(route)
    except Exception:
        route_obj = Route(next=expected_next(state), reason="Default routing fallback")

    final, overridden = check_move(state, route_obj.next)
    route_record = {
        "status": status,
        "proposed": route_obj.next,
        "expected": expected_next(state),
        "final": final,
        "overridden": overridden,
        "reason": route_obj.reason,
    }
    update = {
        "next_step": final,
        "hops": int(state.get("hops", 0) or 0) + 1,
        "trajectory": ["supervisor"],
        "routes": [route_record],
        "stage_results": {
            "last_route": route_record,
        },
    }
    return Command(goto=final, update=update)
