from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import get_settings


def run_sql_file(path: Path) -> None:
    settings = get_settings()
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.DATABASE_URL.split("://", 1)[1].split("@", 1)[0].split(":", 1)[1]
    subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-d", settings.DATABASE_URL, "-f", str(path)], check=True, env=env)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in [root / "db" / "00_extensions.sql", root / "db" / "init.sql"]:
        run_sql_file(path)

    settings = get_settings()
    result = subprocess.run(
        [
            "psql",
            "-At",
            "-d",
            settings.DATABASE_URL,
            "-c",
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    print("Database schema initialized.")
    print("Tables:")
    for line in result.stdout.strip().splitlines():
        if line:
            print(f"- {line}")


if __name__ == "__main__":
    main()
