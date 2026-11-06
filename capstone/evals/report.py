from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "evals" / "results"
GOLDEN_PATH = ROOT / "data" / "golden.jsonl"
OUTPUT_PATH = ROOT / "docs" / "evaluation_report.md"

METRIC_GROUPS = {
    "Outcome": [
        "task_success_rate",
        "escalation_accuracy",
        "routing_accuracy",
        "trajectory_match",
        "summary_completeness",
        "human_control_compliance",
    ],
    "Tooling": [
        "tool_selection_accuracy",
        "tool_argument_accuracy",
        "tool_error_rate",
        "redundant_hops",
    ],
    "Quality": [
        "classification_accuracy",
        "field_f1_clean",
        "field_f1_poor",
        "correctness",
        "communication_quality",
        "faithfulness",
    ],
    "Safety": [
        "injection_resistance",
        "pii_leakage",
    ],
    "Efficiency": [
        "latency_p95_s",
        "latency_vs_baseline",
        "tokens_per_case",
        "tokens_vs_baseline",
    ],
}


def _find_summary(name: str) -> Path:
    target = RESULTS_ROOT / f"{name}_summary.json"
    if target.exists():
        return target
    latest = RESULTS_ROOT / "latest_summary.json"
    if latest.exists():
        return latest
    raise FileNotFoundError(f"No summary found for {name!r} under {RESULTS_ROOT}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _metric_value(summary: dict[str, Any], metric: str) -> float:
    metrics = summary.get("metrics") or {}
    value = metrics.get(metric)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_metric(value: float) -> str:
    if abs(value) < 1:
        return f"{value:.3f}"
    return f"{value:.3f}"


def _format_threshold(metric: str, value: float, threshold: Any) -> str:
    if isinstance(threshold, dict):
        op = threshold.get("op")
        limit = threshold.get("value")
        if op == ">=":
            return f"{value:.3f} >= {float(limit):.3f}"
        if op == "<=":
            return f"{value:.3f} <= {float(limit):.3f}"
        return f"{value:.3f} == {float(limit):.3f}"
    return str(value)


def _pass_label(summary: dict[str, Any], metric: str, threshold: Any) -> str:
    if not isinstance(threshold, dict):
        return "n/a"
    value = _metric_value(summary, metric)
    op = threshold.get("op")
    limit = float(threshold.get("value") or 0.0)
    if op == ">=":
        return "PASS" if value >= limit else "FAIL"
    if op == "<=":
        return "PASS" if value <= limit else "FAIL"
    return "PASS" if value == limit else "FAIL"


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def _build_setup_summary() -> str:
    model_cfg = json.loads((ROOT / "evals" / "thresholds.yaml").read_text(encoding="utf-8")) if (ROOT / "evals" / "thresholds.yaml").exists() else {}
    judge_model = "ollama:llama3.1:8b"
    small_model = "ollama:qwen2.5:3b"
    pack_count = _line_count(GOLDEN_PATH)
    return (
        f"- Models: small={small_model}, judge={judge_model}\n"
        f"- Golden packs: {pack_count}\n"
        f"- Judge family: ollama / llama3.1\n"
        f"- Thresholds: {len(model_cfg)} tracked metrics"
    )


def _collect_metric_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    thresholds_path = ROOT / "evals" / "thresholds.yaml"
    if thresholds_path.exists():
        import yaml

        thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8")) or {}
    else:
        thresholds = {}

    rows: list[dict[str, str]] = []
    for group_name, metric_names in METRIC_GROUPS.items():
        for metric in metric_names:
            value = _metric_value(summary, metric)
            threshold = thresholds.get(metric)
            status = _pass_label(summary, metric, threshold)
            rows.append(
                {
                    "area": group_name,
                    "metric": metric,
                    "value": _format_metric(value),
                    "threshold": _format_threshold(metric, value, threshold) if threshold else "-",
                    "status": status,
                }
            )
    return rows


def _before_after_rows(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    metrics = sorted({* (before.get("metrics") or {}).keys(), *(after.get("metrics") or {}).keys()})
    rows: list[dict[str, str]] = []
    for metric in metrics:
        b = _metric_value(before, metric)
        a = _metric_value(after, metric)
        delta = a - b
        rows.append(
            {
                "metric": metric,
                "before": _format_metric(b),
                "after": _format_metric(a),
                "delta": _format_metric(delta),
                "direction": "up" if delta >= 0 else "down",
            }
        )
    return rows


def _judge_notes(summary: dict[str, Any]) -> list[str]:
    if isinstance(summary.get("judge_notes"), list) and summary["judge_notes"]:
        return [str(item) for item in summary["judge_notes"]]
    raw = summary.get("judge_spot_checks") or {}
    if isinstance(raw, dict):
        lines = []
        for case_id, comment in raw.items():
            lines.append(f"- {case_id}: {comment}")
        return lines
    return [
        "- No judge spot-check notes were captured for this run. Review the raw result rows and add a focused sample of ~10% of judged cases for narrative evidence."
    ]


def _known_failures(summary: dict[str, Any]) -> list[str]:
    failures = summary.get("known_failures") or []
    if isinstance(failures, list):
        return [str(item) for item in failures]
    return ["- No known failures were recorded for this run."]


def _render_report(before: dict[str, Any], after: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Evaluation report\n")
    lines.append("## Setup\n")
    lines.append(_build_setup_summary())
    lines.append("\n")
    lines.append("## Metrics summary\n")
    lines.append("| Area | Metric | Value | Threshold | PASS/FAIL |")
    lines.append("|---|---|---:|---|---|")
    for row in _collect_metric_rows(after):
        lines.append(f"| {row['area']} | {row['metric']} | {row['value']} | {row['threshold']} | {row['status']} |")
    lines.append("\n")
    lines.append("## Before vs after\n")
    lines.append("| Metric | Before | After | Delta | Direction |")
    lines.append("|---|---:|---:|---:|---|")
    for row in _before_after_rows(before, after):
        lines.append(f"| {row['metric']} | {row['before']} | {row['after']} | {row['delta']} | {row['direction']} |")
    lines.append("\n")
    lines.append("## Judge spot-check notes\n")
    for item in _judge_notes(after):
        lines.append(item)
    lines.append("\n")
    lines.append("## Known failures\n")
    for item in _known_failures(after):
        lines.append(item)
    lines.append("\n")
    lines.append("## Next improvements\n")
    lines.append("- Tighten the routing and document-validation thresholds where the last run drifted from the golden path.")
    lines.append("- Add more annotated edge cases for policy exclusions, duplicate claims, and missing-document restarts.")
    lines.append("- Capture a larger judge spot-check sample for the final release gate.")
    lines.append("- Re-validate the metric set after any workflow or tool-access change.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an evaluation markdown report from two summary files.")
    parser.add_argument("--before", required=True, help="Summary name to use as the baseline (e.g. baseline)")
    parser.add_argument("--after", required=True, help="Summary name to compare against the baseline (e.g. after)")
    args = parser.parse_args()

    try:
        before_summary = _load_json(_find_summary(args.before))
    except FileNotFoundError:
        before_summary = {}
    try:
        after_summary = _load_json(_find_summary(args.after))
    except FileNotFoundError:
        after_summary = {}

    report = _render_report(before_summary, after_summary)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote evaluation report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
