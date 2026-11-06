from __future__ import annotations

from langchain_core.tools import StructuredTool

from agents.tool_access import tools_for


def _tool(name: str):
    def _run(query: str, actor: str = "agent"):
        return {"query": query, "actor": actor}

    return StructuredTool.from_function(
        func=_run,
        name=name,
        description="test tool",
        args_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "actor": {"type": "string"}},
            "required": ["query", "actor"],
        },
    )


def test_tools_for_wraps_actor_field() -> None:
    tool = _tool("get_case")
    wrapped = tools_for("supervisor", [tool])
    assert wrapped[0].name == "get_case"
    assert "actor" not in wrapped[0].args_schema.model_fields

    result = wrapped[0].invoke({"query": "abc", "actor": "evil-agent"})
    assert result == {"query": "abc", "actor": "supervisor-agent"}
