from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "evals" / "results" / "latest_summary.json"
THRESHOLDS_PATH = ROOT / "evals" / "thresholds.yaml"


if not SUMMARY_PATH.exists():
    pytest.skip("latest_summary.json is missing; no eval gate data is available yet.", allow_module_level=True)

with THRESHOLDS_PATH.open("r", encoding="utf-8") as fh:
    THRESHOLDS = yaml.safe_load(fh) or {}

with SUMMARY_PATH.open("r", encoding="utf-8") as fh:
    SUMMARY = json.load(fh)


@pytest.mark.parametrize("metric,threshold", [(metric, data) for metric, data in THRESHOLDS.items()])
def test_threshold(metric: str, threshold: dict[str, object]) -> None:
    value = float((SUMMARY.get("metrics") or {}).get(metric, 0.0))
    op = str(threshold.get("op") or "==")
    expected = float(threshold.get("value") or 0.0)
    if op == ">=":
        assert value >= expected, f"{metric}={value} failed {op} {expected}"
    elif op == "<=":
        assert value <= expected, f"{metric}={value} failed {op} {expected}"
    else:
        assert value == expected, f"{metric}={value} failed {op} {expected}"
