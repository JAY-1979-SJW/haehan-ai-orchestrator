"""Verify Docker build context exclusion policy.

This static gate catches files that should never enter the API image build
context, including local overrides, secrets, runtime data, caches, and frontend
incremental build artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = ROOT / ".dockerignore"

REQUIRED_PATTERNS = {
    ".git/",
    ".gitignore",
    "docker-compose.override.yml",
    "data/",
    "secrets/",
    ".env*",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "*.tsbuildinfo",
    "**/*.tsbuildinfo",
    "admin-web/tsconfig.tsbuildinfo",
    "local_agent/",
    "docs/",
}

FORBIDDEN_UNIGNORES = {
    "!secrets/",
    "!data/",
    "!.env",
    "!docker-compose.override.yml",
}


def dockerignore_lines(path: Path = DOCKERIGNORE) -> list[str]:
    if not path.exists():
        raise RuntimeError(f"missing .dockerignore: {path}")
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def evaluate(lines: list[str]) -> dict[str, Any]:
    present = set(lines)
    missing = sorted(REQUIRED_PATTERNS - present)
    forbidden_present = sorted(FORBIDDEN_UNIGNORES & present)
    failed = []
    if missing:
        failed.append("dockerignore_required_patterns_missing")
    if forbidden_present:
        failed.append("dockerignore_forbidden_unignore_present")
    return {
        "ok": not failed,
        "status": "ok" if not failed else "docker_context_policy_failed",
        "failed_check_ids": failed,
        "missing_required_patterns": missing,
        "forbidden_unignore_patterns": forbidden_present,
        "secret_values_output": False,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "Docker context policy verification",
        f"status: {payload['status']}",
        f"missing_required_patterns_count: {len(payload['missing_required_patterns'])}",
        f"forbidden_unignore_patterns_count: {len(payload['forbidden_unignore_patterns'])}",
    ]
    if payload["missing_required_patterns"]:
        lines.append("")
        lines.append("missing_required_patterns:")
        lines.extend(f"- {item}" for item in payload["missing_required_patterns"])
    if payload["forbidden_unignore_patterns"]:
        lines.append("")
        lines.append("forbidden_unignore_patterns:")
        lines.extend(f"- {item}" for item in payload["forbidden_unignore_patterns"])
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Docker context exclusion policy.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = evaluate(dockerignore_lines())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
