from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from agents.specialists import run_document, run_intake, run_routing, run_sla_comms, run_summary

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "claim_packs"


def _load_pack(scenario: str) -> tuple[str, list[str], str]:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.load_pack", "--scenario", scenario],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    case_id = ""
    doc_ids: list[str] = []
    pack_id = ""
    for line in proc.stdout.splitlines():
        if line.startswith("case_id="):
            case_id = line.split("=", 1)[1].strip()
        elif line.startswith("doc_ids="):
            doc_ids = json.loads(line.split("=", 1)[1].strip())
    if not case_id:
        raise RuntimeError(f"No case_id found for scenario {scenario}")
    for candidate in sorted(p.name for p in PACK_ROOT.iterdir() if p.is_dir()):
        claim_path = PACK_ROOT / candidate / "claim.json"
        if claim_path.exists():
            payload = json.loads(claim_path.read_text(encoding="utf-8"))
            if str(payload.get("scenario", "")).lower() == scenario.lower():
                pack_id = candidate
                break
    if not pack_id:
        pack_id = case_id.replace("TEST-", "PACK-") if case_id.startswith("TEST-") else ""
    return case_id, doc_ids, pack_id


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a specialist agent against a claim scenario.")
    parser.add_argument("agent", choices=["intake", "document", "summary", "routing", "sla_comms"])
    parser.add_argument("--scenario", help="Scenario name to load from claim packs")
    parser.add_argument("--case-id")
    parser.add_argument("--doc-id")
    parser.add_argument("--purpose", choices=["approval", "missing_docs", "decision"])
    args = parser.parse_args()

    if args.agent == "intake":
        if args.scenario is None:
            raise SystemExit("--scenario is required for intake.")
        _, _, pack_id = _load_pack(args.scenario)
        claim_path = PACK_ROOT / pack_id / "claim.json"
        payload = json.loads(claim_path.read_text(encoding="utf-8"))
        result = await run_intake(payload, [str(p) for p in (PACK_ROOT / pack_id).glob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}])
        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
        return

    if args.case_id is None:
        if args.scenario is None:
            raise SystemExit("Provide --case-id or --scenario")
        case_id, doc_ids, _ = _load_pack(args.scenario)
    else:
        case_id = args.case_id
        doc_ids = []

    if args.agent == "document":
        doc_id = args.doc_id or (doc_ids[0] if doc_ids else "")
        if not doc_id:
            raise SystemExit("A document id is required for document agent runs")
        result = await run_document(case_id, doc_id)
    elif args.agent == "summary":
        result = await run_summary(case_id)
    elif args.agent == "routing":
        result = await run_routing(case_id)
    elif args.agent == "sla_comms":
        purpose = args.purpose or "missing_docs"
        result = await run_sla_comms(case_id, purpose, approver_id=args.case_id and None)
    else:
        raise SystemExit(f"Unsupported agent: {args.agent}")

    print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
