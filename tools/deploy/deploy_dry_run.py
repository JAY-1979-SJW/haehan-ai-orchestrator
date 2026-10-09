"""Run a deployment dry-run command and record quality-gate evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.quality.quality_gate import record_deploy_dry_run  # noqa: E402 - sys.path 부트스트랩 뒤 import


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and record a deploy dry-run command")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run after --")
    args = parser.parse_args()

    command = [part for part in args.command if part != "--"]
    if not command:
        print("usage: python tools/deploy/deploy_dry_run.py -- <dry-run command>", file=sys.stderr)
        return 2

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        encoding="utf-8",
    )
    print(result.stdout, end="")
    path = record_deploy_dry_run(command, exit_code=result.returncode, output=result.stdout)
    print(f"deploy dry-run evidence: {path}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
