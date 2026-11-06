from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from common.db import fetch_all

ROOT = Path(__file__).resolve().parents[1]


def _summarize_after(after: object) -> dict[str, object]:
    if not isinstance(after, dict):
        return {}
    payload = after.copy()
    if isinstance(payload.get("summary"), dict):
        return payload["summary"]
    if "status" in payload:
        return {"status": payload["status"]}
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit timeline and summary")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = fetch_all(
        """
        SELECT a.ts, a.actor, a.action, a.before, a.after, a.linked_checkpoint_id
        FROM audit_with_checkpoint a
        WHERE a.case_id = %s
        ORDER BY a.ts ASC
        """,
        (args.case_id,),
    )

    timeline = []
    for row in rows:
        after = row.get("after") or {}
        summary = _summarize_after(after)
        key_fields = {k: v for k, v in summary.items() if k in {"status", "kind", "decision", "approver_id", "due_at", "result"}}
        timeline.append({
            "ts": row.get("ts"),
            "actor": row.get("actor"),
            "action": row.get("action"),
            "after": key_fields,
            "linked_checkpoint_id": row.get("linked_checkpoint_id"),
        })

    if args.json:
        print(json.dumps({"timeline": timeline, "summary": {"counts_by_actor": dict(Counter(item["actor"] for item in timeline))}}, indent=2, default=str))
        return

    for item in timeline:
        fields = ", ".join(f"{k}={v}" for k, v in item["after"].items()) if item["after"] else "-"
        linked = item["linked_checkpoint_id"] or "-"
        print(f"{item['ts']} | {item['actor']} | {item['action']} | {fields} | {linked}")

    counts = Counter(item["actor"] for item in timeline)
    print("\nSummary: counts by actor")
    for actor, count in counts.most_common():
        print(f"- {actor}: {count}")
    approvals = [item for item in timeline if item["actor"] not in {"human", "supervisor"} and item["action"] in {"approve", "reject"}]
    print(f"Non-human approval actions: {'none' if not approvals else approvals[0]['action']}")
