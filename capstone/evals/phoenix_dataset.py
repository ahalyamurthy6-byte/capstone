from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = get_settings()
    dataset_path = ROOT / "data" / "golden.jsonl"
    rows: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    try:
        from phoenix.client import Client
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("phoenix is not installed") from exc

    client = Client(endpoint=settings.PHOENIX_ENDPOINT)
    dataset = client.upload_dataset(
        dataset_name="claims-golden",
        inputs=[{"pack_id": row.get("pack_id"), "scenario": row.get("scenario")} for row in rows],
        outputs=[{"expected": row.get("expected"), "expected_trajectory": row.get("expected_trajectory")} for row in rows],
        metadata=[{"scenario": row.get("scenario")} for row in rows],
    )
    print(f"Uploaded dataset: {dataset}")


if __name__ == "__main__":
    main()
