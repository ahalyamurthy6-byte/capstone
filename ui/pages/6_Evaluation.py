from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "evals" / "results"


def _load_summary(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"name": path.stem, "metrics": {}, "pass": {}}


st.title("Evaluation dashboard")
paths = sorted(RESULTS_DIR.glob("*_summary.json")) if RESULTS_DIR.exists() else []
selected = st.multiselect("Select one or two summaries", [path.name for path in paths], default=[path.name for path in paths[:1]])
if not selected:
    st.info("No summary files are available yet.")
    st.markdown("[Open Phoenix](http://localhost:6006)")
    st.stop()

summaries = [_load_summary(RESULTS_DIR / name) for name in selected]
thresholds = {}
threshold_path = ROOT / "evals" / "thresholds.yaml"
if threshold_path.exists():
    import yaml

    thresholds = yaml.safe_load(threshold_path.read_text(encoding="utf-8")) or {}

all_metrics = sorted({metric for summary in summaries for metric in (summary.get("metrics") or {}).keys()})
rows = []
for metric in all_metrics:
    for index, summary in enumerate(summaries):
        value = float((summary.get("metrics") or {}).get(metric, 0.0))
        threshold = thresholds.get(metric, {})
        op = str(threshold.get("op") or "==")
        limit = float(threshold.get("value") or 0.0)
        pass_flag = value >= limit if op == ">=" else value <= limit if op == "<=" else value == limit
        rows.append({"summary": summary.get("name"), "metric": metric, "value": value, "threshold": limit, "op": op, "pass": pass_flag})

if rows:
    table = [
        {"summary": row["summary"], "metric": row["metric"], "value": row["value"], "threshold": f"{row['op']} {row['threshold']}", "pass": row["pass"]}
        for row in rows
    ]
    st.dataframe(table, use_container_width=True)
    if len(summaries) == 2:
        baseline, latest = summaries
        delta_rows = []
        for metric in all_metrics:
            before = float((baseline.get("metrics") or {}).get(metric, 0.0))
            after = float((latest.get("metrics") or {}).get(metric, 0.0))
            delta_rows.append({"metric": metric, "before": before, "after": after, "delta": after - before})
        st.dataframe(delta_rows, use_container_width=True)
        st.bar_chart({"before": [row["before"] for row in delta_rows], "after": [row["after"] for row in delta_rows]})

st.markdown("[Phoenix dashboard](http://localhost:6006)")
