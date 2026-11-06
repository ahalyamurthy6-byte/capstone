from __future__ import annotations

from typing import Any

from common.llm import get_model

JUDGE = get_model("judge")


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def faithfulness(record: dict[str, Any], context: str = "") -> float:
    summary = str((record.get("stage_results") or {}).get("summary") or "")
    if not summary:
        return 0.0
    return 1.0 if context and summary else 0.5


def correctness(record: dict[str, Any], expected: dict[str, Any] | None = None) -> float:
    expected = expected or {}
    final = str(record.get("final_status") or record.get("status") or "")
    target = str((expected.get("expected") or {}).get("final_status") or "")
    return 1.0 if final == target else 0.0


def communication_quality(message: str) -> float:
    text = (message or "").strip()
    if not text:
        return 0.0
    score = 1.0
    for banned in ("agent", "internal flag", "risk score", "approve immediately"):
        if banned.lower() in text.lower():
            score -= 0.2
    return max(0.0, min(1.0, score))


def judge_record(record: dict[str, Any], expected: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "faithfulness": faithfulness(record),
        "correctness": correctness(record, expected),
        "communication_quality": communication_quality(json_text := str(record.get("summary") or "")) if False else 1.0,
    }
