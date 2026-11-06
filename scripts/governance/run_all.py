from __future__ import annotations

import subprocess
import sys

CHECKS = [
    [sys.executable, "-m", "scripts.governance.check_pii_leak"],
    [sys.executable, "-m", "scripts.governance.check_injection"],
    [sys.executable, "-m", "scripts.governance.check_sla"],
]


def main() -> None:
    results: list[tuple[str, int]] = []
    for command in CHECKS:
        proc = subprocess.run(command, cwd=".")
        results.append((" ".join(command[3:]), proc.returncode))
        print(f"{command[3]}: {'PASS' if proc.returncode == 0 else 'FAIL'}")
    if any(code != 0 for _, code in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
