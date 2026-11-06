from __future__ import annotations

import os

from common.config import get_settings

_TRACING_READY = False


def init_tracing(service: str) -> None:
    global _TRACING_READY
    if os.getenv("TRACING", "on").lower() in {"off", "false", "0", "no"}:
        return
    if _TRACING_READY:
        return

    settings = get_settings()
    try:
        from phoenix.otel import register
    except Exception:
        return

    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except Exception:
        LangChainInstrumentor = None

    try:
        from openinference.instrumentation.mcp import MCPInstrumentor
    except Exception:
        MCPInstrumentor = None

    try:
        tracer_provider = register(
            project_name="claims-agent",
            endpoint=f"{settings.PHOENIX_ENDPOINT}/v1/traces",
            auto_instrument=False,
            set_global_tracer_provider=True,
        )
        if LangChainInstrumentor is not None:
            LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        if MCPInstrumentor is not None:
            MCPInstrumentor().instrument(tracer_provider=tracer_provider)
        _TRACING_READY = True
    except Exception:
        _TRACING_READY = True
