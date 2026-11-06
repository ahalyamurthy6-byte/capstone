from __future__ import annotations

import asyncio
from typing import Any, Iterable

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import create_model

ALLOWED: dict[str, set[str]] = {
    "supervisor": {"get_case"},
    "intake": {"get_policy", "check_coverage", "find_similar_cases", "register_case", "attach_document", "get_case"},
    "document": {"list_documents", "extract_text", "classify_document", "extract_fields", "validate_case_documents"},
    "summary": {"get_case", "save_summary", "list_documents", "search_policy_wording"},
    "routing": {"get_workload", "assign_case", "request_approval", "get_case"},
    "sla_comms": {"schedule_sla", "send_notification", "request_documents", "get_case"},
}

FORBIDDEN_WORDS = ("approve", "reject", "settle", "finalize")


def _strip_actor_schema(schema: Any) -> Any:
    if schema is None:
        return None
    if hasattr(schema, "model_fields"):
        fields: dict[str, Any] = {}
        for name, field in schema.model_fields.items():
            if name == "actor":
                continue
            default = ... if field.is_required() else field.default
            fields[name] = (field.annotation, default)
        return create_model(f"{schema.__name__}NoActor", **fields)
    if isinstance(schema, dict):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields: dict[str, Any] = {}
        for name, spec in properties.items():
            if name == "actor":
                continue
            type_name = spec.get("type", "string") if isinstance(spec, dict) else "string"
            python_type: Any
            if type_name == "integer":
                python_type = int
            elif type_name == "number":
                python_type = float
            elif type_name == "boolean":
                python_type = bool
            else:
                python_type = str
            default = ... if name in required else None
            fields[name] = (python_type, default)
        return create_model(f"ToolArgsNoActor", **fields)
    return schema


def _wrap_tool(tool: BaseTool, agent: str) -> BaseTool:
    schema = getattr(tool, "args_schema", None)
    if schema is None:
        return tool
    if isinstance(schema, dict):
        if "actor" not in schema.get("properties", {}):
            return tool
    elif not hasattr(schema, "model_fields") or "actor" not in getattr(schema, "model_fields", {}):
        return tool

    schema = _strip_actor_schema(schema)

    def _sync_invoke(**kwargs: Any) -> Any:
        payload = {**kwargs, "actor": f"{agent}-agent"}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(tool.ainvoke(payload))
        return payload

    async def _invoke(**kwargs: Any) -> Any:
        payload = {**kwargs, "actor": f"{agent}-agent"}
        return await tool.ainvoke(payload)

    return StructuredTool(
        name=tool.name,
        description=tool.description or "",
        args_schema=schema,
        func=_sync_invoke,
        coroutine=_invoke,
    )


def tools_for(agent: str, all_tools: list[BaseTool]) -> list[BaseTool]:
    if agent not in ALLOWED:
        raise KeyError(f"Unknown agent: {agent}")

    available = {tool.name for tool in all_tools}
    allowed = ALLOWED[agent]
    missing = sorted(allowed - available)
    if missing:
        raise ValueError(f"Allowed tools missing from MCP tool list for {agent}: {missing}")

    wrapped: list[BaseTool] = []
    for tool in all_tools:
        if tool.name in allowed:
            wrapped.append(_wrap_tool(tool, agent))
    return wrapped


def assert_no_decision_tools(all_tools: Iterable[BaseTool]) -> None:
    forbidden = []
    for tool in all_tools:
        name = tool.name.lower()
        if any(word in name for word in FORBIDDEN_WORDS):
            forbidden.append(tool.name)
    if forbidden:
        raise ValueError(f"Decision-capable tool names are forbidden: {sorted(set(forbidden))}")
