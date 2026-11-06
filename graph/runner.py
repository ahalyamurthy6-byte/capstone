from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from common.config import get_settings
from common.ids import new_case_id
from graph.build import build_graph

DATABASE_URL = get_settings().DATABASE_URL


@asynccontextmanager
async def graph_session() -> AsyncIterator[Any]:
    async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as saver:
        await saver.setup()
        yield build_graph(saver)


def config_for(case_id: str, scenario_or_ui: str = "ui", tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload_tags = ["claims", scenario_or_ui]
    payload_tags.extend(tags or [])
    merged = {"case_id": case_id}
    if metadata:
        merged.update(metadata)
    return {
        "configurable": {"thread_id": case_id},
        "recursion_limit": 40,
        "metadata": merged,
        "tags": sorted(set(payload_tags)),
    }


async def start_case(graph: Any, claim: dict[str, Any], file_paths: list[str], scenario_or_ui: str = "ui", tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    case_id = new_case_id()
    started_at = time.perf_counter()
    input_state = {
        "case_id": case_id,
        "claim": claim,
        "file_paths": file_paths,
        "status": "NEW",
        "hops": 0,
    }
    config = config_for(case_id, scenario_or_ui=scenario_or_ui, tags=tags, metadata=metadata)
    async for event in graph.astream(input_state, config=config, stream_mode="updates"):
        print(json.dumps(event, default=str))
    snapshot = await graph.aget_state(config)
    values = snapshot.values if snapshot else {}
    ready_at = datetime.now(timezone.utc).isoformat()
    status = values.get("status") if values else None
    return {
        "case_id": case_id,
        "status": status,
        "ready_at": ready_at,
        "total_wall_time_s": round(time.perf_counter() - started_at, 3),
        "tags": config.get("tags"),
        "metadata": config.get("metadata"),
    }


async def resume_case(graph: Any, case_id: str, value: dict[str, Any], scenario_or_ui: str = "ui") -> None:
    config = config_for(case_id, scenario_or_ui=scenario_or_ui)
    async for event in graph.astream(Command(resume=value), config=config, stream_mode="updates"):
        print(json.dumps(event, default=str))


async def get_status(graph: Any, case_id: str) -> dict[str, Any]:
    config = config_for(case_id)
    snapshot = await graph.aget_state(config)
    interrupts = []
    for task in getattr(snapshot, "tasks", []) or []:
        interrupts.extend(getattr(task, "interrupts", []) or [])
    return {
        "status": snapshot.values.get("status") if snapshot.values else None,
        "next": snapshot.next,
        "interrupts": interrupts,
        "flags": snapshot.values.get("flags") if snapshot.values else {},
        "trajectory": snapshot.values.get("trajectory") if snapshot.values else [],
    }


async def history(graph: Any, case_id: str) -> list[dict[str, Any]]:
    config = config_for(case_id)
    rows: list[dict[str, Any]] = []
    async for state in graph.aget_state_history(config):
        rows.append(
            {
                "checkpoint_id": state.checkpoint_id,
                "step": state.step,
                "next": state.next,
                "status": state.values.get("status") if state.values else None,
                "created_at": getattr(state, "created_at", None),
            }
        )
    return rows


async def replay(graph: Any, case_id: str, checkpoint_id: str) -> None:
    config = {"configurable": {"thread_id": case_id, "checkpoint_id": checkpoint_id}, "recursion_limit": 40}
    async for event in graph.astream(None, config=config, stream_mode="updates"):
        print(json.dumps(event, default=str))
