from __future__ import annotations

from pydantic import BaseModel
from langchain_core.tools import tool

from common.llm import get_embeddings, get_model, structured


class Ping(BaseModel):
    ok: bool
    reason: str


@tool
def add(a: int, b: int) -> int:
    return a + b


def check_invoke() -> bool:
    result = get_model("small").invoke("Reply with OK")
    text = str(getattr(result, "content", result)).upper()
    return "OK" in text


def check_structured() -> bool:
    llm = structured("small", Ping)
    result = llm.invoke("Check whether the LLM is healthy.")
    return isinstance(result, Ping) and isinstance(result.ok, bool)


def check_tools() -> bool:
    tool_calls = get_model("small").bind_tools([add]).invoke("Add 2 and 3").tool_calls
    return bool(tool_calls)


def check_embeddings() -> bool:
    vector = get_embeddings().embed_query("ping")
    return len(vector) == 768


def main() -> None:
    results = [
        ("plain invoke", check_invoke()),
        ("structured output", check_structured()),
        ("tool calling", check_tools()),
        ("embedding length", check_embeddings()),
    ]
    for name, ok in results:
        print(f"{name}: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
