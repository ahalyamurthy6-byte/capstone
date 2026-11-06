from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ["clean", "poor_scan", "prompt_injection", "missing_docs", "mismatch"]


def _payload(result: object) -> dict[str, object]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", [])
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _load_pack(scenario: str) -> tuple[str, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.load_pack", "--scenario", scenario],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    case_id = None
    doc_ids: list[str] = []
    for line in proc.stdout.strip().splitlines():
        if line.startswith("case_id="):
            case_id = line.split("=", 1)[1].strip()
        elif line.startswith("doc_ids="):
            doc_ids = ast.literal_eval(line.split("=", 1)[1].strip())
    if case_id is None:
        raise RuntimeError(f"No case_id returned for scenario {scenario}: {proc.stdout!r}")
    return case_id, doc_ids


async def _check_case(case_id: str, doc_ids: list[str]) -> tuple[bool, list[dict[str, object]]]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.documents.server"],
        env=os.environ.copy(),
    )
    results: list[dict[str, object]] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for doc_id in doc_ids:
                text = await session.call_tool("extract_text", {"case_id": case_id, "doc_id": doc_id})
                payload = _payload(text)
                classification = await session.call_tool("classify_document", {"case_id": case_id, "doc_id": doc_id})
                class_payload = _payload(classification)
                fields = await session.call_tool("extract_fields", {"case_id": case_id, "doc_id": doc_id})
                fields_payload = _payload(fields)
                validation = await session.call_tool("validate_case_documents", {"case_id": case_id})
                validation_payload = _payload(validation)
                results.append(
                    {
                        "doc": doc_id,
                        "type": class_payload.get("doc_type"),
                        "confidence": payload.get("ocr_confidence", 0),
                        "injection": payload.get("injection_flag", False),
                        "fields_ok": bool(fields_payload.get("claimant_name") or fields_payload.get("amount") or fields_payload.get("policy_number")),
                        "validation": validation_payload,
                    }
                )
    ok = all(bool(item["validation"].get("ok")) for item in results) if results else False
    return ok, results


def main() -> None:
    for scenario in SCENARIOS:
        case_id, doc_ids = _load_pack(scenario)
        ok, rows = asyncio.run(_check_case(case_id, doc_ids))
        validation = rows[0]["validation"] if rows else {}
        print(f"{scenario:15} | {'doc':<18} | {'type':<12} | {'confidence':>9} | {'injection':>9} | {'fields_ok':>9}")
        for row in rows:
            doc = str(row["doc"])
            doc_type = str(row["type"] or "")
            confidence = float(row["confidence"] or 0.0)
            injection = bool(row["injection"])
            fields_ok = bool(row["fields_ok"])
            print(f"{scenario:15} | {doc:<18} | {doc_type:<12} | {confidence:>9.2f} | {str(injection):>9} | {str(fields_ok):>9}")

        if scenario == "clean":
            assert ok is True, f"clean scenario unexpectedly invalid: {validation}"
        elif scenario == "poor_scan":
            assert bool(validation.get("low_confidence_docs")), f"poor_scan missing low_confidence_docs: {validation}"
        elif scenario == "prompt_injection":
            assert bool(validation.get("injection_docs")), f"prompt_injection missing injection_docs: {validation}"
        elif scenario == "missing_docs":
            assert "invoice" in validation.get("missing_types", []), f"missing_docs missing invoice: {validation}"
        elif scenario == "mismatch":
            assert validation.get("mismatches"), f"mismatch missing mismatches: {validation}"

        print(f"{scenario}: {'PASS' if (scenario == 'clean' and ok) or (scenario == 'poor_scan' and validation.get('low_confidence_docs')) or (scenario == 'prompt_injection' and validation.get('injection_docs')) or (scenario == 'missing_docs' and 'invoice' in validation.get('missing_types', [])) or (scenario == 'mismatch' and validation.get('mismatches')) else 'FAIL'}")


if __name__ == "__main__":
    main()
