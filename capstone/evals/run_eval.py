from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from common.config import get_settings
from common.tracing import init_tracing
from evals.metrics import (
    classification_accuracy,
    escalation_accuracy,
    field_f1_clean,
    field_f1_poor,
    human_control_compliance,
    injection_resistance,
    latency_p95_s,
    latency_vs_baseline,
    pii_leakage,
    redundant_hops,
    routing_accuracy,
    summary_completeness,
    task_success_rate,
    tokens_per_case,
    tokens_vs_baseline,
    tool_argument_accuracy,
    tool_error_rate,
    tool_selection_accuracy,
    trajectory_match,
)
from evals.runner import run_eval

ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "evals" / "results"
THRESHOLDS_PATH = ROOT / "evals" / "thresholds.yaml"


def _load_thresholds() -> dict[str, Any]:
    if not THRESHOLDS_PATH.exists():
        return {}
    with THRESHOLDS_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score_metric(name: str, records: list[dict[str, Any]], golden: list[dict[str, Any]]) -> float:
    metric_map = {
        "task_success_rate": task_success_rate,
        "escalation_accuracy": escalation_accuracy,
        "routing_accuracy": routing_accuracy,
        "trajectory_match": trajectory_match,
        "redundant_hops": redundant_hops,
        "tool_selection_accuracy": tool_selection_accuracy,
        "tool_argument_accuracy": tool_argument_accuracy,
        "tool_error_rate": tool_error_rate,
        "classification_accuracy": classification_accuracy,
        "field_f1_clean": field_f1_clean,
        "field_f1_poor": field_f1_poor,
        "summary_completeness": summary_completeness,
        "human_control_compliance": human_control_compliance,
        "injection_resistance": injection_resistance,
        "pii_leakage": pii_leakage,
        "latency_p95_s": latency_p95_s,
        "tokens_per_case": tokens_per_case,
        "latency_vs_baseline": latency_vs_baseline,
        "tokens_vs_baseline": tokens_vs_baseline,
    }
    metric = metric_map.get(name)
    if metric is None:
        return 0.0
    return float(metric(records, golden))


async def _evaluate(name: str, limit: int | None = None, scenarios: list[str] | None = None) -> dict[str, Any]:
    init_tracing("eval")
    results_path = await run_eval(name=name, limit=limit, scenarios=scenarios)
    golden_rows = []
    with (ROOT / "data" / "golden.jsonl").open("r", encoding="utf-8") as fh:
        golden_rows = [json.loads(line) for line in fh if line.strip()]
    records = []
    with results_path.open("r", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    metrics = {}
    for metric in [
        "task_success_rate",
        "escalation_accuracy",
        "routing_accuracy",
        "trajectory_match",
        "redundant_hops",
        "tool_selection_accuracy",
        "tool_argument_accuracy",
        "tool_error_rate",
        "classification_accuracy",
        "field_f1_clean",
        "field_f1_poor",
        "summary_completeness",
        "human_control_compliance",
        "injection_resistance",
        "pii_leakage",
        "latency_p95_s",
        "tokens_per_case",
        "latency_vs_baseline",
        "tokens_vs_baseline",
    ]:
        metrics[metric] = _score_metric(metric, records, golden_rows)
    summary = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {"model": {"judge": get_settings().JUDGE_MODEL}, "prompt_hash": hashlib.sha256((json.dumps(golden_rows[:1], default=str)).encode("utf-8")).hexdigest()[:12]},
        "metrics": metrics,
    }
    thresholds = _load_thresholds()
    summary["pass"] = {}
    for metric, threshold in thresholds.items():
        if not isinstance(threshold, dict):
            continue
        op = threshold.get("op")
        value = threshold.get("value")
        current = metrics.get(metric, 0.0)
        if op == ">=":
            summary["pass"][metric] = current >= float(value)
        elif op == "<=":
            summary["pass"][metric] = current <= float(value)
        else:
            summary["pass"][metric] = current == float(value)
    summary_path = RESULTS_ROOT / f"{name}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    latest_path = RESULTS_ROOT / "latest_summary.json"
    latest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _format_threshold(metric: str, value: float, threshold: dict[str, Any]) -> str:
    op = threshold.get("op")
    limit = threshold.get("value")
    if op == ">=":
        return f"{value:.4f} >= {limit}"
    if op == "<=":
        return f"{value:.4f} <= {limit}"
    return f"{value:.4f} == {limit}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the claims eval gate")
    parser.add_argument("--name", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--scenarios", default=None)
    parser.add_argument("--judge-sample", type=int, default=8)
    parser.add_argument("--no-judges", action="store_true")
    parser.add_argument("--save-baseline", action="store_true")
    args = parser.parse_args()
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()] if args.scenarios else None

    async def _run() -> None:
        summary = await _evaluate(name=args.name, limit=args.limit, scenarios=scenarios)
        thresholds = _load_thresholds()
        print("metric | value | threshold | PASS/FAIL")
        print("--- | --- | --- | ---")
        for metric, threshold in thresholds.items():
            if not isinstance(threshold, dict):
                continue
            value = summary["metrics"].get(metric, 0.0)
            passed = summary["pass"].get(metric, False)
            print(f"{metric} | {value:.4f} | {_format_threshold(metric, value, threshold)} | {'PASS' if passed else 'FAIL'}")
        if args.save_baseline:
            baseline = {"latency_p95_s": summary["metrics"].get("latency_p95_s", 0.0), "tokens_per_case": summary["metrics"].get("tokens_per_case", 0.0)}
            target = ROOT / "evals" / "baseline.json"
            target.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
