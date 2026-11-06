from __future__ import annotations

import secrets
from datetime import datetime


def new_case_id() -> str:
    return f"CLM-{datetime.utcnow():%Y%m%d}-{secrets.token_hex(2)[:4]}"
