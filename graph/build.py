from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import RetryPolicy

from graph.nodes import (
    await_documents,
    doc_join,
    document_fanout,
    finalize,
    human_review,
    intake,
    manual_review,
    notify_decision,
    process_doc,
    routing,
    sla_comms,
    summary,
)
from graph.state import ClaimState
from graph.supervisor import supervisor


def build_graph(checkpointer: Any) -> Any:
    builder = StateGraph(ClaimState)

    builder.add_node("supervisor", supervisor)
    builder.add_node("intake", intake, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("document_fanout", document_fanout)
    builder.add_node("process_doc", process_doc, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("doc_join", doc_join)
    builder.add_node("summary", summary, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("routing", routing, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("sla_comms", sla_comms, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("human_review", human_review)
    builder.add_node("await_documents", await_documents)
    builder.add_node("finalize", finalize)
    builder.add_node("notify_decision", notify_decision)
    builder.add_node("manual_review", manual_review)

    builder.set_entry_point("supervisor")
    builder.add_edge("intake", "supervisor")
    builder.add_edge("doc_join", "supervisor")
    builder.add_edge("summary", "supervisor")
    builder.add_edge("routing", "supervisor")
    builder.add_edge("sla_comms", "supervisor")
    builder.add_edge("process_doc", "doc_join")
    builder.add_edge("notify_decision", END)
    builder.add_edge("manual_review", END)

    return builder.compile(checkpointer=checkpointer)
