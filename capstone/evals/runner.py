from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from common.db import fetch_all
from graph.runner import config_for, get_status, graph_session, start_case

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "claim_packs"
RESULTS_ROOT = ROOT / "evals" / "results"


def _load_pack_files(pack_id: str) -> tuple[dict[str, Any], list[str]]:
    for case_dir in sorted(PACK_ROOT.iterdir()):
        if not case_dir.is_dir():
            continue
        claim_path = case_dir / "claim.json"
        if not claim_path.exists():
            continue
        payload = json.loads(claim_path.read_text(encoding="utf-8"))
        if str(payload.get("pack_id") or case_dir.name) != pack_id:
            continue
        files = [
            str(path)
            for path in sorted(case_dir.iterdir())
            if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}
        ]
        return payload, files
    raise FileNotFoundError(f"No claim pack for {pack_id}")


def _mailpit_messages_for_case(case_id: str) -> list[dict[str, Any]]:
    try:
        with urllib.request.urlopen("http://localhost:8025/api/v1/messages") as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for message in messages:
        message_id = message.get("ID") or message.get("id")
        if not message_id:
            continue
        try:
            with urllib.request.urlopen(f"http://localhost:8025/api/v1/message/{message_id}") as resp:
                detail = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        body = str((detail.get("Content", {}) or {}).get("Text", "") or detail.get("Text", "") or "")
        subject = str((detail.get("Content", {}).get("Headers", {}) or {}).get("Subject", "") or detail.get("Subject", "") or "")
        context = f"{subject}\n{body}"
        if case_id in context:
            out.append(detail)
    return out


async def run_pack(pack: dict[str, Any]) -> dict[str, Any]:
    pack_id = str(pack.get("pack_id") or "")
    scenario = str(pack.get("scenario") or "")
    claim, files = _load_pack_files(pack_id)
    started = time.perf_counter()
    async with graph_session() as graph:
        meta = await start_case(
            graph,
            claim,
            files,
            scenario_or_ui="eval",
            tags=[scenario, "eval"],
            metadata={"pack_id": pack_id, "scenario": scenario},
        )
        case_id = str(meta["case_id"])
        status = await get_status(graph, case_id)
        snapshot = await graph.aget_state(config_for(case_id))
        values = snapshot.values if snapshot else {}
        elapsed = time.perf_counter() - started
        record = {
            "pack_id": pack_id,
            "scenario": scenario,
            "case_id": case_id,
            "final_status": (status.get("status") or values.get("status") or "UNKNOWN"),
            "flags": values.get("flags") or status.get("flags") or {},
            "stage_results": values.get("stage_results") or {},
            "doc_results": values.get("doc_results") or [],
            "routes": values.get("routes") or [],
            "agent_runs": values.get("agent_runs") or [],
            "trajectory": values.get("trajectory") or status.get("trajectory") or [],
            "token_usage": values.get("token_usage") or 0,
            "latency_s": round(elapsed, 3),
            "mail_messages": _mailpit_messages_for_case(case_id),
            "audit_rows": fetch_all("SELECT * FROM audit_log WHERE case_id = %s ORDER BY ts", (case_id,)),
        }
        return record


async def run_eval(name: str, limit: int | None = None, scenarios: list[str] | None = None) -> Path:
    results_path = RESULTS_ROOT / f"{name}.jsonl"
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    with (ROOT / "data" / "golden.jsonl").open("r", encoding="utf-8") as fh:
        packs = [json.loads(line) for line in fh if line.strip()]

    if scenarios:
        wanted = {item.lower() for item in scenarios}
        packs = [pack for pack in packs if str(pack.get("scenario", "")).lower() in wanted]

    if limit is not None and limit > 0:
        chosen: list[dict[str, Any]] = []
        seen = set()
        for pack in packs:
            scenario = str(pack.get("scenario", "")).lower()
            if scenario not in seen:
                chosen.append(pack)
                seen.add(scenario)
            if len(chosen) >= limit:
                break
        if len(chosen) < limit:
            remaining = [pack for pack in packs if pack not in chosen]
            for pack in remaining:
                if len(chosen) >= limit:
                    break
                chosen.append(pack)
        packs = chosen

    with results_path.open("w", encoding="utf-8") as fh:
        for pack in packs:
            try:
                result = await run_pack(pack)
            except Exception as exc:  # pragma: no cover - nonfatal for batch runs
                result = {"pack_id": pack.get("pack_id"), "scenario": pack.get("scenario"), "error": str(exc)}
            fh.write(json.dumps(result, default=str))
            fh.write("\n")
    return results_path
