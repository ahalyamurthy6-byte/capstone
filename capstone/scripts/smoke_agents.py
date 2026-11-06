from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from agents.specialists import run_document, run_intake, run_routing, run_sla_comms, run_summary
from agents.tool_access import ALLOWED, assert_no_decision_tools, tools_for
from agents.mcp_client import load_all_tools

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "claim_packs"
SCENARIOS = ["clean", "poor_scan", "missing_docs", "duplicate", "prompt_injection"]


def _pack_for_scenario(scenario: str) -> str:
    for candidate in sorted(p.name for p in PACK_ROOT.iterdir() if p.is_dir()):
        claim_path = PACK_ROOT / candidate / "claim.json"
        if claim_path.exists():
            payload = json.loads(claim_path.read_text(encoding="utf-8"))
            if str(payload.get("scenario", "")).lower() == scenario.lower():
                return candidate
    raise FileNotFoundError(f"No claim pack found for scenario: {scenario}")


def _load_pack(scenario: str) -> tuple[str, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.load_pack", "--scenario", scenario],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    case_id = ""
    doc_ids: list[str] = []
    for line in proc.stdout.splitlines():
        if line.startswith("case_id="):
            case_id = line.split("=", 1)[1].strip()
        elif line.startswith("doc_ids="):
            doc_ids = json.loads(line.split("=", 1)[1].strip())
    if not case_id:
        raise RuntimeError(f"No case_id returned for scenario {scenario}")
    return case_id, doc_ids


async def _assert_tool_names(agent_name: str, run_result: object) -> None:
    tool_names = {item["name"] for item in getattr(run_result, "tool_calls", []) if isinstance(item, dict) and "name" in item}
    allowed = ALLOWED.get(agent_name, set())
    missing = [name for name in tool_names if name not in allowed]
    if missing:
        raise AssertionError(f"{agent_name} used forbidden tools: {missing}")


async def _mailpit_count() -> int:
    try:
        with urllib.request.urlopen("http://localhost:8025/api/v1/messages", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return 0
    if isinstance(payload, dict):
        msgs = payload.get("messages") or payload.get("items") or []
        return len(msgs) if isinstance(msgs, list) else 0
    if isinstance(payload, list):
        return len(payload)
    return 0


async def main() -> None:
    all_tools = await load_all_tools()
    assert_no_decision_tools(all_tools)
    total_tokens = 0
    results: list[tuple[str, str, bool, int]] = []

    for scenario in SCENARIOS:
        case_id, doc_ids = _load_pack(scenario)
        pack_id = _pack_for_scenario(scenario)
        claim_path = PACK_ROOT / pack_id / "claim.json"
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        file_paths = [str(p) for p in (PACK_ROOT / pack_id).glob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}]

        intake_run = await run_intake(claim, file_paths)
        await _assert_tool_names("intake", intake_run)
        duplicate_expected = scenario == "duplicate"
        duplicate_value = bool((intake_run.output or {}).get("duplicate_of"))
        results.append(("intake", scenario, duplicate_value == duplicate_expected, intake_run.tokens))
        total_tokens += intake_run.tokens

        for doc_id in doc_ids:
            doc_run = await run_document(case_id, doc_id)
            await _assert_tool_names("document", doc_run)
            doc_payload = doc_run.output or {}
            if scenario == "poor_scan":
                if doc_payload.get("ocr_confidence", 0.0) < 0.6:
                    ok = True
                else:
                    ok = False
            elif scenario == "prompt_injection":
                ok = bool(doc_payload.get("injection_flag"))
            else:
                ok = True
            results.append(("document", f"{scenario}:{doc_id}", ok, doc_run.tokens))
            total_tokens += doc_run.tokens

        if scenario in {"clean", "prompt_injection"}:
            summary_run = await run_summary(case_id)
            await _assert_tool_names("summary", summary_run)
            risks = (summary_run.output or {}).get("risks", [])
            risk_ok = bool(risks) and all(str(item.get("clause_id") or "").strip() for item in risks)
            if scenario == "prompt_injection":
                risk_ok = risk_ok and any("injection" in str(item.get("text", "")).lower() for item in risks)
            results.append(("summary", scenario, risk_ok, summary_run.tokens))
            total_tokens += summary_run.tokens

        if scenario == "clean":
            routing_run = await run_routing(case_id)
            await _assert_tool_names("routing", routing_run)
            results.append(("routing", scenario, bool((routing_run.output or {}).get("approver_id")), routing_run.tokens))
            total_tokens += routing_run.tokens

        if scenario == "missing_docs":
            before_count = await _mailpit_count()
            sla_run = await run_sla_comms(case_id, "missing_docs", missing_types=["invoice", "medical_report"], approver_id="APR-1")
            await _assert_tool_names("sla_comms", sla_run)
            after_count = await _mailpit_count()
            results.append(("sla_comms", scenario, after_count > before_count, sla_run.tokens))
            total_tokens += sla_run.tokens

    print(f"{'agent':<12} {'scenario':<20} {'result':<6} {'tokens':>8}")
    for agent_name, scenario_name, passed, tokens_used in results:
        print(f"{agent_name:<12} {scenario_name:<20} {'PASS' if passed else 'FAIL':<6} {tokens_used:>8}")
    print(f"TOTAL TOKENS: {total_tokens}")

    failed = [row for row in results if not row[2]]
    if failed:
        print(f"FAIL: {len(failed)} checks failed")
        raise SystemExit(1)
    print("PASS: smoke_agents checks succeeded")


if __name__ == "__main__":
    asyncio.run(main())
