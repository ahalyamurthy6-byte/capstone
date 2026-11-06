from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from common.tracing import init_tracing
from graph.runner import config_for, get_status, graph_session, history, replay, resume_case, start_case

init_tracing("cli")

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "claim_packs"


async def _load_pack(scenario: str) -> tuple[dict, list[str]]:
    for candidate in sorted(p.name for p in PACK_ROOT.iterdir() if p.is_dir()):
        claim_path = PACK_ROOT / candidate / "claim.json"
        if claim_path.exists():
            payload = json.loads(claim_path.read_text(encoding="utf-8"))
            if str(payload.get("scenario", "")).lower() == scenario.lower():
                files = [str(p) for p in (PACK_ROOT / candidate).glob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}]
                return payload, files
    raise FileNotFoundError(f"No pack for scenario: {scenario}")


async def cmd_start(args: argparse.Namespace) -> None:
    claim, files = await _load_pack(args.scenario)
    async with graph_session() as graph:
        started = await start_case(graph, claim, files)
        case_id = started["case_id"]
        status = await get_status(graph, case_id)
        print(json.dumps({"case_id": case_id, "ready_at": started.get("ready_at"), "status": status}, default=str))


async def cmd_status(args: argparse.Namespace) -> None:
    async with graph_session() as graph:
        status = await get_status(graph, args.case_id)
        print(json.dumps(status, default=str))


async def cmd_resume(args: argparse.Namespace) -> None:
    async with graph_session() as graph:
        await resume_case(graph, args.case_id, {"decision": args.decision, "rationale": args.rationale, "approver_id": args.approver})
        status = await get_status(graph, args.case_id)
        print(json.dumps(status, default=str))


async def cmd_docs(args: argparse.Namespace) -> None:
    async with graph_session() as graph:
        await resume_case(graph, args.case_id, {"file_paths": args.files})
        status = await get_status(graph, args.case_id)
        print(json.dumps(status, default=str))


async def cmd_history(args: argparse.Namespace) -> None:
    async with graph_session() as graph:
        rows = await history(graph, args.case_id)
        print(json.dumps(rows, default=str))


async def cmd_replay(args: argparse.Namespace) -> None:
    async with graph_session() as graph:
        await replay(graph, args.case_id, args.checkpoint_id)


async def cmd_demo(_args: argparse.Namespace) -> None:
    scenarios = ["clean", "mismatch", "poor_scan", "missing_docs"]
    for scenario in scenarios:
        claim, files = await _load_pack(scenario)
        async with graph_session() as graph:
            started = await start_case(graph, claim, files)
            print(f"scenario={scenario} case_id={started['case_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph claim workflow CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--scenario", required=True)
    start.set_defaults(func=cmd_start)

    status = sub.add_parser("status")
    status.add_argument("--case-id", required=True)
    status.set_defaults(func=cmd_status)

    resume = sub.add_parser("resume")
    resume.add_argument("--case-id", required=True)
    resume.add_argument("--decision", choices=["approve", "reject", "more_info"], required=True)
    resume.add_argument("--approver", required=True)
    resume.add_argument("--rationale", required=True)
    resume.set_defaults(func=cmd_resume)

    docs = sub.add_parser("docs")
    docs.add_argument("--case-id", required=True)
    docs.add_argument("--files", nargs="+")
    docs.set_defaults(func=cmd_docs)

    hist = sub.add_parser("history")
    hist.add_argument("--case-id", required=True)
    hist.set_defaults(func=cmd_history)

    replay_cmd = sub.add_parser("replay")
    replay_cmd.add_argument("--case-id", required=True)
    replay_cmd.add_argument("--checkpoint-id", required=True)
    replay_cmd.set_defaults(func=cmd_replay)

    demo = sub.add_parser("demo")
    demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
