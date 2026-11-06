from __future__ import annotations

import json
import socket
import sys
import urllib.request
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import get_settings


REQUIRED_MODELS = {
    "qwen2.5:3b",
    "qwen2.5:7b",
    "llama3.1:8b",
    "nomic-embed-text",
}


def print_result(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{label}: {status} {detail}".strip())


def check_postgres() -> tuple[bool, str]:
    try:
        import psycopg

        settings = get_settings()
        with psycopg.connect(settings.DATABASE_URL, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm') ORDER BY extname;"
                )
                installed = {row[0] for row in cur.fetchall()}
        ok = {"vector", "pg_trgm"}.issubset(installed)
        detail = f"installed={sorted(installed)}"
        return ok, detail
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def check_ollama() -> tuple[bool, str]:
    try:
        settings = get_settings()
        with urllib.request.urlopen(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = {model.get("name") for model in payload.get("models", []) if isinstance(model, dict)}
        missing = sorted(REQUIRED_MODELS - names)
        ok = not missing
        detail = f"present={sorted(names)}; missing={missing}"
        return ok, detail
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def check_smtp() -> tuple[bool, str]:
    try:
        settings = get_settings()
        with socket.create_connection((settings.SMTP_HOST, settings.SMTP_PORT), timeout=5):
            return True, f"{settings.SMTP_HOST}:{settings.SMTP_PORT}"
    except OSError as exc:
        return False, str(exc)


def check_phoenix() -> tuple[bool, str]:
    try:
        settings = get_settings()
        with urllib.request.urlopen(settings.PHOENIX_ENDPOINT, timeout=10) as response:
            return True, f"status={response.status}"
    except (URLError, ValueError) as exc:
        return False, str(exc)


def main() -> int:
    checks = {
        "postgres": check_postgres(),
        "ollama": check_ollama(),
        "smtp": check_smtp(),
        "phoenix": check_phoenix(),
    }
    failed = False
    for label, (ok, detail) in checks.items():
        print_result(label, ok, detail)
        if not ok:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
