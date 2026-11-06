#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres123@localhost:5433/genAI_training}"
HARD_RESET=0

if [[ "${1:-}" == "--hard" ]]; then
  HARD_RESET=1
fi

if [[ "$HARD_RESET" -eq 1 ]]; then
  echo "Hard reset: tearing down Docker volumes and recreating the stack."
  docker compose down -v
  docker compose up -d
  exit 0
fi

echo "audit_log is intentionally left untouched because it is append-only and preserves compliance history."

export DATABASE_URL
python - "$DATABASE_URL" <<'PY'
import os
import sys

from psycopg import connect

url = os.environ.get("DATABASE_URL") or sys.argv[1]

with connect(url, autocommit=True) as conn:
    with conn.cursor() as cur:
        tables = [
            "cases",
            "documents",
            "summaries",
            "assignments",
            "approvals",
            "sla_timers",
            "notifications",
        ]
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('checkpoints','checkpoint_writes','checkpoint_blobs')"
        )
        for (table_name,) in cur.fetchall():
            tables.append(table_name)

        for table_name in sorted(set(tables)):
            cur.execute(f"TRUNCATE TABLE IF EXISTS \"{table_name}\" RESTART IDENTITY CASCADE;")
PY

python -m scripts.init_db
python -m scripts.make_claim_packs
python -m db.seed

if curl -fsS -X DELETE http://localhost:8025/api/v1/messages >/dev/null 2>&1; then
  echo "Mailpit queue cleared."
else
  echo "Mailpit not reachable at localhost:8025; skipping API clear."
fi

echo "Demo database reset complete."
