from __future__ import annotations

from langchain.agents.middleware import (
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)


def build_middleware() -> list[object]:
    return [
        PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_tool_results=True),
        PIIMiddleware("member_id", detector=r"\bM\d{8}\b", strategy="redact", apply_to_input=True, apply_to_tool_results=True),
        PIIMiddleware("ssn", detector=r"\b\d{3}-\d{2}-\d{4}\b", strategy="redact", apply_to_input=True, apply_to_tool_results=True),
        ToolCallLimitMiddleware(run_limit=10),
        ToolRetryMiddleware(max_retries=2),
    ]
