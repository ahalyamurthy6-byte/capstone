from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from common.db import execute


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_audit(
    case_id: str,
    actor: str,
    action: str,
    before: Any | None = None,
    after: Any | None = None,
    checkpoint_id: str | None = None,
) -> None:
    payload_before = json.dumps(before, default=_json_default) if before is not None else None
    payload_after = json.dumps(after, default=_json_default) if after is not None else None
    execute(
        """
        INSERT INTO audit_log (case_id, actor, action, before, after, checkpoint_id)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        """,
        (case_id, actor, action, payload_before, payload_after, checkpoint_id),
    )
