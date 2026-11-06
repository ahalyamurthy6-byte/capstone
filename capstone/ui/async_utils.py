from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from typing import Any


def run(coro: Awaitable[Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Any = None
    error: Exception | None = None

    def _runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - Streamlit worker fallback
            error = exc

    worker = threading.Thread(target=_runner)
    worker.start()
    worker.join()
    if error is not None:
        raise error
    return result
