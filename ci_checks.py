"""Verify the documented examples against their exit codes and reports."""

import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    checks = json.loads((root / "checks.json").read_text(encoding="utf-8"))
    for check in checks:
        result = subprocess.run(
            [sys.executable, "-B", *check["args"]], cwd=root, capture_output=True, timeout=10,
        )
        if result.returncode != check["exit"] or result.stderr or len(result.stdout.splitlines()) != 1:
            raise SystemExit(f"Unexpected CLI output or exit code in {check['name']}")
        if json.loads(result.stdout) != check["report"]:
            raise SystemExit(f"Unexpected report in {check['name']}")
        print(f"PASS {check['name']} (exit {check['exit']})")


if __name__ == "__main__":
    main()
